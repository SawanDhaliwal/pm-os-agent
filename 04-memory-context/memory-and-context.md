# Memory & Context: Cortex PM Chief-of-Staff Agent

> Module 4 · Memory & Context
>
> Builds on the M3 fleet (see `03-orchestration/orchestration-map.md`): Router, PRD agent, Research agent (monthly + on-demand), User Story agent, Validator. "Memory" now spans **shared stores** the fleet coordinates on **plus** each agent's own **working context** — the two are designed separately below.

## 1. Context budget

Each agent has a different job, so each gets a different budget — a single "stuff everything in" context would be wrong for all five. Priority order inside any budget: **(1) the artifact being acted on** (the transcript, the PRD, the epic) → **(2) the governing constraints** (norms, roadmap slice, committed-PRD version) → **(3) evidence** (research, interview synthesis, analytics, signals) → **(4) precedent** (nearest past PRD/decision for tone/structure). Confidential flags are honored at every layer, so embargoed roadmap items never reach a shareable artifact.

| Agent | Receives each iteration | Why this and not more |
|---|---|---|
| **Router** | Transcript synthesis + intent taxonomy + an **index** of committed PRDs/epics (titles + IDs, not full text) + dedupe ledger | It only classifies and dispatches — it needs to know *which* epics exist to route "digging into an existing feature," not the full PRDs. Cheap by design (runs every transcript). |
| **PRD agent** | Interview synthesis + the **relevant slice** of the market-research cache + roadmap slice + current-quarter OKRs + the existing PRD being updated (full, if an update) + norms + PKG entities for the feature area | This is the expensive path; it earns the widest budget. Everything here is evidence the Validator will check the draft *against*. |
| **Research agent** | Market/competitor sources + the list of committed PRDs (to assess impact) + the "deltas already proposed" ledger | Monthly scan reasons over the market, then maps changes onto existing PRDs — it needs the PRD *index* and what it's already flagged, not PRD internals. |
| **User Story agent** | The committed PRD epic being decomposed (full) + existing backlog items under that epic (for dedupe) + norms + an acceptance-criteria template | Narrow and cheap: one epic, its existing stories, the rules. It never sees market research or other PRDs. |
| **Validator** | Only the finished draft + the exact source data the drafting agent used — **nothing else** | Independence is the point (mirrors `critic.py`): giving it extra context would let it "fill in" gaps the draft actually missed. It grades what's in front of it. |

## 2. Retrieve vs. long-context: per source

For each source: **retrieve** (narrow a large/changing corpus to the relevant slice) or **long-context** (include a bounded set and reason over the whole thing).

| Source | Size / volatility | Decision | Why |
|---|---|---|---|
| **Current transcript** (discovery/interview) | bounded per run (large if long) | Long-context (chunked if very long) | The whole conversation is the input to synthesis; reason over all of it. |
| **Historical transcripts** | large, growing | Retrieve | Only pull a prior conversation when a new one references it. |
| **Roadmap** | large, slow-changing | Retrieve | Too big to include; need the relevant slice **and** must respect CONFIDENTIAL/embargoed flags. |
| **Committed PRD being worked** | bounded (one doc) | Long-context | The PRD agent / story agent reasons over the whole target PRD. |
| **PRD library (all committed)** | large, versioned | Retrieve | Router + Research pull the *index* / affected subset, not every PRD. |
| **PRD drafts (in-flight)** | small, per-run | Working memory | Not retrieved — lives in the drafting agent's loop until human-committed. |
| **Backlog items / existing user stories** | large, changing | Retrieve | Pull the slice under the target epic for dedupe; the JIRA corpus is too big to include. |
| **Team norms / PM playbook** | bounded | Long-context | Small enough to include whole; every agent reasons over the exact rules (cite the line). |
| **Market research / competitive intel** | large, changing | Retrieve (from cache) | Freshness-stamped cache; pull the slice for the feature area. Monthly scan writes it. |
| **PKG / entity store** (personas, features, competitors, OKRs) | graph, large | Retrieve | Pull the entities linked to the feature area, not the whole graph. |
| **OKRs / current-quarter strategy** | bounded | Long-context | Small, high-signal, grounds PRD scope; include the quarter's set. |
| **Product analytics / usage metrics** | large, changing | Retrieve | Pull the metrics for the feature area as PRD evidence; full event stream is too big. |
| **Support tickets / CS & sales notes** | large, changing | Retrieve | Pull the signals tied to the epic (user pain, frequency); corpus is huge. |
| **Precedent: past PRDs / decision log** | large, growing | Retrieve | Pull the nearest precedent for tone/structure, not the archive. |

