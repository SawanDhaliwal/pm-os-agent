"""The Validator — one agent, per-artifact checklists.

Independence is the design: it receives only the artifact and the exact source data the
drafting agent retrieved. Giving it more context would let it "fill in" evidence the
draft actually missed, which is the failure it exists to catch.

Deterministic checks run FIRST, in plain Python, before any model call. Traceability,
the queue cap, and confidential containment are zero-tolerance rows in
`bounds-and-evals.md` §3 — they must not depend on a judgment call.
"""

from __future__ import annotations

from . import config, llm, prompts, tools, trace

VERDICT_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["pass", "fail"]},
        "reasons": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["verdict", "reasons"],
    "additionalProperties": False,
}


def _deterministic_confidential(artifact: dict) -> list[str]:
    blob = str(artifact).lower()
    return [t for t in config.CONFIDENTIAL_TERMS if t in blob]


def _model_pass(agent: str, checks: str, artifact: dict, source_log: list[str]) -> dict:
    system = prompts.VALIDATOR_SYSTEM + "\n" + checks
    user = (
        "SOURCE DATA the drafting agent retrieved:\n"
        + "\n".join(source_log[:40])
        + "\n\nARTIFACT UNDER REVIEW:\n"
        + str(artifact)
    )
    return llm.judge(agent, system, user, VERDICT_SCHEMA)


def validate_prd(artifact: dict, source_log: list[str], *, is_update: bool = False) -> dict:
    """Frontier-tier check (matches the artifact, per the M1 anatomy)."""
    trace.agent("validator", f"reviewing {'PRD update' if is_update else 'new PRD'} (frontier tier)")

    leaks = _deterministic_confidential(artifact)
    if leaks:
        trace.bound(f"confidential containment — {leaks} present in PRD artifact", tripped=True)
        return {"verdict": "fail", "reasons": [f"confidential term(s) present: {leaks}"],
                "deterministic": True}

    research_seen = any("get_research" in s for s in source_log)
    if not research_seen:
        trace.bound("PRD drafted without calling get_research", tripped=True)
        return {"verdict": "fail", "deterministic": True,
                "reasons": ["market research is required for a PRD and was never retrieved"]}
    trace.bound("confidential containment clean; research retrieved")

    checks = prompts.VALIDATOR_PRD_CHECKS + (prompts.VALIDATOR_UPDATE_CHECKS if is_update else "")
    verdict = _model_pass("validator_prd", checks, artifact, source_log)
    verdict["deterministic"] = False
    return verdict


def validate_stories(artifact: dict, source_log: list[str]) -> dict:
    """Cheap-tier check. Traceability and the cap are settled in code first."""
    trace.agent("validator", "reviewing story batch (cheap tier)")

    leaks = _deterministic_confidential(artifact)
    if leaks:
        trace.bound(f"confidential containment — {leaks} in story batch", tripped=True)
        return {"verdict": "fail", "deterministic": True,
                "reasons": [f"confidential term(s) present: {leaks}"]}

    cap = tools.enforce_queue_cap(artifact["stories"])
    if not cap["ok"]:
        trace.bound(
            f"queue cap — {cap['count']} stories exceeds cap of {cap['cap']}", tripped=True
        )
        return {"verdict": "fail", "deterministic": True,
                "reasons": [f"{cap['error']}: {cap['count']} > {cap['cap']}; {cap['action']}"]}

    trc = tools.validate_story_traceability(artifact["prd_id"], artifact["stories"])
    if not trc["ok"]:
        trace.bound(f"story traceability — untraceable: {trc['untraceable']}", tripped=True)
        return {"verdict": "fail", "deterministic": True,
                "reasons": [f"stories not traceable to a committed epic: {trc['untraceable']}"]}

    trace.bound(f"cap {cap['count']}/{cap['cap']} ok; traceability 100% ok; no leaks")
    verdict = _model_pass("validator_story", prompts.VALIDATOR_STORY_CHECKS, artifact, source_log)
    verdict["deterministic"] = False
    return verdict


def report(verdict: dict) -> None:
    if verdict["verdict"] == "pass":
        trace.ok(f"VALIDATOR: pass ({'deterministic' if verdict.get('deterministic') else 'model'})")
    else:
        trace.fail("VALIDATOR: fail")
    for r in verdict.get("reasons", [])[:6]:
        trace.info(f"- {r}")
