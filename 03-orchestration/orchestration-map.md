# Orchestration Map: Cortex PM Chief-of-Staff Agent

> Module 3 · Orchestration & Subagents, ★ Deliverable 3
>
> Builds on your M2 Loop Spec. Only split one agent into a team when there's a real reason, coordination has a cost.

## 1. Why split? (or why not)

The single Cortex loop (transcript → synthesize → draft/update PRD → develop user stories → queue for JIRA) collapses jobs that operate on **three different cadences**, and that mismatch is the real reason to split:

- **PRDs are episodic and reactive.** A PRD is a long-lived strategic artifact, created or meaningfully updated only when a *significant* market or user shift appears. Producing one is expensive: it requires **both** user-interview synthesis **and** market research. This path runs rarely.
- **User stories are continuous.** They're generated *underneath* an already-committed PRD, on an ongoing basis, as conversations dig into an existing epic/feature. Cheap, frequent, narrow context.
- **Market research is periodic and proactive.** The market moves whether or not anyone had a meeting about it. Research shouldn't only fire when a PRD run happens to need it — it should also run on its own schedule (monthly), keeping a warm, freshness-stamped view of the landscape and **proactively proposing PRD updates when it detects a material change**. This is what keeps the product continually in tune with the market and lets us react in an agile way, instead of only noticing a competitive shift the next time someone books a discovery call.

Bundling these into one loop forces the expensive research pipeline onto the common path, *and* makes market-attunement purely reactive — you'd only ever learn about a market change downstream of an interview. Splitting lets the **high-frequency cheap path** (router + stories), the **rare expensive path** (PRD authoring), and the **scheduled monitoring path** (research) each run on their own clock.

The router is still the piece that makes transcripts actionable — a transcript doesn't announce whether it's about new epics/features (touch the PRD) or digging into an existing one (make user stories). But the research agent adds a **second way work enters the system**: not everything starts from a transcript; the monthly scan can originate a PRD-update on its own.

**What we deliberately do NOT split:** no per-story subagents (one decomposition pass handles a batch), and one shared Validator rather than one per artifact type (identical machinery, different checklist — see §5).

## 2. Topology

**Pattern:** Router / dispatcher (hierarchical) with **conditional** parallelism and a **second, scheduled entry point**. Two ways work starts: (a) a transcript through the router, (b) the monthly research scan. Both converge on the same PRD-authoring + Validator + human-checkpoint spine.

```
  transcript / signal                              ┌─── clock: monthly cron ───┐
   (hook + cron backup)                            ▼                           │
          │                                 ┌────────────────┐                 │
          ▼                                 │ Research Agent  │  on-demand call │
 ┌──────────────────┐   neither → drop      │ (standing;      │◀───────────────┘  from PRD agent
 │ Ingestion +      │──────────────────▶    │  two triggers)  │
 │ Router Agent     │   classify intent:    └───┬────────┬────┘
 │ (cheap, fast,    │   PRD? · stories? ·       │        │ writes
 │  every transcript)│  both? · ambiguous?      │        ▼
 └───────┬──────────┘                           │   market-research cache
         │ dispatch (work orders)               │   (shared, freshness-stamped)
   ┌─────┴──────────────────┐                   │
   ▼                        ▼                    │ monthly: material change?
┌────────────────────┐  ┌──────────────────────┐│  → prd.update_proposed
│ PRD Agent          │  │ User Story Agent      ││       (which PRDs affected)
│ (episodic,         │  │ (continuous, cheap)   ││
│  frontier model)   │  │  reads COMMITTED PRD, ││
│  authors new PRDs  │  │  never a draft        ││
│  AND research-     │◀─┼───req (blocking)──────┘│
│  driven updates    │◀─┼────────────────────────┘  research hands PRD-update
│  (single writer)   │  │                            work to the PRD agent
└─────────┬──────────┘  └──────────┬────────────┘
          │ PRD draft / update         story batch
          ▼                              ▼
     ┌──────────────────────────────────────┐
     │ Validator (independent, per-artifact) │
     └──────────────────┬───────────────────┘
                        │ pass
                        ▼
            human checkpoint ──▶ queued
                        ▲     (PRD commit · PRD update push · stories → JIRA)
                  (fail → revise, bounded; then escalate)
                        nothing auto-published, ever

  Dependency edge: if one transcript both changes a PRD AND asks for stories under it,
  the stories WAIT for the PRD to be human-committed first. Independent areas parallelize.
  The monthly research push follows the SAME human gate: no PRD update goes live un-reviewed.
```

## 3. Roster

