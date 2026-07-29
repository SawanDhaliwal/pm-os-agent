#!/usr/bin/env python3
"""Cortex — PM chief-of-staff fleet. CLI + demo driver.

    python cortex.py seed                 # bootstrap dummy data (committed PRD + cache)
    python cortex.py demo                 # scripted end-to-end demo, stops at gates
    python cortex.py demo --auto-approve  # same, but simulates the human at each gate
    python cortex.py transcript <name>    # run the transcript path on one fixture
    python cortex.py scan                 # run the monthly market scan
    python cortex.py gates                # list pending human gates
    python cortex.py approve <gate_id> [--edits N]
    python cortex.py reject  <gate_id> --reason "..."
    python cortex.py status               # fleet state, cost, gate integrity
    python cortex.py bounds               # the enforced bounds table
    python cortex.py evals [--live]       # replay set / CI gate
    python cortex.py canary               # seed a deliberately flawed artifact
    python cortex.py reset                # wipe runtime state

Trust rung: supervised. Nothing leaves the fleet without a human resolving a gate.
"""

from __future__ import annotations

import argparse
import sys

from fleet import (
    config,
    evals,
    executor,
    gates,
    llm,
    orchestrator,
    research,
    router,
    state,
    trace,
)

TRANSCRIPTS = sorted(p.stem for p in (config.FIXTURES / "transcripts").glob("*.md"))


# --- seed ---------------------------------------------------------------------

def cmd_seed(_args) -> int:
    """Bootstrap: one committed PRD + a warm research cache, so the story path works."""
    trace.banner("SEED — dummy data for the demo")
    store = {
        "PRD-NORTHSTAR": {
            "prd_id": "PRD-NORTHSTAR",
            "title": "Northstar: self-serve onboarding activation",
            "area": "onboarding",
            "version": 3,
            "status": "committed",
            "problem_statement": (
                "New self-serve signups reach first value too slowly; activation stalls "
                "before the team ever sees intent."
            ),
            "target_user": "Self-serve admin evaluating the product in week one",
            "success_metrics": ["Activation rate 39% -> 50%", "Time-to-first-value < 10 min"],
            "in_scope": [
                "Guided activation checklist",
                "Step-completion instrumentation",
                "Empty-state guidance",
                "Contextual tips",
                "Day-2 milestone email",
            ],
            "out_of_scope": ["Pricing or packaging changes", "Enterprise SSO provisioning"],
            "epics": [
                {"epic_id": "EPIC-ONBOARD-01", "description": "Guided activation checklist"},
                {"epic_id": "EPIC-ONBOARD-02", "description": "Step-completion instrumentation"},
                {"epic_id": "EPIC-ONBOARD-03", "description": "Empty-state guidance + contextual tips"},
                {"epic_id": "EPIC-ONBOARD-04", "description": "Day-2 milestone email"},
            ],
            "evidence": ["seeded fixture"],
            "updated_at": state.iso(),
            "history": [],
        }
    }
    state.save("prd_store.json", store)
    trace.ok("PRD-NORTHSTAR v3 seeded as COMMITTED (4 epics)")

    state.save(
        "research_cache.json",
        {
            "entries": [
                {
                    "source": "seed",
                    "area": "onboarding",
                    "title": "Seeded baseline market read",
                    "findings": [
                        {
                            "claim": "Two direct competitors now ship guided onboarding checklists.",
                            "area": "onboarding",
                            "confidence": 0.8,
                        }
                    ],
                    "stamped_at": state.iso(),
                }
            ],
            "last_scan": state.iso(),
            "month_spend_usd": 0.0,
        },
    )
    trace.ok("research cache warmed for 'onboarding' (0d old, inside the 45d window)")
    trace.info("run `python cortex.py demo --auto-approve` next")
    return 0


# --- primitives ---------------------------------------------------------------

def _resolve_pending(auto: bool, actor: str = "pm(simulated)") -> list[dict]:
    """At the supervised rung a human resolves each gate. With --auto-approve we
    simulate that, loudly — a real deployment has a person here."""
    applied = []
    for g in gates.pending():
        if g["kind"] == "cost_confirm":
            label = "cost confirm"
        else:
            label = g["kind"]
        if not auto:
            continue
        trace.warn(f"[SIMULATED HUMAN] approving {label}: {g['id']}")
        tok = gates.approve(g["id"], actor=actor, edits=0)
        if g["kind"] == "cost_confirm":
            gates.assert_token(tok)
            trace.info("cost confirmed — expensive PRD path released")
        else:
            applied.append(orchestrator.apply_gate(g["id"]))
    return applied


