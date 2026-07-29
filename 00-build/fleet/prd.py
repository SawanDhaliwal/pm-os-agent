"""PRD agent — the single writer of PRDs.

Frontier tier, rare, wide context. Runs a real tool loop (so the trajectory is
inspectable) capped at 15 iterations / 15 min / $5.

Two hard rules enforced here in code rather than left to the prompt:
  * **Research is required.** If the cache for the area is stale beyond the 45-day
    window and a live pull can't fix it, the agent STOPS and escalates — it never
    authors strategy on thin evidence.
  * **It cannot commit its own work.** `state.write_prd` lands the draft as
    `awaiting_commit`; only `executor.commit_prd` (holding a human approval token) can
    move it to `committed`.
"""

from __future__ import annotations

from . import config, gates, llm, prompts, research, state, tools, trace, validator

PRD_SCHEMA = {
    "type": "object",
    "properties": {
        "escalate": {"type": "boolean"},
        "escalate_reason": {"type": "string"},
        "prd_id": {"type": "string"},
        "title": {"type": "string"},
        "problem_statement": {"type": "string"},
        "target_user": {"type": "string"},
        "success_metrics": {"type": "array", "items": {"type": "string"}},
        "in_scope": {"type": "array", "items": {"type": "string"}},
        "out_of_scope": {"type": "array", "items": {"type": "string"}},
        "epics": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "epic_id": {"type": "string"},
                    "description": {"type": "string"},
                },
                "required": ["epic_id", "description"],
                "additionalProperties": False,
            },
        },
        "evidence": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "escalate", "escalate_reason", "prd_id", "title", "problem_statement",
        "target_user", "success_metrics", "in_scope", "out_of_scope", "epics", "evidence",
    ],
    "additionalProperties": False,
}


def _render(artifact: dict) -> str:
    lines = [
        f"{artifact['title']}  ({artifact['prd_id']})",
        "",
        f"PROBLEM   {artifact['problem_statement']}",
        f"USER      {artifact['target_user']}",
        "",
        "SUCCESS METRICS",
        *[f"  - {m}" for m in artifact["success_metrics"]],
        "",
        "IN SCOPE",
        *[f"  + {s}" for s in artifact["in_scope"]],
        "OUT OF SCOPE",
        *[f"  - {s}" for s in artifact["out_of_scope"]],
        "",
        "EPICS",
        *[f"  {e['epic_id']}  {e['description']}" for e in artifact["epics"]],
        "",
        "EVIDENCE RELIED ON",
        *[f"  * {e}" for e in artifact["evidence"][:8]],
    ]
    return "\n".join(lines)


