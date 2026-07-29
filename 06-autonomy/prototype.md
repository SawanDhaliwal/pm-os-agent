# Prototype: Cortex PM Chief-of-Staff Agent

> Module 6 · ★ Deliverable 1, the working agent demo

## What it does

_Cortex ingests a discovery transcript (or wakes on a monthly market scan), decides whether the conversation implies a **scope change** or **story decomposition**, drafts the corresponding artifact grounded in retrieved evidence, has an independent Validator check it, and then **stops** — queuing it for a human. A PM owns every irreversible decision; the fleet owns all the drafting._

## How you built it

- **Coding agent:** **Claude Code**, directed design-first. Each module doc was written and argued through *before* any code existed, then the fleet in `00-build/` was generated against those docs — so the specs are the source of truth and the code is the implementation, not the reverse.
- **Repo / config:** [`00-build/`](../00-build/) — `cortex.py` (CLI + demo driver) and `fleet/` (14 modules). Run guide: [`00-build/FLEET.md`](../00-build/FLEET.md). Bounds live in one place, [`fleet/config.py`](../00-build/fleet/config.py).
- **Live link:** _n/a — runs locally against fixtures; no hosted surface._

**What each design doc specified, and where it landed in code:**

| Doc | Specified | Implemented in |
|---|---|---|
| [`agent-line-map.md`](../01-agent-line/agent-line-map.md) | 5 agents, 16 scored decisions, 3 human gates + 1 cost gate, per-agent model tiering | `fleet/config.py` (`AGENTS`, `CEILINGS`), the five agent modules |
| [`loop-spec.md`](../02-loop-design/loop-spec.md) | Three cadences: hook+cron transcript, monthly scan, event-driven workers | `fleet/router.py`, `fleet/research.py`, `fleet/orchestrator.py` |
| [`orchestration-map.md`](../03-orchestration/orchestration-map.md) | Work-order queue, blocked-on dependency, single-writer rules, per-artifact validator | `fleet/orchestrator.py`, `fleet/state.py`, `fleet/validator.py` |
| [`memory-and-context.md`](../04-memory-context/memory-and-context.md) | Per-agent context budgets, retrieve-vs-long-context, shared stores | `fleet/tools.py` (closed per-agent registries), `fleet/state.py` |
| [`bounds-and-evals.md`](../05-bounds-evals/bounds-and-evals.md) | Every bound below + the replay set | `fleet/config.py`, `fleet/evals.py` |
| [`governance-and-strategy.md`](../06-autonomy/governance-and-strategy.md) | `supervised` rung, permanent ceilings, canary catch-rate | `fleet/gates.py`, `fleet/executor.py` |

**Model + bounds — per agent, not one global setting** (`cortex.py bounds` prints this):

| Agent | Model tier | Max iterations | Timeout | Cost cap |
|---|---|---|---|---|
| Router | `claude-haiku-4-5` | 5 | 45s | $0.05 |
| User Story | `claude-haiku-4-5` | 8 | 90s | $0.10 |
| Validator (story) | `claude-haiku-4-5` | 3 | 45s | $0.05 |
| PRD | `claude-sonnet-5` | 15 | 15 min | $5.00 |
| Research | `claude-sonnet-5` | 5 **per source** | 90s **per source** | $2.00 |
| Validator (PRD) | `claude-sonnet-5` | 3 | 180s | $1.00 |

Timeouts are circuit breakers at ~2–3× expected p95, sized so that **iteration cap × per-iteration time fits inside the timeout** — otherwise the two bounds fight (asserted by the `bound-congruence` eval).

**Policy bounds:** queue cap **10** stories/batch (no split-to-dodge) · revision cap **2** · PRD proposals **≤3** per scan · research freshness window **45d** · blocked-order TTL **14d** · materiality threshold **0.6** · scan ceiling **45 min**, which derives a **~30-source** cap · monthly scan budget **$50**.