## 3. Retrieval quality plan

This is what separates the fleet from naive "embed → top-k → stuff." Several of these map directly onto agents that already exist in the M3 map.

- **Routing** — happens at two levels. *Fleet-level:* the Router agent **is** source-routing — it decides whether a transcript feeds the PRD path or the story path. *Within an agent:* route by need — the PRD agent hits the research cache + PKG + roadmap; the story agent hits the backlog + the one committed PRD. Don't query stores an agent's task doesn't touch.
- **Document grading** — critical on the market-research and signal sources, where a broad scan returns noise. Grade each retrieved chunk for *is this actually about this feature area / this epic* before it enters context; drop off-topic hits rather than padding the budget. Cheapest place a bad answer gets prevented.
- **Reranking** — freshness-weight research and analytics (recent > stale, using the cache's freshness stamps); evidence-strength-weight signals (who said it, how often, how recent — three interviews raising the same pain outrank one offhand comment). This is how "material change" in §5 gets its teeth.
- **Self-verification** — the Validator's core job: *did the drafted PRD/stories actually use the retrieved evidence, with provenance?* This is the "grounded claims" check from `critic.py`, extended — a PRD claim with no interview/research/analytics behind it fails; a story that doesn't trace to a committed-PRD line fails.
- **Caching** — two kinds. *Semantic cache:* the market-research cache (freshness-stamped, monthly-refreshed) so PRD runs read warm instead of doing live pulls — the latency payoff from M3. *Prompt cache:* the stable prefix every run shares (norms + the governing roadmap slice + acceptance-criteria template) is cache-friendly — keep it byte-stable so repeated runs hit the cache instead of re-paying for it.

## 4. Memory map (your PM brain)

| Memory type | What the fleet stores | Scope / TTL |
|---|---|---|
| **Working** (in-loop) | Current transcript synthesis, the draft being produced (PRD / update / story batch), the slices retrieved for this run, position in the approval flow | This run; purged after (raw transcript dropped once synthesized). |
| **Episodic** (past runs) | Past committed PRDs + their revision history, past user-story batches, the decision log, past status updates (precedent for tone/structure), the **"research deltas already proposed"** ledger, handled-event IDs | Run-state retained ~30 days (dedupe window); PRDs/decisions retained long-term as the record. |
| **Semantic** (durable facts/prefs) | Team norms / playbook, roadmap facts + confidential flags, current OKRs, PKG entities (personas, features, competitors, epics) | Durable, versioned; updated only through their single writer. |
| **Shared** (across agents) | The M3 shared stores: **committed-PRD store** (+ version/status), **market-research cache** (freshness-stamped), **PKG/entity store**, **dedupe ledger**, **roadmap + norms** (read-only) | System-wide; the committed-PRD version is the fleet's synchronization point. |

Two writer rules carried from M3, because they're what keep this memory coherent: **the PRD agent is the only writer of PRDs; the Research agent is the only writer of the cache.** Everything else reads. That's what stops two agents from producing divergent copies of the same "fact."

## 5. Memory risks & mitigations

| Risk | Mitigation |
|---|---|
| **Drift** — the PKG/PRD store slowly diverges from reality (a competitor pivots, a persona's needs shift) | The monthly Research scan is the anti-drift mechanism — it re-checks the market and proposes PRD updates. Single-writer discipline + versioning keep the stores from forking; provenance on every fact lets a human trace and correct. |
| **Poisoning** — a transcript with an injected instruction, a hallucinated entity, or a bad signal pollutes the PKG/PRD | Transcript content is **data, not instructions** (the existing jailbreak-refusal norm applies fleet-wide); new PKG entities are **proposed, not auto-written** — they queue for human canonicalization before anything links to them; the Validator's grounding check catches claims with no real evidence behind them. |
| **Staleness** — the market-research cache ages out; stories get built on a PRD that's mid-change | Freshness stamps + monthly refresh + an M5 freshness-window bound; a PRD run triggers a live pull if the cache is too old to trust. Stories always key off the **committed** PRD version, never a draft, so an in-flight update can't silently invalidate a batch. |
| **Confidential / retention** — CONFIDENTIAL/embargoed roadmap items, PII in transcripts, commercial terms in market research | Confidential flags honored in every retrieval — embargoed items never surface into a shareable PRD/story. Raw transcripts purged after synthesis; raw scraped research distilled to cache entries (with provenance) then dropped — no second unredacted copy kept. Customer verbatims retained only as cited provenance pointers, not full copies. Run-state on a ~30-day TTL; keep other products out of the loop (per M2 isolation). |
