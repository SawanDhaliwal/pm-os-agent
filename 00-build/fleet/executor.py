"""Post-approval executor — the only component holding external write permission.

This is the infrastructure form of the M5 permissions bound: *no agent holds a
standing external write credential.* The User Story agent cannot reach JIRA; the PRD
agent cannot mark its own draft committed. Both queue a gate. Only this module writes,
and only against a one-time approval token minted by a human resolving that gate.

Deleting every agent's ability to do this is what makes "nothing auto-publishes" a
property of the system rather than a promise in a prompt.
"""

from __future__ import annotations

from . import config, gates, state, trace


class ConfidentialLeak(RuntimeError):
    """Zero-tolerance: an embargoed term reached an artifact about to leave the fleet."""


def _scan_confidential(payload: dict) -> None:
    """Deterministic pre-write scan. A hard fail, never a warning (M5 §2).

    Runs in plain Python precisely so a model cannot be persuaded to skip it.
    """
    blob = str(payload).lower()
    hits = [t for t in config.CONFIDENTIAL_TERMS if t in blob]
    if hits:
        raise ConfidentialLeak(
            f"embargoed term(s) {hits} present in an outbound artifact — write refused"
        )


def push_to_jira(token: str) -> list[dict]:
    """Create tickets. Requires an approved `jira_push` gate."""
    gate = gates.assert_token(token)
    if gate["kind"] != "jira_push":
        raise gates.GateError(f"token is for '{gate['kind']}', not a JIRA push")

    artifact = gate["artifact"]
    _scan_confidential(artifact)

    board = state.load("jira.json")
    created = []
    for i, story in enumerate(artifact["stories"], start=len(board) + 1):
        ticket = {
            "key": f"NS-{100 + i}",
            "title": story["title"],
            "acceptance_criteria": story.get("acceptance_criteria", []),
            "prd_id": artifact["prd_id"],
            "prd_version": artifact["prd_version"],
            "prd_scope_ref": story.get("prd_scope_ref"),
            "created_at": state.iso(),
            "approved_by": gate["actor"],
            "gate_id": gate["id"],
        }
        board.append(ticket)
        created.append(ticket)
    state.save("jira.json", board)
    state.mark_stories_created(artifact["prd_id"], [s["title"] for s in artifact["stories"]])
    state.audit("jira.pushed", "executor", {"count": len(created), "gate_id": gate["id"]})
    trace.agent("executor", f"created {len(created)} JIRA ticket(s) — post-approval write")
    for t in created:
        trace.info(f"{t['key']}  {t['title']}  [{t['prd_scope_ref']}]")
    return created


def commit_prd(token: str) -> dict:
    """Move a PRD draft to `committed`. Requires an approved PRD gate."""
    gate = gates.assert_token(token)
    if gate["kind"] not in ("prd_commit", "prd_update_push"):
        raise gates.GateError(f"token is for '{gate['kind']}', not a PRD commit")

    artifact = gate["artifact"]
    _scan_confidential(artifact)
    prd_id = artifact["prd_id"]

    # Re-mint a token for the state layer's own writer check.
    gates_list = state.load("gates.json")
    for g in gates_list:
        if g["id"] == gate["id"]:
            g["token_used"] = False
    state.save("gates.json", gates_list)

    rec = state.set_prd_status(prd_id, "committed", approval_token=token)
    trace.agent("executor", f"{prd_id} v{rec['version']} -> committed (approved by {gate['actor']})")

    # Close the research delta this update answered, so next month's scan does not
    # re-propose it (the stateful bound from M5's runaway-loop check).
    if gate["kind"] == "prd_update_push" and artifact.get("delta_key"):
        led = state.ledger()
        for d in led["deltas_proposed"]:
            if d["key"] == artifact["delta_key"]:
                d["status"] = "closed"
        state.save("ledger.json", led)
        trace.info(f"closed research delta '{artifact['delta_key']}' in the ledger")
    return rec


def apply(gate_id: str) -> dict | list[dict]:
    """Dispatch an approved gate to the right write path."""
    gate = gates.get(gate_id)
    if gate["status"] != "approved":
        raise gates.GateError(f"gate {gate_id} is {gate['status']}, not approved")
    if gate["kind"] == "jira_push":
        return push_to_jira(gate["token"])
    if gate["kind"] in ("prd_commit", "prd_update_push"):
        return commit_prd(gate["token"])
    if gate["kind"] == "cost_confirm":
        gates.assert_token(gate["token"])
        trace.info("cost confirmed — expensive PRD path released")
        return {"released": True}
    raise gates.GateError(f"no executor path for gate kind '{gate['kind']}'")
