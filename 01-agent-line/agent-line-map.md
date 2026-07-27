# Agent Line Map: Cortex PM Chief-of-Staff Fleet

> Module 1 · The Agent Line
>
> Reconciled with the M3 fleet in `03-orchestration/orchestration-map.md`: **Ingestion+Router**, **PRD agent**, **Research agent** (monthly + on-demand), **User Story agent**, **Validator**. The single-Cortex version had one above-the-line gate (the JIRA push); the fleet has **three** — more agents mean more surface where autonomous work could go wrong, so more explicit lines.

## The workflow, decision by decision

List every discrete decision or action in your agent's workflow, then score each one and place it **above** the line (a human owns it) or **below** (the agent owns it). Borderline calls get an HITL checkpoint. The `Agent` column names which fleet member owns the decision.

| Agent | Decision / action | Rev. | Blast | Meas. | Above / Below | HITL? | Justification |
|---|---|---|---|---|---|---|---|
| Router | Ingest + synthesize transcript into structured signals | H | L | H | Below | · | Read + summarize; no artifact committed |
| Router | Dedupe against handled event IDs | H | L | H | Below | · | Deterministic; stops the cron leg re-processing a meeting the hook handled |
| Router | Classify intent (PRD? · stories? · both? · neither?) | H | M | M | Below | spot-check | A misroute is recoverable but sends work down the wrong path; sample it, and route ambiguous cases to the PRD path (conservative) |
| Router | Trigger the **expensive** PRD path on a "significant change" | M | M | L | Below | **confirm (cost gate)** | Cheap human confirm before burning the frontier research/PRD pipeline on a false positive (orchestration §7) |
| Router | Sequence dependent work (hold stories blocked-on an in-flight PRD) | H | M | H | Below | · | Deterministic ordering rule; prevents stories built on a PRD that's changing |
| Research | Refresh market-research cache (monthly scan or on-demand pull) | H | L | M | Below | · | Read + distill; the cache is re-derivable and freshness-stamped |
| Research | Detect a **material** market change | H | M | L | Below | spot-check | Judgment call; the Validator materiality-checks it before it can churn a PRD |
| Research | Propose PRD updates to the affected PRDs | H | M | M | Below | · | Proposes *what* changed + *which* PRDs only — the PRD agent authors, a human commits; never edits PRD text itself |
| PRD | Pull research + synthesize interviews into a PRD draft/update | M | M | M | Below | spot-check | Draft only; blocks and **escalates** if required research is missing/stale rather than authoring on thin evidence |
| PRD | **Commit / finalize a new PRD** | L | H | L | **Above** | **required** | Locks the source of truth every downstream story inherits |
| PRD | **Push a research-driven PRD update live** | L | H | L | **Above** | **required** | Silently changing a live committed PRD reshapes in-flight and future work; human review before the final push |
| User Story | Decompose a committed-PRD epic into stories + dedupe vs. backlog | H | L | H | Below | spot-check | Drafts against a *pinned committed* version; deduped and capped |
| User Story | Propose / queue the story batch (capped) | H | L | H | Below | · | Queues a request, creates nothing (the `propose_stories` pattern) |
| User Story | **Push approved stories to JIRA** | L | H | H | **Above** | **required** | Creates real, ID-bearing tickets that fire notifications and enter sprint planning |
| Validator | Validate an artifact (PRD / update / story batch) + materiality check | H | L | H | Below | · | Independent automated gate that *feeds* the human checkpoint; never writes |
| Validator | Fail action: revise (bounded), then escalate | H | L | H | Below | · | Bounded bounce (`MAX_REVISIONS`), then hand to a human — no infinite loop |

## Agent anatomy (sketch)

- **Model:** per-agent tiering, matching orchestration §7 — the split exists so the expensive tier runs rarely.
  - **Fast/cheap (`claude-haiku-4-5`):** Router and User Story agent — high-frequency, narrow context, cheap to re-run and spot-check.
  - **Frontier (`claude-sonnet-5`+):** PRD agent and Research agent — rare, high-stakes, wide context; a weak PRD draft or a missed market shift costs far more than the token savings.
  - **Validator:** matches the artifact under review — cheap for a story batch, frontier for a PRD.
