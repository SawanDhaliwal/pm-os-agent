"""Work-queue pump — the coordination layer.

Agents don't call each other. The Router (and the monthly scan) emit work orders; this
pumps the ready ones so the fast path never blocks on the slow path. It also enforces
the blocked-on dependency and the blocked-order TTL, which is the guard against silent
starvation (work that never runs because a human never reviewed).
"""

from __future__ import annotations

from . import config, executor, gates, llm, prd, state, stories, trace

HANDLERS = {
    "prd.work_requested": prd.run,
    "prd.update_proposed": prd.run,
    "stories.work_requested": stories.run,
}


def check_ttl() -> list[dict]:
    """Blocked orders past the TTL escalate rather than waiting forever."""
    expired = state.expired_blocked_orders()
    for o in expired:
        trace.bound(
            f"blocked-order TTL — {o['id']} ({o['kind']}) blocked "
            f">{config.BLOCKED_ORDER_TTL_DAYS}d on '{o['blocked_on']}'",
            tripped=True,
        )
        trace.fail(f"escalating {o['id']} to the PM — dependency never cleared")
        state.update_order(o["id"], status="escalated_ttl")
        state.audit("work.ttl_escalated", "orchestrator", {"id": o["id"]})
    return expired


def pump(max_orders: int = 10) -> list[dict]:
    """Run every ready work order. Returns the results."""
    check_ttl()
    results = []
    for _ in range(max_orders):
        queue = state.work_queue()
        ready = [o for o in queue if o["status"] == "ready"]
        if not ready:
            break
        order = ready[0]
        handler = HANDLERS.get(order["kind"])
        if handler is None:
            state.update_order(order["id"], status="unhandled")
            continue
        state.update_order(order["id"], status="running")
        try:
            res = handler(order)
        except llm.BoundExceeded as exc:
            trace.bound(f"{exc.bound_name} — {exc.detail}", tripped=True)
            res = {"status": "bound_tripped", "bound": exc.bound_name}
        except state.WriterViolation as exc:
            trace.fail(f"single-writer violation: {exc}")
            res = {"status": "writer_violation", "detail": str(exc)}
        state.update_order(order["id"], status=res.get("status", "done"), result=res)
        results.append({"order": order["id"], "kind": order["kind"], **res})
    return results


def apply_gate(gate_id: str) -> dict:
    """Apply an approved gate, then release anything that was waiting on it."""
    gate = gates.get(gate_id)
    out = executor.apply(gate_id)

    if gate["kind"] in ("prd_commit", "prd_update_push"):
        prd_id = gate["artifact"]["prd_id"]
        freed = state.unblock_orders(f"prd_committed:{prd_id}")
        if freed:
            trace.ok(f"{prd_id} committed — released {len(freed)} blocked story order(s)")
    return {"gate": gate_id, "kind": gate["kind"], "result": out}


def blocked_summary() -> list[list[str]]:
    rows = []
    for o in state.work_queue():
        if o["status"] == "blocked":
            rows.append(
                [
                    o["id"],
                    o["kind"],
                    o["blocked_on"] or "-",
                    f"{state.days_since(o['created_at']):.1f}d / {config.BLOCKED_ORDER_TTL_DAYS}d",
                ]
            )
    return rows
