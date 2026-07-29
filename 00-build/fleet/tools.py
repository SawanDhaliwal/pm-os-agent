"""Per-agent tool registries — closed sets.

Carried forward from the original `tools.py` design note: what an agent *cannot* do is
defined by what isn't in its registry. There is no `create_jira_issue`, no
`commit_prd`, no `post_update` anywhere in this file. The write paths live in
`executor.py` behind a human approval token.

Each agent gets only the tools its rows in `agent-line-map.md` need — the Story agent
cannot read market research, the Research agent cannot read a PRD body.
"""

from __future__ import annotations

import json

from . import config, state

FIX = config.FIXTURES


def _read(name: str) -> str:
    p = FIX / name
    return p.read_text() if p.exists() else ""


# --- Shared read tools --------------------------------------------------------

def get_roadmap(query: str = "") -> dict:
    return {
        "roadmap": _read("roadmap.md"),
        "warning": "items marked CONFIDENTIAL must never appear in an outbound artifact",
    }


def get_norms(query: str = "") -> dict:
    return {"norms": _read("team-norms.md")}


def get_okrs(query: str = "") -> dict:
    return {"okrs": _read("okrs.md")}


# --- PRD agent tools ----------------------------------------------------------

def get_research(area: str = "*") -> dict:
    """Read the market-research cache slice. Reports freshness so the agent can see
    staleness; the hard stop is enforced in prd.py, not left to judgment."""
    entries = state.cache_slice(area)
    if not entries:
        return {"area": area, "entries": [], "stale": True, "freshness_days": None,
                "note": "no research cached for this area"}
    return {
        "area": area,
        "entries": entries,
        "freshness_days": round(state.cache_freshness_days(area), 1),
        "stale": state.is_stale(area),
        "freshness_window_days": config.RESEARCH_FRESHNESS_DAYS,
    }


def get_prd(prd_id: str) -> dict:
    rec = state.get_prd(prd_id)
    if rec is None:
        return {"error": "prd_not_found", "prd_id": prd_id,
                "known": [p["prd_id"] for p in state.prd_index()]}
    return rec


def search_past_prds(query: str = "") -> dict:
    """Precedent for tone/structure — retrieve, don't invent a format."""
    corpus = json.loads(_read("past-prds.json") or "[]")
    terms = {t for t in query.lower().split() if len(t) > 3}
    hits = [c for c in corpus if not terms or any(t in json.dumps(c).lower() for t in terms)]
    return {"query": query, "matches": hits[:3] or corpus[:1]}


# --- User Story agent tools ---------------------------------------------------

def get_committed_prd(prd_id: str) -> dict:
    """The synchronization point, enforced in infrastructure.

    Refuses to return anything that is not `committed` — so the Story agent physically
    cannot draft against a draft PRD, regardless of what it is asked to do.
    """
    rec = state.get_prd(prd_id)
    if rec is None:
        return {"error": "prd_not_found", "prd_id": prd_id}
    if rec.get("status") != "committed":
        return {
            "error": "prd_not_committed",
            "prd_id": prd_id,
            "status": rec.get("status"),
            "action": "stories may only be drafted against a committed PRD version",
        }
    return {
        "prd_id": prd_id,
        "version": rec["version"],
        "title": rec["title"],
        "epics": rec["epics"],
        "in_scope": rec.get("in_scope", []),
        "out_of_scope": rec.get("out_of_scope", []),
    }


def get_backlog(prd_id: str) -> dict:
    """Existing stories, for dedupe."""
    return {"prd_id": prd_id, "existing_titles": state.existing_story_titles(prd_id)}


# --- Research agent tools -----------------------------------------------------

def list_sources() -> dict:
    """The governed source list. Its length is a bounds input (see config.MAX_SOURCES)."""
    sources = json.loads(_read("market/sources.json") or "[]")
    return {"sources": sources, "count": len(sources), "max_allowed": config.MAX_SOURCES}