- **Tools:** each agent gets only what its rows need; the "queue/propose, never autonomous external write" rule from `00-build/tools.py` holds fleet-wide.
  - **Router:** transcript pull + synthesize, dedupe ledger, committed-PRD *index*, and a classify/dispatch action that emits work orders onto the shared queue.
  - **Research:** market/web + competitive-intel connectors, cache read/write (its single-writer store), committed-PRD index (to map changes onto PRDs).
  - **PRD agent:** research-cache read, roadmap/norms/OKRs/PKG read, PRD authoring via OneDrive/SharePoint/M365, and a **propose-commit** action (queues the draft; the commit itself is the human gate).
  - **User Story agent:** committed-PRD read, backlog read (JIRA read), `propose_stories` (capped, queued) — the JIRA *write* fires only after the human gate, never inside the loop.
  - **Validator:** reads the draft + the exact source data the drafting agent used; returns pass/fail + reasons. No write access to anything.
- **Memory:** designed in `04-memory-context/memory-and-context.md` — **shared stores** (committed-PRD store with version/status, freshness-stamped market-research cache, PKG/entity store, dedupe ledger, read-only roadmap+norms) **plus** each agent's per-run working context. Two single-writer rules keep it coherent: the **PRD agent is the only writer of PRDs**, the **Research agent is the only writer of the cache**. The committed-PRD version is the fleet's synchronization point (stories key off it, never a draft).
- **Loop:** now defined across M2 + M3 — the transcript path is hook + cron backup (`02-loop-design/loop-spec.md`); the Research agent adds a **monthly scheduled** loop; agents coordinate through an event/work-order queue rather than one linear loop.
- **Bounds:** _M5 — but per-agent: tight caps on the Router/story path, a looser cap on the PRD path, a fixed monthly budget on the Research scan (orchestration §7)._
- **Evals:** _M5 — routing accuracy, PRD groundedness, story traceability, and materiality precision on the monthly scan._

## The golden rule, applied

_One sentence per above-the-line decision: why it stays human (which of reversibility / blast radius / measurability failed)._

- **Commit a new PRD:** Measurability and blast radius both fail — there's no objective test for "is this the right scope," and every downstream story inherits whatever gets locked, so a bad commit compounds across everything the fleet produces after it.
- **Push a research-driven PRD update live:** Blast radius fails — this is an agent *proactively* changing a committed strategic doc that nobody asked to change; a market signal is not self-evidently worth a rewrite, and the consequence lands on in-flight and future work no rule can catch after the fact.
- **Push approved stories to JIRA:** Reversibility and blast radius fail — real, ID-bearing tickets fire notifications and enter sprint planning the moment they exist; nothing is externally visible until this step, which is exactly why it's gated hard.
- **(Cost gate, not an ownership transfer)** the Router's "confirm before triggering the expensive PRD path" is a checkpoint that protects the budget against a false-positive trigger, not a decision a human *owns* — the human is confirming spend, not authoring the artifact.

## Hardest call

_Your toughest "above vs below" decision and how you resolved it. (Share this in `#cohort-channel`.)_

In the single-agent version the hardest call was whether the PRD *draft* needed its own checkpoint. The fleet introduces a genuinely harder one: the **Research agent's monthly scan can originate a change to a live committed PRD with no human and no transcript prompting it.** That's new — every other action in the system starts from something a human did (a meeting, a request); this one starts from the market moving on its own. Scoring the *proposal* Below feels right (it's just a flagged delta, creates nothing), but the same autonomous origination that makes the fleet agile is also what makes it dangerous: an over-eager scan could quietly rewrite strategy on noise. I resolved it by splitting the monthly path into three scored steps — **propose** (Research, Below), **author** (PRD agent, Below, single-writer so no divergent copies), and **push** (Above, required human review) — with the Validator's *materiality check* sitting in between as an automated gate that fails a non-material or single-data-point "change" before it ever reaches the human. So the agility is preserved (the scan runs autonomously and surfaces real shifts continuously), but proactively-originated change to a committed doc has to clear *both* an automated materiality bar and a human before it's real. The tradeoff worth watching: if the materiality check is too loose it generates human-review fatigue and people rubber-stamp; too tight and the fleet stops being agile — that threshold is the knob to tune in M5.
