"""User Story agent — continuous, cheap tier, narrow context.

Decomposes one epic of a **committed** PRD into stories. Three guards, all in code:
  * `tools.get_committed_prd` refuses to return a draft, so the agent physically cannot
    decompose a PRD that is mid-change (the synchronization point).
  * `validate_story_traceability` is a deterministic 100% gate — every story must
    resolve to a real epic_id.
  * `enforce_queue_cap` rejects an over-cap batch outright and refuses the split-to-dodge
    workaround.

It has no JIRA write. Its output is queued for a human.
"""

from __future__ import annotations

from . import config, gates, llm, prompts, state, tools, trace, validator

STORIES_SCHEMA = {
    "type": "object",
    "properties": {
        "escalate": {"type": "boolean"},
        "escalate_reason": {"type": "string"},
        "prd_id": {"type": "string"},
        "epic_id": {"type": "string"},
        "stories": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "acceptance_criteria": {"type": "array", "items": {"type": "string"}},
                    "prd_scope_ref": {"type": "string"},
                },
                "required": ["title", "acceptance_criteria", "prd_scope_ref"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["escalate", "escalate_reason", "prd_id", "epic_id", "stories"],
    "additionalProperties": False,
}


def _render(artifact: dict) -> str:
    out = [f"{artifact['prd_id']} / {artifact['epic_id']} — "
           f"{len(artifact['stories'])} story(ies), queued for approval", ""]
    for i, s in enumerate(artifact["stories"], 1):
        out.append(f"{i}. {s['title']}   [{s['prd_scope_ref']}]")
        for ac in s["acceptance_criteria"][:4]:
            out.append(f"     AC: {ac}")
    return "\n".join(out)


def run(order: dict) -> dict:
    payload = order["payload"]
    prd_id = payload["prd_id"]
    epic_id = payload.get("epic_id") or ""

    trace.banner(f"USER STORY AGENT — {prd_id} / {epic_id or '(epic from PRD)'}", trace.GREEN)

    # Fail fast, in code, before spending a token on an uncommitted PRD.
    check = tools.get_committed_prd(prd_id)
    if "error" in check:
        trace.bound(f"committed-PRD sync point — {check['error']} "
                    f"(status: {check.get('status')})", tripped=True)
        trace.fail("refusing to draft stories against a non-committed PRD — escalating")
        state.audit("stories.refused", "stories", {"prd_id": prd_id, "why": check["error"]})
        return {"status": "escalated", "reason": check["error"], "prd_id": prd_id}
    trace.bound(f"committed-PRD sync point — {prd_id} v{check['version']} is committed")
    pinned_version = check["version"]

    user = (
        f"Decompose epic '{epic_id}' of PRD {prd_id} into user stories.\n"
        f"If no epic was named, pick the single most relevant epic and say which.\n"
        f"Conversation signals: {payload.get('signals', [])}\n"
        f"Read the committed PRD and the existing backlog before writing.\n"
        f"Hard cap: at most {config.MAX_QUEUE_ITEMS} stories."
    )

    try:
        artifact, source_log = llm.tool_loop(
            "stories",
            prompts.STORIES_SYSTEM,
            user,
            tools.schemas_for("stories"),
            tools.REGISTRY["stories"],
            final_schema=STORIES_SCHEMA,
        )
    except llm.BoundExceeded as exc:
        trace.bound(f"{exc.bound_name} — {exc.detail}", tripped=True)
        return {"status": "bound_tripped", "bound": exc.bound_name, "detail": exc.detail}

    if artifact.get("escalate"):
        trace.fail(f"agent escalated: {artifact['escalate_reason']}")
        return {"status": "escalated", "reason": artifact["escalate_reason"]}

    artifact["prd_id"] = prd_id
    artifact["prd_version"] = pinned_version
    artifact["type"] = "story_batch"
    trace.artifact("STORY BATCH (queued, nothing created in JIRA)", _render(artifact))

    verdict = validator.validate_stories(artifact, source_log)
    validator.report(verdict)
    revisions = 0
    while verdict["verdict"] == "fail":
        if revisions >= config.MAX_REVISIONS:
            trace.bound(f"revision cap {config.MAX_REVISIONS} — escalating, not looping",
                        tripped=True)
            return {"status": "escalated", "reason": "revision cap exhausted", "verdict": verdict}
        revisions += 1
        trace.warn(f"revision {revisions}/{config.MAX_REVISIONS}")
        try:
            artifact, source_log = llm.tool_loop(
                "stories",
                prompts.STORIES_SYSTEM,
                user + f"\n\nA validator REJECTED your batch: {verdict['reasons']}. Fix it.",
                tools.schemas_for("stories"),
                tools.REGISTRY["stories"],
                final_schema=STORIES_SCHEMA,
            )
        except llm.BoundExceeded as exc:
            trace.bound(f"{exc.bound_name} — {exc.detail}", tripped=True)
            return {"status": "bound_tripped", "bound": exc.bound_name}
        artifact["prd_id"] = prd_id
        artifact["prd_version"] = pinned_version
        artifact["type"] = "story_batch"
        verdict = validator.validate_stories(artifact, source_log)
        validator.report(verdict)

    gate_id = gates.open_gate(
        "jira_push",
        f"{len(artifact['stories'])} story(ies) for {prd_id} v{pinned_version} "
        f"queued for the JIRA push. Ceiling for this class: "
        f"{config.CEILINGS['jira_push']}.",
        artifact,
    )
    return {"status": "queued", "gate_id": gate_id, "count": len(artifact["stories"]),
            "revisions": revisions}
