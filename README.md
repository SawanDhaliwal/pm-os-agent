# Cortex: PM Chief-of-Staff Agent Fleet

> Final project for Product School's **Run Your AI Agent Team** certification.
>
> Cortex turns product-discovery transcripts and a scheduled market scan into **PRDs and JIRA-ready user stories**. It drafts everything autonomously and creates nothing: three human gates are the only paths out of the system, and they are enforced in infrastructure rather than requested in a prompt.

Built as a **five-agent fleet** — Router · Research · PRD · User Story · Validator — running on three different cadences, bounded per agent, and sitting on the `supervised` rung of the Trust Ladder.

---

## The agent in one sentence

Cortex ingests a discovery transcript (or wakes on a monthly market scan), decides whether the conversation implies a **scope change** or **story decomposition**, drafts the corresponding artifact grounded in retrieved evidence, has an independent Validator check it, and then **stops** — queuing it for a human. A PM owns every irreversible decision; the fleet owns all the drafting.

**Where the agent line falls:** below it — transcript synthesis, intent routing, market research, PRD drafting, story decomposition, validation. Above it — committing a PRD, pushing a research-driven PRD update live, and creating JIRA tickets. See [`01-agent-line/agent-line-map.md`](01-agent-line/agent-line-map.md).

## Deliverables at a glance

| # | Deliverable | Module | Status | File |
|---|---|---|---|---|
| 1 | **Working agent demo** | Built across labs | ◐ agent runs; write-up + screenshots pending | [`00-build/`](00-build/) · `06-autonomy/prototype.md` |
| 2 | **Loop Spec** | M2 | ✅ | [`02-loop-design/loop-spec.md`](02-loop-design/loop-spec.md) |
| 3 | **Orchestration Map** | M3 | ✅ | [`03-orchestration/orchestration-map.md`](03-orchestration/orchestration-map.md) |
| 4 | **Insights: build process** | M6 | ☐ template | `06-autonomy/build-insights.md` |
| 5 | **Insights: bounds, trust & autonomy strategy** | M6 | ✅ | [`06-autonomy/governance-and-strategy.md`](06-autonomy/governance-and-strategy.md) |

Supporting modules: [M1 agent line](01-agent-line/agent-line-map.md) ✅ · [M4 memory & context](04-memory-context/memory-and-context.md) ✅ · [M5 bounds & evals](05-bounds-evals/bounds-and-evals.md) ✅

## Build & demo

Built by directing **Claude Code** against the design docs in `01-` … `06-`, with the runnable fleet in [`00-build/`](00-build/). Full run guide: [`00-build/FLEET.md`](00-build/FLEET.md).

```bash
cd 00-build && python3 cortex.py evals
```

15 guard assertions, **no API calls, sub-second, free** — the CI gate.

```bash
cd 00-build && python3 cortex.py demo --auto-approve
```

Four acts end-to-end. Verified: **exit 0, 38 model calls, ~$0.20** on the fast tier.

| Act | Demonstrates |
|---|---|
| 1 | **Continuous path** — epic deep-dive → 5 stories → validator → gate → JIRA tickets written *only* post-approval |
| 2 | **Episodic path** — discovery → cost-confirm gate → stale-cache detected → on-demand research pull → PRD draft → `PRD_COMMIT` gate |
| 3 | **Scheduled path** — monthly scan; coverage reported as **PARTIAL (5/6)**, material deltas kept, noise dropped below threshold |
| 4 | **Guardrails** — prompt-injection refusal · non-committed-PRD refusal · required-research escalation · seeded canary |

Drop `--auto-approve` and the run genuinely halts at each gate with nothing created — that is the honest `supervised` behaviour.

## Where it sits on the Trust Ladder

**Current rung: `supervised`.** Every consequential action waits for approval. This isn't caution for its own sake — three of the M5 eval dimensions (materiality precision, gate integrity, routing accuracy) have **no production baseline yet** and can only be measured in supervised operation.

