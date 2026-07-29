"""Shared stores — the coordination surface for the fleet.

Implements the two load-bearing rules from `03-orchestration/orchestration-map.md` §6
**in infrastructure**:

  1. Single writer per store. `write_prd` refuses any caller that isn't the PRD agent;
     `write_cache` refuses any caller that isn't Research. A divergent second writer
     is not "discouraged", it raises.
  2. The committed-PRD version is the synchronization point. Stories may only be
     drafted against status == "committed", never a draft.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from . import config


class WriterViolation(RuntimeError):
    """A store was written by an agent that does not own it."""


def now() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime | None = None) -> str:
    return (dt or now()).isoformat()


def days_since(stamp: str) -> float:
    try:
        then = datetime.fromisoformat(stamp)
    except ValueError:
        return 1e9
    if then.tzinfo is None:
        then = then.replace(tzinfo=timezone.utc)
    return (now() - then).total_seconds() / 86400


_DEFAULTS: dict[str, Any] = {
    "prd_store.json": {},
    "research_cache.json": {"entries": [], "last_scan": None, "month_spend_usd": 0.0},
    "ledger.json": {"handled_events": [], "stories_created": [], "deltas_proposed": []},
    "work_queue.json": [],
    "gates.json": [],
    "jira.json": [],
    "audit.json": [],
}


def _path(name: str) -> Path:
    config.STATE_DIR.mkdir(parents=True, exist_ok=True)
    return config.STATE_DIR / name


def load(name: str) -> Any:
    p = _path(name)
    if not p.exists():
        return json.loads(json.dumps(_DEFAULTS[name]))
    return json.loads(p.read_text())


def save(name: str, data: Any) -> None:
    _path(name).write_text(json.dumps(data, indent=2))


def audit(event: str, actor: str, detail: dict) -> None:
    log = load("audit.json")
    log.append({"at": iso(), "event": event, "actor": actor, "detail": detail})
    save("audit.json", log)


# --- PRD store (single writer: the PRD agent) ---------------------------------

def prds() -> dict:
    return load("prd_store.json")


def committed_prds() -> dict:
    return {k: v for k, v in prds().items() if v.get("status") == "committed"}


def get_prd(prd_id: str) -> dict | None:
    return prds().get(prd_id)


def prd_index() -> list[dict]:
    """What the Router and Research see — titles/IDs/epics only, never full bodies
    (memory-and-context.md §1: the Router gets an index, not the corpus)."""
    out = []
    for pid, rec in prds().items():
        out.append(
            {
                "prd_id": pid,
                "title": rec.get("title"),
                "status": rec.get("status"),
                "version": rec.get("version"),
                "epics": [e["epic_id"] for e in rec.get("epics", [])],
            }
        )
    return out


def write_prd(record: dict, *, agent: str) -> dict:
    if agent != "prd":
        raise WriterViolation(
            f"single-writer rule: '{agent}' may not write the PRD store (owner: prd)"
        )
    store = prds()
    pid = record["prd_id"]
    existing = store.get(pid)
    record["version"] = (existing.get("version", 0) + 1) if existing else 1
    record["updated_at"] = iso()
    record.setdefault("status", "awaiting_commit")
    history = (existing or {}).get("history", [])
    if existing:
        history = history + [
            {"version": existing.get("version"), "status": existing.get("status"), "at": existing.get("updated_at")}
        ]
    record["history"] = history
    store[pid] = record
    save("prd_store.json", store)
    audit("prd.written", agent, {"prd_id": pid, "version": record["version"]})
    return record


def set_prd_status(prd_id: str, status: str, *, approval_token: str) -> dict:
    """Only the post-approval executor holds a token. See executor.py."""
    from . import gates

    gates.assert_token(approval_token)
    store = prds()
    store[prd_id]["status"] = status
    store[prd_id]["updated_at"] = iso()
    save("prd_store.json", store)
    audit("prd.status", "executor", {"prd_id": prd_id, "status": status})
    return store[prd_id]


# --- Research cache (single writer: the Research agent) -----------------------

def cache() -> dict:
    return load("research_cache.json")


def _norm_area(s: str) -> str:
    return "".join(ch for ch in (s or "").lower() if ch.isalnum())


def cache_slice(area: str) -> list[dict]:
    """Tolerant area matching.

    The area string reaches this function from two directions — the Router's structured
    field and, separately, whatever the PRD agent free-forms into a tool call ("team
    collaboration" vs "collaboration"). A strict equality check silently returns an empty
    slice and the agent concludes research is missing, so match on a normalized
    substring in either direction.
    """
    entries = cache()["entries"]
    if area == "*":
        return entries
    want = _norm_area(area)
    exact = [e for e in entries if _norm_area(e.get("area")) == want]
    if exact:
        return exact
    return [
        e
        for e in entries
        if want and (want in _norm_area(e.get("area")) or _norm_area(e.get("area")) in want)
    ]


def cache_freshness_days(area: str) -> float:
    entries = cache_slice(area)
    if not entries:
        return 1e9
    return min(days_since(e["stamped_at"]) for e in entries)


def is_stale(area: str) -> bool:
    return cache_freshness_days(area) > config.RESEARCH_FRESHNESS_DAYS


def write_cache(entries: list[dict], *, agent: str, spend_usd: float = 0.0) -> None:
    if agent != "research":
        raise WriterViolation(
            f"single-writer rule: '{agent}' may not write the research cache (owner: research)"
        )
    c = cache()
    by_key = {(e["source"], e["area"]): e for e in c["entries"]}
    for e in entries:
        by_key[(e["source"], e["area"])] = e
    c["entries"] = list(by_key.values())
    c["last_scan"] = iso()
    c["month_spend_usd"] = round(c.get("month_spend_usd", 0.0) + spend_usd, 4)
    save("research_cache.json", c)
    audit("cache.written", agent, {"count": len(entries), "spend_usd": spend_usd})


# --- Ledgers (dedupe; the stateful bound that stops cross-run runaway) --------

def ledger() -> dict:
    return load("ledger.json")


def seen_event(event_id: str) -> bool:
    return event_id in ledger()["handled_events"]


def mark_event(event_id: str) -> None:
    led = ledger()
    if event_id not in led["handled_events"]:
        led["handled_events"].append(event_id)
    save("ledger.json", led)


def delta_already_proposed(delta_key: str) -> bool:
    return any(d["key"] == delta_key and d["status"] == "open" for d in ledger()["deltas_proposed"])


def mark_delta_proposed(delta_key: str, summary: str) -> None:
    led = ledger()
    led["deltas_proposed"].append(
        {"key": delta_key, "summary": summary, "status": "open", "at": iso()}
    )
    save("ledger.json", led)


def existing_story_titles(prd_id: str) -> list[str]:
    backlog = json.loads((config.FIXTURES / "backlog.json").read_text())
    live = [s["title"] for s in backlog if s.get("prd_id") == prd_id]
    queued = [s["title"] for s in ledger()["stories_created"] if s.get("prd_id") == prd_id]
    return live + queued


def mark_stories_created(prd_id: str, titles: list[str]) -> None:
    led = ledger()
    for t in titles:
        led["stories_created"].append({"prd_id": prd_id, "title": t, "at": iso()})
    save("ledger.json", led)


# --- Work queue (blocked-on dependency + TTL) --------------------------------

def enqueue(kind: str, payload: dict, blocked_on: str | None = None) -> dict:
    q = load("work_queue.json")
    order = {
        "id": f"wo_{int(time.time() * 1000)}_{len(q)}",
        "kind": kind,
        "payload": payload,
        "status": "blocked" if blocked_on else "ready",
        "blocked_on": blocked_on,
        "created_at": iso(),
    }
    q.append(order)
    save("work_queue.json", q)
    audit("work.enqueued", "router", {"id": order["id"], "kind": kind, "blocked_on": blocked_on})
    return order


def work_queue() -> list[dict]:
    return load("work_queue.json")


def update_order(order_id: str, **fields) -> None:
    q = load("work_queue.json")
    for o in q:
        if o["id"] == order_id:
            o.update(fields)
    save("work_queue.json", q)


def unblock_orders(gate_id: str) -> list[dict]:
    """Called when a gate resolves: any order waiting on it becomes ready."""
    q = load("work_queue.json")
    freed = []
    for o in q:
        if o.get("blocked_on") == gate_id and o["status"] == "blocked":
            o["status"] = "ready"
            o["blocked_on"] = None
            freed.append(o)
    save("work_queue.json", q)
    return freed


def expired_blocked_orders() -> list[dict]:
    ttl = timedelta(days=config.BLOCKED_ORDER_TTL_DAYS)
    out = []
    for o in work_queue():
        if o["status"] == "blocked" and days_since(o["created_at"]) > ttl.days:
            out.append(o)
    return out


def reset() -> None:
    for name in _DEFAULTS:
        p = _path(name)
        if p.exists():
            p.unlink()