def read_source(source_id: str) -> dict:
    sources = {s["id"]: s for s in json.loads(_read("market/sources.json") or "[]")}
    meta = sources.get(source_id)
    if meta is None:
        return {"error": "unknown_source", "source_id": source_id}
    body = _read(f"market/{meta['file']}")
    if not body:
        return {"error": "source_unreachable", "source_id": source_id}
    return {"source_id": source_id, "area": meta["area"], "title": meta["title"], "content": body}


# --- Deterministic validators (plain code, no model) -------------------------

def validate_story_traceability(prd_id: str, stories: list[dict]) -> dict:
    """Every story must resolve to a real epic in the committed PRD. 100% hard gate.

    Cheaper and more reliable than asking a model to re-check references.
    """
    prd = state.get_prd(prd_id) or {}
    valid = {e["epic_id"] for e in prd.get("epics", [])}
    bad = [
        {"title": s.get("title"), "ref": s.get("prd_scope_ref")}
        for s in stories
        if s.get("prd_scope_ref") not in valid
    ]
    return {"ok": not bad, "valid_epics": sorted(valid), "untraceable": bad}


def enforce_queue_cap(stories: list[dict]) -> dict:
    """The commitment bound. Over-cap batches are rejected, not silently trimmed —
    and explicitly not split, which would dodge the cap."""
    if len(stories) > config.MAX_QUEUE_ITEMS:
        return {
            "ok": False,
            "error": "batch_exceeds_queue_cap",
            "count": len(stories),
            "cap": config.MAX_QUEUE_ITEMS,
            "action": "escalate to a human; do not split the batch to dodge the cap",
        }
    return {"ok": True, "count": len(stories), "cap": config.MAX_QUEUE_ITEMS}


# --- Registries + schemas (what each agent may call) -------------------------

SCHEMAS = {
    "get_roadmap": {
        "name": "get_roadmap",
        "description": "Return the roadmap. Items marked CONFIDENTIAL must never be surfaced.",
        "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}},
    },
    "get_norms": {
        "name": "get_norms",
        "description": "Return the team norms / PM playbook that govern this agent.",
        "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}},
    },
    "get_okrs": {
        "name": "get_okrs",
        "description": "Return the current-quarter OKRs.",
        "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}},
    },
    "get_research": {
        "name": "get_research",
        "description": "Read the market-research cache for a product area. Required before drafting a PRD.",
        "input_schema": {
            "type": "object",
            "properties": {"area": {"type": "string"}},
            "required": ["area"],
        },
    },
    "get_prd": {
        "name": "get_prd",
        "description": "Read a PRD record by id (any status).",
        "input_schema": {
            "type": "object",
            "properties": {"prd_id": {"type": "string"}},
            "required": ["prd_id"],
        },
    },
    "search_past_prds": {
        "name": "search_past_prds",
        "description": "Find precedent PRDs for structure and tone.",
        "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}},
    },
    "get_committed_prd": {
        "name": "get_committed_prd",
        "description": "Read a COMMITTED PRD. Returns an error for drafts — stories may only be built on committed versions.",
        "input_schema": {
            "type": "object",
            "properties": {"prd_id": {"type": "string"}},
            "required": ["prd_id"],
        },
    },
    "get_backlog": {
        "name": "get_backlog",
        "description": "List existing story titles for a PRD so new ones are not duplicates.",
        "input_schema": {
            "type": "object",
            "properties": {"prd_id": {"type": "string"}},
            "required": ["prd_id"],
        },
    },
}

REGISTRY = {
    "prd": {
        "get_research": get_research,
        "get_roadmap": get_roadmap,
        "get_norms": get_norms,
        "get_okrs": get_okrs,
        "get_prd": get_prd,
        "search_past_prds": search_past_prds,
    },
    "stories": {
        "get_committed_prd": get_committed_prd,
        "get_backlog": get_backlog,
        "get_norms": get_norms,
    },
    "research": {
        "list_sources": list_sources,
        "read_source": read_source,
    },
}


def schemas_for(agent: str) -> list[dict]:
    return [SCHEMAS[name] for name in REGISTRY[agent] if name in SCHEMAS]