**The design principle that shaped the code:** bounds are enforced in Python, never requested in a prompt. `state.write_prd` *raises* if a non-PRD agent calls it; `tools.get_committed_prd` *refuses* to return a draft; `executor.py` is the only module that can write externally and requires a one-time token only a human gate can mint. There is no `create_jira_issue`, `commit_prd`, or `post_update` tool in any agent's registry — which is why a jailbroken agent still cannot push a ticket.

## Screenshots (required, collected M2 to M6)

Real screenshots of *your* Cortex running. These are the `00-build/CORTEX-ANATOMY.md` set and they are required, a link alone is not enough.

| # | Screenshot | What it shows | From |
|---|---|---|---|
| 1 | _[img]_ | happy-path run: a real drafted update + the HITL checkpoint (queued, not posted) | M2 |
| 2 | _[img]_ | the critic rejecting a bad draft (revise/block) | M3 |
| 3 | _[img]_ | a grounded update citing pulled activity + a caught hallucination | M4 |
| 4 | _[img]_ | jailbreak refused + escalated | M5 |
| 5 | _[img]_ | an iteration/cost/queue bound halting a runaway | M5 |
| 6 | _[img]_ | end-to-end run | M6 |

## How to run it

**Prerequisites:** Python 3 (built on 3.14.6) and an Anthropic API key.

```bash
cd 00-build && pip3 install -r requirements.txt
```

Put your key in `00-build/.env` (gitignored, never committed):

```
ANTHROPIC_API_KEY=sk-ant-...
```

No other env vars are required — every bound has a default. `CORTEX_MODEL` is honoured as the cheap-tier fallback if you already set it.

**1. Verify the guards — free, no API calls, sub-second.** This is the CI gate; 15/15 must pass.

```bash
cd 00-build && python3 cortex.py evals
```

**2. Print the enforced bounds** (also free — good first screenshot):

```bash
cd 00-build && python3 cortex.py bounds
```

**3. Run the full demo.** Four acts end to end. Verified: exit 0, 38 model calls, ~$0.20 on the fast tier (~$0.30–0.60 on the real frontier tier, a few minutes).

```bash
cd 00-build && python3 cortex.py demo --auto-approve
```

`--auto-approve` simulates the human at each gate and labels every one `[SIMULATED HUMAN]` in the trace. For a faster, cents-scale run while capturing screenshots:

```bash
cd 00-build && CORTEX_MODEL_FRONTIER=claude-haiku-4-5 python3 cortex.py demo --auto-approve
```

**4. To show the gates honestly, drop `--auto-approve`** — the run halts with nothing created, which is the real `supervised` behaviour:

```bash
cd 00-build && python3 cortex.py transcript epic-deep-dive
```

```bash
cd 00-build && python3 cortex.py gates
```

Approving is the *only* path to a JIRA write:

```bash
cd 00-build && python3 cortex.py approve <gate_id> --edits 2
```

**5. Individual scenarios** for the remaining screenshots:

```bash
cd 00-build && python3 cortex.py scan
```

```bash
cd 00-build && python3 cortex.py canary
```

```bash
cd 00-build && python3 cortex.py status
```

`scan` shows coverage % and materiality filtering; `canary` seeds a deliberately flawed artifact (reject it to prove the gate is awake); `status` shows fleet state, per-agent spend vs caps, and the gate-integrity metrics.

**For clean screenshots** — strip ANSI colour and stream to a file (`PYTHONUNBUFFERED=1` matters when piping, or Python buffers and you see nothing until the end):

```bash
cd 00-build && NO_COLOR=1 PYTHONUNBUFFERED=1 python3 cortex.py demo --auto-approve | tee /tmp/demo.log
```

**Reset between runs** (wipes only `00-build/state/`; fixtures untouched):

```bash
cd 00-build && python3 cortex.py reset && python3 cortex.py seed
```

Transcript fixtures: `epic-deep-dive` (→stories) · `new-feature-discovery` (→PRD) · `ambiguous-scope` (→PRD, conservative) · `jailbreak-injection` (refuse) · `standup-chitchat` (→neither). `python3 cortex.py --help` lists every command.