| Agent / subagent | Responsibility | Runs which Loop Spec |
|---|---|---|
| **Ingestion + Router agent** | Ingests the transcript (pull + synthesize, M2 steps 1–2), dedupes, then **classifies intent** and dispatches work orders. Conservative on ambiguity — routes to the PRD-review path (or flags a human) rather than silently defaulting to story generation. | M2 loop (hook + cron), extended with classify/dispatch |
| **PRD agent** | The **single writer** of PRDs. Authors new PRDs and applies research-driven updates. Blocks on the Research agent for market context — a PRD is never authored from interviews alone. Produces drafts, queued for human commit. | PRD loop (episodic, goal-style) |
| **Research agent** *(now standing, not a subagent)* | **Two triggers:** (a) called on-demand by the PRD agent for a scoped ask; (b) a **monthly scheduled scan** that refreshes the market-research cache, and when it detects a *material* change, proposes updates to the affected existing PRDs (handed to the PRD agent to author, then human-gated). Keeps the product continually in tune with the market. | Research loop (cron + on-demand; read + market/web connectors) |
| **User Story agent** | Decomposes a specified epic/feature of a **committed** PRD into user stories with acceptance criteria, deduped, capped, queued before any JIRA push. | draft-user-stories loop (continuous) |
| **Validator** | Independent check on each artifact before it advances — never saw the draft context. One agent, per-artifact checklists (PRD, PRD-update, story batch). | validation loop (shared) |

## 4. Communication & hand-offs

Event-driven, through a shared work queue — agents emit work orders and pick them up, so the fast path never blocks on the slow path.