**To climb to `bounded-autonomous`** (per artifact class): ≥50 artifacts over ≥8 weeks, 100% story traceability, zero confidential-containment or unapproved-write breaches, human edit-rate <5% **and canary catch-rate ≥90%**.

That last condition is the load-bearing one. A low edit-rate is ambiguous — it means *either* the agent is reliable *or* the reviewer stopped reading, and those look identical in the data. So the review queue is seeded with deliberately flawed artifacts (`cortex.py canary`) and promotion requires catching them. **No class is ever promoted on edit-rate alone.**

**Two permanent ceilings:** committing a new PRD and pushing a research-driven PRD update never leave `supervised`. Measurability fails permanently — no volume of clean runs can prove that scope is an agent's call.

---

## How to submit

- Turn the five deliverable files into the final deck (the **Final Project Deliverables Builder** that ships with the course generates `pitch.html` + a clean `README.md`, or use a tool like Gamma).
- Submit within 7 days of the cohort ending.
- **Still outstanding:** `06-autonomy/prototype.md` (screenshots from the demo runs) and `06-autonomy/build-insights.md`.

## Repo structure

```
pm-os-agent/
├── README.md                          ← this dashboard
├── 00-build/                          ← the runnable fleet
│   ├── cortex.py                      ← CLI + demo driver (seed · demo · gates · approve · evals)
│   ├── FLEET.md                       ← how to run, and where each design decision lives in code
│   ├── fleet/
│   │   ├── config.py                  ← ALL bounds + model tiering (single source of truth)
│   │   ├── router.py                  ← Ingestion + Router  (cheap tier, every transcript)
│   │   ├── research.py                ← Research           (monthly cron + on-demand)
│   │   ├── prd.py                     ← PRD agent          (frontier tier, sole PRD writer)
│   │   ├── stories.py                 ← User Story agent   (cheap tier, committed PRDs only)
│   │   ├── validator.py               ← independent per-artifact checks
│   │   ├── gates.py                   ← human gates + approval tokens + canaries
│   │   ├── executor.py                ← the ONLY external writer, token-gated
│   │   ├── state.py                   ← shared stores, single-writer rules enforced
│   │   ├── orchestrator.py            ← work queue, blocked-on deps, TTL
│   │   ├── llm.py · tools.py · prompts.py · trace.py · evals.py
│   ├── fixtures/                      ← dummy data
│   │   ├── transcripts/               ← 5 discovery transcripts (incl. an injection attempt)
│   │   ├── market/                    ← 6 market sources (incl. a poisoned page)
│   │   └── roadmap.md · team-norms.md · okrs.md · backlog.json · past-prds.json
│   ├── RUNBOOK.md · PROMPTS.md · CORTEX-ANATOMY.md · DEMO-SCRIPT.md   ← course material
│   └── state/                         ← runtime state (gitignored, regenerated by `seed`)
├── 01-agent-line/agent-line-map.md    ← M1: above vs below the line, per agent
├── 02-loop-design/loop-spec.md        ← M2: three cadences              ★ Deliverable 2
├── 03-orchestration/orchestration-map.md ← M3: fleet + validator        ★ Deliverable 3
├── 04-memory-context/memory-and-context.md ← M4: per-agent context budgets
├── 05-bounds-evals/bounds-and-evals.md ← M5: bounds + the replay set
└── 06-autonomy/
    ├── prototype.md                   ← demo + screenshots             ★ Deliverable 1
    ├── build-insights.md              ← friction · learning · aha      ★ Deliverable 4
    └── governance-and-strategy.md     ← Trust Ladder + autonomy        ★ Deliverable 5
```

## What is deliberately absent from the code

There is no `create_jira_issue`, `commit_prd`, or `post_update` tool in any agent's registry. Those write paths exist only in `executor.py`, behind a one-time approval token that only a human resolving a gate can mint.

That is why *"nothing auto-publishes"* is a property of the system rather than a promise in a prompt — and why a fully jailbroken agent still cannot push a ticket.