def cmd_transcript(args) -> int:
    out = router.run(args.name)
    if out["status"] == "dispatched":
        _resolve_pending(args.auto_approve)
        orchestrator.pump()
        _resolve_pending(args.auto_approve)
        orchestrator.pump()
        _resolve_pending(args.auto_approve)
    llm.METER.report()
    _show_pending_hint()
    return 0


def cmd_scan(args) -> int:
    research.scan()
    _resolve_pending(args.auto_approve)
    orchestrator.pump()
    _resolve_pending(args.auto_approve)
    llm.METER.report()
    _show_pending_hint()
    return 0


def _show_pending_hint() -> None:
    p = gates.pending()
    if p:
        trace.rule("pending human gates")
        for g in p:
            print(f"  {g['id']}  {g['kind']:<16} {g['summary'][:70]}")
        trace.info("approve with: python cortex.py approve <gate_id>")


def cmd_gates(_args) -> int:
    p = gates.pending()
    trace.banner(f"PENDING HUMAN GATES — {len(p)} (trust rung: {config.TRUST_RUNG})")
    if not p:
        trace.ok("nothing waiting on a human")
        return 0
    rows = [
        [g["id"], g["kind"], g["ceiling"], "CANARY" if g["canary"] else "-", g["summary"][:40]]
        for g in p
    ]
    trace.table(["gate id", "kind", "ceiling", "seeded", "summary"], rows,
                widths=[26, 18, 22, 9, 42])
    return 0


def cmd_approve(args) -> int:
    g = gates.get(args.gate_id)
    if g["canary"]:
        trace.fail("You approved a SEEDED CANARY — the defect was not caught.")
        trace.info("Per the M6 decision rule this counts against canary catch-rate, and a")
        trace.info("low catch-rate blocks widening autonomy regardless of edit-rate.")
    gates.approve(args.gate_id, actor=args.actor, edits=args.edits)
    trace.ok(f"gate {args.gate_id} approved by {args.actor} (edits: {args.edits})")
    if g["kind"] != "cost_confirm":
        out = orchestrator.apply_gate(args.gate_id)
        trace.info(f"applied: {out['kind']}")
    orchestrator.pump()
    _show_pending_hint()
    return 0


def cmd_reject(args) -> int:
    g = gates.get(args.gate_id)
    gates.reject(args.gate_id, args.reason, actor=args.actor)
    if g["canary"]:
        trace.ok("Seeded canary CAUGHT — the human gate is functioning.")
    trace.ok(f"gate {args.gate_id} rejected: {args.reason}")
    return 0


def cmd_canary(_args) -> int:
    trace.banner("CANARY — seeding a deliberately flawed artifact")
    trace.info("Defect: a story whose prd_scope_ref points at a non-existent epic.")
    trace.info("A functioning gate rejects it. Approving it proves the gate is theater.")
    gid = gates.seed_canary()
    trace.info(f"reject with: python cortex.py reject {gid} --reason 'untraceable epic'")
    return 0


def cmd_bounds(_args) -> int:
    trace.banner("ENFORCED BOUNDS — every value checked in Python, not requested in a prompt")
    rows = []
    for name, b in config.AGENTS.items():
        rows.append([name, b.tier, str(b.max_iterations), f"{b.timeout_s}s", f"${b.cost_usd:.2f}"])
    trace.table(["agent", "model tier", "max iter", "timeout", "cost cap"], rows,
                widths=[18, 20, 11, 11, 11])
    print()
    policy = [
        ["queue cap (stories/batch)", str(config.MAX_QUEUE_ITEMS), "tools.enforce_queue_cap"],
        ["revision cap", str(config.MAX_REVISIONS), "prd.py / stories.py"],
        ["PRD proposals per scan", str(config.MAX_PRD_PROPOSALS_PER_SCAN), "research.scan"],
        ["research freshness window", f"{config.RESEARCH_FRESHNESS_DAYS}d", "state.is_stale"],
        ["blocked-order TTL", f"{config.BLOCKED_ORDER_TTL_DAYS}d", "orchestrator.check_ttl"],
        ["materiality threshold", str(config.MATERIALITY_THRESHOLD), "research.scan"],
        ["scan ceiling", f"{config.SCAN_CEILING_S}s", "research.scan"],
        ["max sources (derived)", str(config.MAX_SOURCES), "ceiling / per-source timeout"],
        ["monthly scan cap", f"${config.SCAN_MONTHLY_CAP_USD:.0f}", "research.scan"],
    ]
    trace.table(["policy bound", "value", "enforced in"], policy, widths=[30, 12, 34])
    print()
    trace.table(
        ["artifact class", "autonomy ceiling"],
        [[k, v] for k, v in config.CEILINGS.items()],
        widths=[26, 26],
    )
    trace.info("prd_commit + prd_update_push ceilings are PERMANENT (measurability fails)")
    return 0