- **Router → PRD agent** (`prd.work_requested`): target feature area / epic (or "new"), the change signal, synthesized interview evidence, reason. The PRD agent then pulls research.
- **Router → User Story agent** (`stories.work_requested`): committed PRD ID + version, the epic/feature to decompose, relevant transcript signals.
- **PRD agent → Research agent** (on-demand, request/response): a scoped research ask. The Research agent **serves it from the warm cache when fresh**, and only does a live pull if the cache is stale — this is the payoff of the standing schedule: most PRD runs read a warm cache instead of blocking on a minutes-long live pull. If research is required but unavailable/too stale to trust → the PRD agent stops and escalates rather than authoring on thin evidence.
- **Research agent (monthly) → PRD agent** (`prd.update_proposed`): the detected market delta + the list of existing PRDs it materially affects. The PRD agent authors the actual update diff (keeping PRDs single-writer — the Research agent proposes *what* changed and *which* PRDs, it doesn't hand-edit PRD text itself). This is the agile loop: market moves → monthly scan catches it → affected PRDs get a proposed revision.
- **PRD / User Story agent → Validator**: the finished draft/update + the source data it used, for an independent pass.
- **Validator → human checkpoint**: pass → queued. A new PRD queues for commit; a **research-driven PRD update queues for human review before the final push** (no market-triggered change goes live un-reviewed); stories queue for the JIRA push. Nothing is auto-published.
- **The dependency hand-off (the coordination cost):** when one transcript triggers *both* a PRD change and stories under that same PRD, the router marks the story order **blocked-on** the PRD order — stories wait until the PRD is human-committed, so we never generate stories against a PRD that's about to change. Independent orders run concurrently.
- **Protocol note:** connectors (JIRA, OneDrive/SharePoint, M365, market-research sources) via MCP-style tool access per agent; inter-agent messaging is a lightweight internal event queue + work-order schema, not a full A2A protocol — the fleet is small enough.

## 5. The validator

One Validator agent, mode-switched by artifact type (same independent, pass/fail-with-reasons machinery as today's `critic.py`; only the checklist changes):

- **On a new PRD:** grounded in *both* interview synthesis and market research (flag/fail if research is thin, stale, or absent — it's required); scope traceable; aligned to roadmap + norms; no confidential/embargoed items; no committed dates or launch gates; and a **change-justification check** — the "significant change" claimed must actually be present.
- **On a research-driven PRD update:** additionally verify the **market delta is real and material**, sourced from the cache/scan that triggered it — not noise, a stale reading, or an over-reaction to a single data point. This guards the proactive path from churning PRDs on every minor market wobble, which would create human-review fatigue and defeat the agility goal.
- **On a story batch:** every story traces to a committed-PRD epic/line; acceptance criteria present; no duplication; within the batch cap; nothing pushed to JIRA (queued only).

- **What the critic checks:** grounded claims · norms compliance · no confidential leak · nothing posted/committed · (PRD) market research present · (PRD/update) change actually significant & sourced · (stories) traceable to a *committed* PRD.
- **Fail action:** revise, bounded by a revision cap (the `MAX_REVISIONS` bounce-cap from `critic.py`); on cap-exhaustion or a structural problem (missing research, non-material delta, story references a non-committed PRD) → escalate to a human, don't loop.

## 6. State: shared vs isolated

**Shared, system-wide (the source of truth the fleet coordinates on):**
- **Committed-PRD store** — authoritative record read by the router, the User Story agent, and the monthly research scan (to know which PRDs exist and could be affected). Carries PRD **version + status** (draft / awaiting-commit / committed). Stories key off *committed* only; a PRD mid-revision holds story generation for its affected epics.
- **Market-research cache** — now a **first-class shared store**, freshness-stamped, written by the Research agent (monthly refresh + on-demand pulls) and read by the PRD agent. Freshness stamps are what let a PRD run decide "warm enough to reuse" vs. "trigger a live pull." This store is the mechanism that decouples PRD-run latency from live research.
- **PKG / entity store** — personas, features, epics, competitors, OKRs that PRDs and stories link against.
- **Dedupe ledger** — handled transcript/event IDs (cron backup doesn't re-process a meeting the hook handled); stories-created (avoid duplicates); and **research deltas already proposed** (so the monthly scan doesn't re-propose the same market change month after month until it's acted on).
- **Roadmap + norms** — read-only, govern every agent.

**Isolated, per-run / per-agent:**
- Each agent's working draft (new PRD, PRD update, or story batch) until human-approved — never promoted to the shared store before its gate.
- Raw transcript text — purged after the router's synthesis; only structured signals + provenance persist.
- The Research agent's per-scan scratch (raw scraped/pulled market material) — distilled into cache entries with provenance, then dropped.
- Each agent's scratch/worktree (one workspace per PRD, grouped stories under it, per M2).

**Two load-bearing shared-state rules:**
1. **Committed-PRD version is the synchronization point** — stories are always generated against a pinned committed version, so a PRD update in flight can't silently invalidate a story batch drafted in parallel.
2. **The Research agent is the only writer of the cache; the PRD agent is the only writer of PRDs.** Single-writer discipline on both shared stores prevents two agents diverging on the same artifact — the monthly scan *proposes*, the PRD agent *authors*.

## 7. Cost & latency budget

The split is **cost-justified by frequency**: keep the expensive path off the common path, and make the monthly market cost predictable and bounded.

| Component | Frequency | Model tier | Rough per-run latency | Rough per-run token cost |
|---|---|---|---|---|
| Ingestion + Router | every transcript (high) | fast/cheap (`claude-haiku-4-5`) | seconds (synthesize + classify) | ~cents |
| User Story agent | frequent | fast/cheap | seconds–low minutes | ~cents |
| PRD agent | rare / episodic | frontier (`claude-sonnet-5`+) | minutes; **lower now** — reads warm cache instead of blocking on a live pull | 10–100× a story run |
| Research agent — on-demand | rare (only when cache stale) | frontier-ish + connectors | minutes (live pull) — mostly avoided by the schedule | moderate, infrequent |
| Research agent — monthly scan | 1×/month, predictable | frontier-ish + connectors, batched | minutes–tens of minutes (broad scan) | bounded monthly line item |
| Validator | per artifact | matches the artifact | seconds–minutes | proportional |

- **The schedule's payoff is latency, not just freshness:** by keeping the cache warm monthly, the on-demand research path (the one that sits *inside* a PRD run) fires rarely — so PRD authoring stops paying a live-research tax on every run. You trade a predictable monthly batch cost for lower per-PRD latency and continuous market coverage.
- **Coordination tax:** one extra classification hop (router) on every transcript, plus one recurring monthly scan. The router is cheap by design; the monthly scan is a fixed, forecastable cost. A misroute or a missed market shift is far more expensive than either.
- **Two budget-protecting HITLs:** (1) before spinning up the expensive PRD path on a "significant change" trigger, a light human confirm avoids burning it on a false positive; (2) research-driven PRD updates queue for human review before the final push — this is both a correctness gate *and* a cost/noise gate, since the Validator's materiality check plus the human keep the monthly scan from generating churn.
- **Forward-link to M5 bounds:** per-agent cost caps (tight on router/stories, looser on PRD, a fixed budget on the monthly scan); the Validator's revision cap bounces each artifact type separately; the **cache freshness window** and **committed-PRD retention** are the two knobs trading cost against staleness — the freshness window in particular sets how often on-demand pulls (expensive) fire vs. cache reads (cheap).
