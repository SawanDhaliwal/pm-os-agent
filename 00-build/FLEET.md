# Cortex Fleet — how to run and demo it

The runnable implementation of the design in `01-agent-line/` … `06-autonomy/`.
Five agents, three cadences, three human gates, all bounds enforced in Python.

```
transcript ──▶ Router ──┬──▶ PRD agent ──────┐
(hook + cron)  (cheap)  │    (frontier)      │
                        └──▶ Story agent ────┤──▶ Validator ──▶ HUMAN GATE ──▶ executor
monthly cron ──▶ Research ───▶ PRD agent ────┘   (independent)   (supervised)   (the only
                (frontier, the only self-starting loop)                          writer)
```

## Setup

```bash
cd 00-build
pip3 install -r requirements.txt
# ANTHROPIC_API_KEY must be in 00-build/.env
python3 cortex.py seed
```

Optional env (all have defaults; `CORTEX_MODEL` still works as the cheap tier):

| Var | Default | Meaning |
|---|---|---|
| `CORTEX_MODEL_CHEAP` | `claude-haiku-4-5` | Router, Story, Validator-on-stories |
| `CORTEX_MODEL_FRONTIER` | `claude-sonnet-5` | PRD, Research, Validator-on-PRD |
| `CORTEX_MAX_QUEUE_ITEMS` | `10` | stories per batch |
| `CORTEX_MATERIALITY_THRESHOLD` | `0.6` | anti-churn knob on the monthly scan |
| `CORTEX_FRESHNESS_DAYS` | `45` | research staleness window |
| `CORTEX_COST_CONFIRM` | `1` | gate before the expensive PRD path |

## The demo (start here)

```bash
python3 cortex.py demo --auto-approve
```

Four acts, each a screenshot:

| Act | Shows |
|---|---|
| 1 | **Continuous path** — epic deep-dive → stories → validator → gate → JIRA |
| 2 | **Episodic path** — discovery → cost-confirm gate → frontier PRD draft → gate |
| 3 | **Scheduled path** — monthly market scan, coverage %, materiality filter |
| 4 | **Guardrails** — injection refusal, sync-point refusal, seeded canary |

Without `--auto-approve` the demo stops at each gate — that's the honest supervised
behaviour. With it, approvals are simulated and **labelled `[SIMULATED HUMAN]`** in the
trace.

A full run takes a few minutes and costs roughly **$0.30–0.60** (the frontier-tier PRD
and Research legs dominate). For a fast, cents-scale dry run while you iterate or grab
screenshots, force everything onto the cheap tier:

```bash
CORTEX_MODEL_FRONTIER=claude-haiku-4-5 python3 cortex.py demo --auto-approve
```

Add `PYTHONUNBUFFERED=1` if you are piping to a file and want to watch it stream.

## Individual commands

```bash
python3 cortex.py bounds                    # the enforced bounds table
python3 cortex.py evals                     # 15 guard assertions, no API calls, free
python3 cortex.py evals --live              # + fixtures needing real model calls
python3 cortex.py transcript epic-deep-dive # one transcript through the fleet
python3 cortex.py scan                      # the monthly research scan
python3 cortex.py gates                     # what's waiting on a human
python3 cortex.py approve <gate_id> --edits 2
python3 cortex.py reject  <gate_id> --reason "..."
python3 cortex.py canary                    # seed a deliberately flawed artifact
python3 cortex.py status                    # state, cost, gate-integrity metrics
python3 cortex.py reset                     # wipe runtime state (fixtures untouched)
```

Transcript fixtures: `epic-deep-dive` (→stories) · `new-feature-discovery` (→PRD) ·
`ambiguous-scope` (→PRD, conservative) · `jailbreak-injection` (refuse) ·
`standup-chitchat` (→neither).

## Where each design decision lives in code

| Design claim | Enforced in |
|---|---|
| Bounds enforced in infra, not prompts | `fleet/config.py` + every reader |
| Per-agent model tiering | `fleet/config.py` `AGENTS` |
| Iteration × time fits the timeout | `fleet/config.py`, asserted by `evals` |
| Single writer: PRD agent owns PRDs | `fleet/state.py:write_prd` raises otherwise |
| Single writer: Research owns the cache | `fleet/state.py:write_cache` raises otherwise |
| Stories only off a **committed** PRD | `fleet/tools.py:get_committed_prd` |
| 100% story traceability | `fleet/tools.py:validate_story_traceability` |
| Queue cap, no split-to-dodge | `fleet/tools.py:enforce_queue_cap` |
| No standing external write credential | `fleet/executor.py` (token-gated) |
| Confidential containment (hard fail) | `fleet/executor.py:_scan_confidential` |
| Research required before a PRD | `fleet/prd.py` freshness check + validator |
| Coverage reported with the verdict | `fleet/research.py` |
| Per-source timeout ⇒ mark uncovered | `fleet/research.py` |
| Proposal cap + delta ledger (anti-churn) | `fleet/research.py`, `fleet/state.py` |
| Blocked-order TTL | `fleet/orchestrator.py:check_ttl` |
| Supervised rung / gates | `fleet/gates.py` |
| Canary catch-rate | `fleet/gates.py:integrity` |
| Permanent ceilings | `fleet/config.py:CEILINGS` |

## What is deliberately absent

There is no `create_jira_issue`, `commit_prd`, or `post_update` tool in any agent's
registry. The write paths exist only in `executor.py`, behind a one-time approval token
that only a human resolving a gate can mint. That is why "nothing auto-publishes" is a
property of the system rather than a promise in a prompt — and why a jailbroken agent
still cannot push a ticket.

Runtime state lives in `00-build/state/` (gitignored, regenerated by `seed`).
