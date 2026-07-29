# Loop Spec: Cortex PM Chief-of-Staff Fleet

> Module 2 · Loop Design
>
> Reconciled with the M1 agent line (`01-agent-line/agent-line-map.md`) and the M3 fleet (`03-orchestration/orchestration-map.md`). This is no longer one loop — it's a small fleet of loops on **three cadences**. The transcript path below is the original Cortex loop; the Research monitoring loop and the event-driven worker loops are what the fleet added.

## Trigger and loop type

| Agent | Trigger | Loop type |
|---|---|---|
| **Ingestion + Router** | Hook (a discovery transcript lands) **+ cron backup** | Reactive / event-driven (the entry loop) |
| **Research** | **Monthly cron** (scheduled scan) **+ on-demand** call from the PRD agent | Scheduled monitor + request/response |
| **PRD agent** | Work order from the Router or a `prd.update_proposed` from Research | Goal-style (draft until done, then gate) |
| **User Story agent** | Work order from the Router (may be **blocked-on** a PRD commit) | Goal-style |
| **Validator** | An artifact is drafted and ready | Single-pass, per artifact |

Agents coordinate through an **event / work-order queue**, not one linear loop — so the fast path (router → stories) never blocks on the slow path (PRD + research).

## Why this loop type

- **Transcript path — hook + cron backup (unchanged reasoning):** a product discovery meeting triggers an update to a PRD or the need for a new one; the hook reacts the moment the transcript lands, and a cron job ensures no meeting was missed. A heartbeat would be wasteful — discovery meetings don't occur on a regular cadence — and a pure goal loop would miss the transcript when it's available.
- **Research path — monthly cron (new):** the market moves whether or not anyone booked a meeting. A scheduled monthly scan keeps the product continually in tune with market changes and lets the fleet act in an agile way, instead of only noticing a competitive shift the next time a discovery call happens. This is the one loop that can **originate** work (a PRD update) with no transcript and no human prompt — which is exactly why its output is gated hard downstream (see Stop conditions).
- **Worker paths — event-driven (new):** the PRD and User Story agents don't poll; they wake on a work order. This lets the Router dispatch one, both, or neither, and lets a story order **wait** on an in-flight PRD commit rather than generating stories against a PRD that's about to change.

## Definition of done

Depends on which loop fired:
- **Transcript loop:** the transcript is classified and resolves to *either* dispatched work orders that produce **a PRD draft/update queued for human commit and/or a user-story batch queued for the JIRA push**, *or* "neither" → logged and dropped.
- **Research monthly loop:** a **refreshed, freshness-stamped market-research cache**, plus zero-or-more **proposed PRD updates queued for human review** on the PRDs a material change affects.
- **Worker loops:** a single artifact drafted, validated, and queued at its human gate. Nothing is ever auto-published.

## Stop conditions

- **Success:** the relevant artifact is drafted, passes the Validator, and is **queued for approval** at its gate (new-PRD commit · research-driven PRD-update push · stories → JIRA).
- **Stuck / give up:**
  - Transcript can't be pulled after 3 tries → stop and log (quarantine).
  - Required market research is missing or too stale to trust → the PRD agent **stops and escalates** rather than authoring on thin evidence.
  - Validator revision cap (`MAX_REVISIONS`) exhausted → stop bouncing, escalate to a human.
- **Escalate to human** — the three above-the-line gates from M1, plus one cost gate:
  - **Commit a new PRD** (locks the source of truth every story inherits).
  - **Push a research-driven PRD update live** (an agent proactively changing a committed doc).
  - **Push approved user stories to JIRA** (creates real, ID-bearing tickets).
  - **Cost confirm:** before the Router spins up the expensive PRD + research path on a "significant change" trigger, get a light human OK so a false positive doesn't burn the frontier pipeline.

## State

Spans the fleet — see `04-memory-context/memory-and-context.md` for the full map. In brief:
- **Shared, system-wide:** the **committed-PRD store** (+ version/status — the fleet's synchronization point; stories key off the *committed* version, never a draft), the **freshness-stamped market-research cache**, the **PKG/entity store**, the **dedupe ledger** (handled event IDs, stories-created, **and research deltas already proposed** so the monthly scan doesn't re-flag the same change every month), and read-only **roadmap + norms**.
- **Per-run / working:** current transcript synthesis, the draft being produced, retrieved slices, and **position in the approval flow** per work order.
- Scope: run-state retained ~30 days; PRDs/decisions retained long-term as the record. **Single-writer rules:** the PRD agent is the only writer of PRDs; the Research agent is the only writer of the cache.

## The five components

- **Work tree:** one workspace per PRD with its grouped user stories underneath (so they can be compared for duplication), **plus** per-connector / per-work-order isolation so the Router's parallel streams (a ticket vs. a transcript vs. the monthly scan) don't share state or block each other, **plus** the Research agent's per-scan scratch (distilled to cache entries, then dropped).
- **Skills:** `summarize-product-discovery-transcript`, `draft-PRD`, `draft-user-stories` (original), plus the fleet's additions: `classify-and-route` (intent → work orders), `dedupe`, `market-research-scan`, `detect-material-change`, `propose-prd-update`, `validate-artifact`.
- **Plugins / connectors:** JIRA (read/write — write only *after* the human gate), OneDrive/SharePoint (read/write), M365 (PRD drafting), **market / web + competitive-intel sources** (Research agent), and the internal **event/work-order queue** for inter-agent coordination.
- **Subagents:** this is now a full fleet, not a single agent spawning helpers — **Ingestion+Router** (dispatcher), **PRD agent** (single writer of PRDs), **Research agent** (standing; monthly + on-demand), **User Story agent**, **Validator** (independent, per-artifact). Topology and hand-offs are specified in `03-orchestration/orchestration-map.md`; the load-bearing edge is that a story order can be **blocked-on** a PRD commit.
- **State tracking:** as in State above — shared stores + per-work-order approval-flow position + the dedupe/proposed-delta ledgers.

## Context plan

Per `04-memory-context/memory-and-context.md`: each agent gets a **different** context budget, priority-ordered **artifact → governing constraints (norms/roadmap/committed-PRD) → evidence (research/interviews/analytics) → precedent**, with confidential flags honored at every layer so embargoed roadmap items never reach a shareable artifact. The Validator deliberately sees **only** the draft + the exact source data used, to keep its check independent. Large/changing sources (roadmap, backlog, market research, PKG) are **retrieved** as slices; bounded sources (norms, current OKRs, the target PRD, the current transcript) are held **long-context**. The stable prefix every run shares (norms + roadmap slice + acceptance-criteria template) is kept byte-stable for prompt-cache hits.

## Hand-off to bounds and evals (M5)

- **Write:** log each agent's per-iteration results and the PKG/PRD diffs (also the input to the redaction/grounding audits).
- **Select:** the right PRD + committed version, the right research slice, the backlog slice under the target epic.
- **Compress:** summarize past PRDs for precedent; prune the rolling dedup window without touching the permanent PRD record.
- **Isolate:** keep each connector's state separate, and keep other products out of the loop.
- **Per-agent bounds:** tight cost/iteration caps on the high-frequency Router + story path, a looser cap on the rare PRD path, and a **fixed monthly budget** on the Research scan.
- **Eval targets:** routing accuracy (Router), PRD groundedness (uses the retrieved evidence), story traceability (to a committed-PRD line), and **materiality precision** on the monthly scan (the M5 knob — too loose breeds review fatigue, too tight kills agility).
