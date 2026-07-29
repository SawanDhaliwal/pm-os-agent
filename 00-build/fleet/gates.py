"""Human gates — the mechanism that makes the trust rung `supervised` real.

An artifact reaching a gate is *queued*, never applied. The only way anything leaves
the fleet is a human resolving a gate, which mints a one-time **approval token** that
`executor.py` requires. No agent can mint one.

Also implements the governance canary (`06-autonomy/governance-and-strategy.md`): a
low human edit-rate is ambiguous — it means either the agent is reliable *or* the
reviewer stopped reading. Seeded defect artifacts tell those two apart.
"""

from __future__ import annotations

import secrets
import time

from . import config, state, trace


class GateError(RuntimeError):
    pass


def open_gate(kind: str, summary: str, artifact: dict, *, canary: bool = False) -> str:
    if kind not in config.GATE_KINDS:
        raise GateError(f"unknown gate kind '{kind}'")
    gates = state.load("gates.json")
    gate_id = f"gate_{kind}_{int(time.time() * 1000) % 10_000_000}"
    gates.append(
        {
            "id": gate_id,
            "kind": kind,
            "summary": summary,
            "artifact": artifact,
            "status": "pending",
            "opened_at": state.iso(),
            "resolved_at": None,
            "actor": None,
            "edits": None,
            "reason": None,
            "canary": canary,
            "token": None,
            "token_used": False,
            "ceiling": config.CEILINGS.get(
                {"jira_push": "jira_push", "prd_commit": "prd_commit",
                 "prd_update_push": "prd_update_push"}.get(kind, "story_batch"),
                "supervised",
            ),
        }
    )
    state.save("gates.json", gates)
    state.audit("gate.opened", "fleet", {"id": gate_id, "kind": kind, "canary": canary})
    trace.gate(kind, gate_id, summary)
    return gate_id


def pending() -> list[dict]:
    return [g for g in state.load("gates.json") if g["status"] == "pending"]


def get(gate_id: str) -> dict:
    for g in state.load("gates.json"):
        if g["id"] == gate_id:
            return g
    raise GateError(f"no such gate: {gate_id}")


def approve(gate_id: str, actor: str = "pm", edits: int = 0) -> str:
    """Resolve a gate. Returns a one-time approval token for the executor."""
    gates = state.load("gates.json")
    token = None
    for g in gates:
        if g["id"] != gate_id:
            continue
        if g["status"] != "pending":
            raise GateError(f"gate {gate_id} already {g['status']}")
        token = f"tok_{secrets.token_hex(8)}"
        g.update(
            status="approved",
            resolved_at=state.iso(),
            actor=actor,
            edits=edits,
            token=token,
            latency_s=round(
                (state.now() - state.datetime.fromisoformat(g["opened_at"])).total_seconds(), 1
            ),
        )
    if token is None:
        raise GateError(f"no such gate: {gate_id}")
    state.save("gates.json", gates)
    state.audit("gate.approved", actor, {"id": gate_id, "edits": edits})
    freed = state.unblock_orders(gate_id)
    if freed:
        trace.info(f"unblocked {len(freed)} work order(s) waiting on {gate_id}")
    return token


def reject(gate_id: str, reason: str, actor: str = "pm") -> None:
    gates = state.load("gates.json")
    for g in gates:
        if g["id"] == gate_id:
            if g["status"] != "pending":
                raise GateError(f"gate {gate_id} already {g['status']}")
            g.update(status="rejected", resolved_at=state.iso(), actor=actor, reason=reason)
    state.save("gates.json", gates)
    state.audit("gate.rejected", actor, {"id": gate_id, "reason": reason})


def assert_token(token: str) -> dict:
    """Validate a one-time approval token. This is the JIT-permission check: without
    an approved gate there is no token, and without a token there is no external write.
    """
    gates = state.load("gates.json")
    for g in gates:
        if g.get("token") and g["token"] == token:
            if g["status"] != "approved":
                raise GateError("token belongs to an unapproved gate")
            if g["token_used"]:
                raise GateError("approval token already used (one-time only)")
            g["token_used"] = True
            state.save("gates.json", gates)
            return g
    raise GateError("invalid approval token — no external write permitted")


# --- Governance metrics -------------------------------------------------------

def integrity() -> dict:
    """Gate-integrity metrics from M6: edit-rate, latency, and canary catch-rate.

    The canary rate is what disambiguates a low edit-rate. Promotion on edit-rate
    alone is explicitly disallowed by the decision rule.
    """
    gates = state.load("gates.json")
    resolved = [g for g in gates if g["status"] in ("approved", "rejected")]
    real = [g for g in resolved if not g["canary"]]
    canaries = [g for g in resolved if g["canary"]]

    edited = [g for g in real if (g.get("edits") or 0) > 0 or g["status"] == "rejected"]
    caught = [g for g in canaries if g["status"] == "rejected"]

    return {
        "resolved": len(resolved),
        "real_artifacts": len(real),
        "edit_rate": (len(edited) / len(real)) if real else None,
        "canaries_seeded": len(canaries),
        "canary_catch_rate": (len(caught) / len(canaries)) if canaries else None,
        "mean_latency_s": (
            round(sum(g.get("latency_s") or 0 for g in real) / len(real), 1) if real else None
        ),
        "pending": len(pending()),
    }


def seed_canary(prd_id: str = "PRD-NORTHSTAR") -> str:
    """Inject a deliberately flawed story batch into the review queue.

    The defect: a story whose `prd_scope_ref` points at an epic that does not exist.
    A functioning gate rejects it; an asleep reviewer approves it.
    """
    artifact = {
        "type": "story_batch",
        "prd_id": prd_id,
        "prd_version": 1,
        "stories": [
            {
                "title": "Add one-click SSO provisioning for enterprise admins",
                "acceptance_criteria": ["Admin can enable SSO in under a minute"],
                "prd_scope_ref": "EPIC-DOES-NOT-EXIST",
            }
        ],
    }
    return open_gate(
        "jira_push",
        "[SEEDED CANARY] 1 story queued for JIRA push",
        artifact,
        canary=True,
    )