def cmd_status(_args) -> int:
    trace.banner(f"FLEET STATUS — trust rung: {config.TRUST_RUNG}")

    prds = state.prds()
    if prds:
        trace.rule("PRD store (single writer: prd agent)")
        trace.table(
            ["prd id", "v", "status", "epics", "title"],
            [[p["prd_id"][:24], str(p["version"]), p["status"], str(len(p.get("epics", []))),
              (p.get("title") or "")[:28]] for p in prds.values()],
            widths=[26, 4, 18, 8, 30],
        )

    c = state.cache()
    trace.rule("research cache (single writer: research agent)")
    if c["entries"]:
        for e in c["entries"]:
            trace.info(f"{e['source']:<12} area={e['area']:<12} "
                       f"{state.days_since(e['stamped_at']):.0f}d old  "
                       f"{len(e['findings'])} finding(s)")
        trace.info(f"month spend: ${c.get('month_spend_usd', 0):.4f} / "
                   f"${config.SCAN_MONTHLY_CAP_USD:.0f} cap")
    else:
        trace.info("empty")

    q = state.work_queue()
    trace.rule("work queue")
    if q:
        trace.table(
            ["order", "kind", "status", "blocked on"],
            [[o["id"][-14:], o["kind"], o["status"], (o.get("blocked_on") or "-")[:28]] for o in q],
            widths=[18, 26, 18, 30],
        )
    else:
        trace.info("empty")

    board = state.load("jira.json")
    trace.rule("JIRA (written only by executor, post-approval)")
    if board:
        for t in board:
            trace.info(f"{t['key']:<8} {t['title'][:48]:<50} [{t['prd_scope_ref']}] "
                       f"approved_by={t['approved_by']}")
    else:
        trace.info("no tickets — nothing has been pushed")

    trace.rule("gate integrity (M6 governance metrics)")
    m = gates.integrity()
    er = "n/a" if m["edit_rate"] is None else f"{m['edit_rate']:.0%}"
    cc = "n/a" if m["canary_catch_rate"] is None else f"{m['canary_catch_rate']:.0%}"
    trace.table(
        ["metric", "value", "M6 requirement"],
        [
            ["resolved gates", str(m["resolved"]), "-"],
            ["pending gates", str(m["pending"]), "-"],
            ["human edit-rate", er, ">10% (else gate may be eroding)"],
            ["canaries seeded", str(m["canaries_seeded"]), "~1 in 20 artifacts"],
            ["canary catch-rate", cc, ">=90% to widen autonomy"],
            ["mean approval latency", f"{m['mean_latency_s'] or 0:.1f}s", "above a floor"],
        ],
        widths=[24, 14, 38],
    )
    if m["canary_catch_rate"] is not None and m["canary_catch_rate"] < 0.75:
        trace.fail("canary catch-rate <75% -> automatic demotion trigger (M6)")

    rows = orchestrator.blocked_summary()
    if rows:
        trace.rule("blocked orders (TTL watch)")
        trace.table(["order", "kind", "blocked on", "age / TTL"], rows, widths=[20, 26, 30, 16])
    return 0


def cmd_evals(args) -> int:
    evals.deterministic()
    if args.live:
        evals.live()
        llm.METER.report()
    return 0 if evals.summary() else 1


def cmd_reset(_args) -> int:
    state.reset()
    trace.ok("runtime state wiped (fixtures untouched)")
    return 0


# --- the demo -----------------------------------------------------------------