def run(order: dict) -> dict:
    payload = order["payload"]
    prd_id = payload["prd_id"]
    is_new = payload.get("is_new", False)
    is_research_driven = order["kind"] == "prd.update_proposed"

    kind_label = "NEW PRD" if is_new else "PRD UPDATE"
    origin = "monthly market scan" if is_research_driven else "discovery transcript"
    trace.banner(f"PRD AGENT — {kind_label}: {prd_id}\norigin: {origin}", trace.BLUE)

    existing = state.get_prd(prd_id)
    # A NEW PRD takes its area from the router, not from a neighbouring PRD — otherwise
    # the freshness check passes on unrelated research and the required-research rule
    # silently does nothing.
    area = (existing or {}).get("area") or payload.get("area") or "*"

    # --- Required-research check, enforced before any drafting ---------------
    freshness = state.cache_freshness_days(area)
    if state.is_stale(area):
        trace.bound(
            f"research freshness — {area} is {freshness:.0f}d old "
            f"(window {config.RESEARCH_FRESHNESS_DAYS}d)",
            tripped=True,
        )
        pull = research.on_demand(area)
        if state.is_stale(area):
            trace.fail("required market research unavailable / still stale — ESCALATING")
            state.audit("prd.escalated", "prd", {"prd_id": prd_id, "reason": "stale_research"})
            return {"status": "escalated", "reason": "required research missing or stale",
                    "freshness_days": freshness, "pull": pull}
    else:
        trace.bound(f"research freshness — {area} {freshness:.0f}d old, within window")

    user = (
        f"TASK: {'Author a new PRD' if is_new else f'Draft an update to {prd_id}'}.\n"
        f"PRD id to use: {prd_id}\n"
        f"Reason this was triggered: {payload.get('reason','')}\n"
        f"Interview / user evidence: {payload.get('interview_summary','')}\n"
        f"Signals: {payload.get('signals', [])}\n"
    )
    if is_research_driven:
        user += (
            f"\nThis is a RESEARCH-DRIVEN update proposed by the monthly market scan "
            f"(materiality {payload.get('materiality')}). Market delta: "
            f"{payload.get('delta_summary')}\n"
        )
    user += (
        f"\nProduct area: '{area}'. Call get_research with exactly area='{area}'.\n"
        "Gather context with your tools first (research is required), then write the PRD."
    )

    try:
        artifact, source_log = llm.tool_loop(
            "prd",
            prompts.PRD_SYSTEM,
            user,
            tools.schemas_for("prd"),
            tools.REGISTRY["prd"],
            final_schema=PRD_SCHEMA,
        )
    except llm.BoundExceeded as exc:
        trace.bound(f"{exc.bound_name} — {exc.detail}", tripped=True)
        return {"status": "bound_tripped", "bound": exc.bound_name, "detail": exc.detail}

    if artifact.get("escalate"):
        trace.fail(f"agent escalated: {artifact['escalate_reason']}")
        return {"status": "escalated", "reason": artifact["escalate_reason"]}

    artifact["prd_id"] = prd_id  # never let the model rename the target
    trace.artifact(f"{kind_label} DRAFT (queued, not committed)", _render(artifact))

    # --- Independent validation, bounded revision loop -----------------------
    verdict = validator.validate_prd(artifact, source_log, is_update=not is_new)
    validator.report(verdict)
    revisions = 0
    while verdict["verdict"] == "fail":
        if revisions >= config.MAX_REVISIONS:
            trace.bound(f"revision cap {config.MAX_REVISIONS} — escalating, not looping",
                        tripped=True)
            return {"status": "escalated", "reason": "revision cap exhausted",
                    "verdict": verdict}
        revisions += 1
        trace.warn(f"revision {revisions}/{config.MAX_REVISIONS}")
        try:
            artifact, source_log = llm.tool_loop(
                "prd",
                prompts.PRD_SYSTEM,
                user + f"\n\nA validator REJECTED your draft: {verdict['reasons']}. Fix it.",
                tools.schemas_for("prd"),
                tools.REGISTRY["prd"],
                final_schema=PRD_SCHEMA,
            )
        except llm.BoundExceeded as exc:
            trace.bound(f"{exc.bound_name} — {exc.detail}", tripped=True)
            return {"status": "bound_tripped", "bound": exc.bound_name}
        artifact["prd_id"] = prd_id
        verdict = validator.validate_prd(artifact, source_log, is_update=not is_new)
        validator.report(verdict)

    # --- Land as a DRAFT. Only the executor can commit. ----------------------
    # An UPDATE merges onto the existing record rather than replacing it. A model that
    # returns an empty title or epics list on an update would otherwise wipe fields of a
    # live committed PRD — and because stories key off epic_ids, wiping epics silently
    # breaks story generation for that PRD. Empty never overwrites non-empty.
    def field(name: str):
        value = artifact.get(name)
        if value in (None, "", [], {}):
            return (existing or {}).get(name, value)
        return value

    record = {
        "prd_id": prd_id,
        "title": field("title"),
        "area": area if area != "*" else "onboarding",
        "problem_statement": field("problem_statement"),
        "target_user": field("target_user"),
        "success_metrics": field("success_metrics"),
        "in_scope": field("in_scope"),
        "out_of_scope": field("out_of_scope"),
        "epics": field("epics"),
        "evidence": field("evidence"),
        "status": "awaiting_commit",
    }
    if existing and existing.get("epics") and not record["epics"]:
        trace.bound("epic preservation — refusing to write an update that empties epics",
                    tripped=True)
        record["epics"] = existing["epics"]
    saved = state.write_prd(record, agent="prd")
    trace.agent("prd", f"{prd_id} v{saved['version']} written as 'awaiting_commit' "
                       f"(single-writer store)")

    gate_kind = "prd_update_push" if is_research_driven else "prd_commit"
    gate_artifact = dict(saved)
    if is_research_driven:
        gate_artifact["delta_key"] = payload.get("delta_key")
    gate_id = gates.open_gate(
        gate_kind,
        f"{kind_label} {prd_id} v{saved['version']} — {len(artifact['epics'])} epic(s). "
        f"Ceiling for this class: {config.CEILINGS[gate_kind]} (permanent).",
        gate_artifact,
    )
    return {"status": "queued", "gate_id": gate_id, "prd_id": prd_id,
            "version": saved["version"], "revisions": revisions}