def cmd_demo(args) -> int:
    auto = args.auto_approve
    trace.banner(
        "CORTEX FLEET DEMO\n"
        "Router . Research . PRD . User Story . Validator\n"
        f"trust rung: {config.TRUST_RUNG}  |  "
        f"tiers: {config.TIER_CHEAP} (cheap) / {config.TIER_FRONTIER} (frontier)"
    )
    if not auto:
        trace.warn("running WITHOUT --auto-approve: the demo will stop at each human gate.")
        trace.info("add --auto-approve to simulate the human and see the full flow.\n")

    cmd_seed(args)

    # ACT 1 — the continuous cheap path: an epic deep-dive becomes stories.
    trace.banner("ACT 1 — continuous path: epic deep-dive -> user stories -> JIRA", trace.GREEN)
    router.run("epic-deep-dive")
    orchestrator.pump()
    _resolve_pending(auto)

    # ACT 2 — the episodic expensive path: new feature discovery -> PRD.
    trace.banner("ACT 2 — episodic path: discovery -> cost gate -> PRD draft", trace.BLUE)
    router.run("new-feature-discovery")
    _resolve_pending(auto)  # cost confirm releases the frontier path
    orchestrator.pump()
    _resolve_pending(auto)

    # ACT 3 — the autonomous originator: monthly scan proposes a PRD update.
    trace.banner("ACT 3 — scheduled path: monthly market scan (the only self-starting loop)",
                 trace.MAGENTA)
    research.scan()
    orchestrator.pump()
    _resolve_pending(auto)

    # ACT 4 — the guardrails.
    trace.banner("ACT 4 — guardrails", trace.RED)
    trace.rule("4a. prompt injection in a transcript")
    router.run("jailbreak-injection")

    trace.rule("4b. stories against a NON-committed PRD (the sync point)")
    # Land a draft PRD directly (as the owning agent) so the refusal is unambiguous:
    # the PRD exists, it is simply not committed yet.
    state.write_prd(
        {
            "prd_id": "PRD-DRAFTONLY",
            "title": "Deliberately left in draft, to prove the sync point",
            "area": "onboarding",
            "epics": [{"epic_id": "EPIC-DRAFT-01", "description": "not committed"}],
            "in_scope": [],
            "out_of_scope": [],
        },
        agent="prd",
    )
    state.enqueue("stories.work_requested",
                  {"prd_id": "PRD-DRAFTONLY", "epic_id": "EPIC-DRAFT-01"})
    orchestrator.pump()

    trace.rule("4c. PRD requested for an area with NO market research (required-research rule)")
    state.enqueue(
        "prd.work_requested",
        {"prd_id": "PRD-BILLINGX", "is_new": True, "area": "billing",
         "signals": ["two customers asked for usage-based billing"],
         "interview_summary": "Two interviews mentioned usage-based pricing.",
         "reason": "no market research exists for the billing area"},
    )
    orchestrator.pump()

    trace.rule("4d. seeded canary — is the human gate awake?")
    gates.seed_canary()

    trace.banner("DEMO COMPLETE")
    llm.METER.report()
    trace.info(f"total model spend this run: ${llm.METER.total():.4f} "
               f"across {llm.METER.calls} call(s)")
    print()
    cmd_status(args)
    _show_pending_hint()
    return 0


# --- arg parsing --------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="cortex", description="Cortex PM chief-of-staff fleet",
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__,
    )
    p.add_argument("--auto-approve", action="store_true",
                   help="simulate the human at every gate (labeled in the trace)")
    sub = p.add_subparsers(dest="cmd", required=True)

    def _auto(parser):
        parser.add_argument("--auto-approve", action="store_true", dest="auto_approve",
                            help="simulate the human at every gate (labeled in the trace)")
        return parser

    sub.add_parser("seed").set_defaults(fn=cmd_seed)
    _auto(sub.add_parser("demo")).set_defaults(fn=cmd_demo)
    _auto(sub.add_parser("scan")).set_defaults(fn=cmd_scan)
    sub.add_parser("gates").set_defaults(fn=cmd_gates)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    sub.add_parser("bounds").set_defaults(fn=cmd_bounds)
    sub.add_parser("canary").set_defaults(fn=cmd_canary)
    sub.add_parser("reset").set_defaults(fn=cmd_reset)

    t = _auto(sub.add_parser("transcript"))
    t.add_argument("name", choices=TRANSCRIPTS)
    t.set_defaults(fn=cmd_transcript)

    a = sub.add_parser("approve")
    a.add_argument("gate_id")
    a.add_argument("--edits", type=int, default=0, help="how many edits the human made")
    a.add_argument("--actor", default="pm")
    a.set_defaults(fn=cmd_approve)

    r = sub.add_parser("reject")
    r.add_argument("gate_id")
    r.add_argument("--reason", required=True)
    r.add_argument("--actor", default="pm")
    r.set_defaults(fn=cmd_reject)

    e = sub.add_parser("evals")
    e.add_argument("--live", action="store_true", help="also run fixtures needing model calls")
    e.set_defaults(fn=cmd_evals)

    args = p.parse_args(argv)
    try:
        return args.fn(args)
    except KeyboardInterrupt:
        trace.warn("interrupted")
        return 130


if __name__ == "__main__":
    sys.exit(main())
