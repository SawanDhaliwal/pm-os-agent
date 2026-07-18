# Agent Line Map: Cortex PM Chief-of-Staff Agent

> Module 1 · The Agent Line

## The workflow, decision by decision

List every discrete decision or action in your agent's workflow, then score each one and place it **above** the line (a human owns it) or **below** (the agent owns it). Borderline calls get an HITL checkpoint.

| Decision / action | Reversibility (H/M/L) | Blast radius (H/M/L) | Measurability (H/M/L) | Above / Below | HITL? | Justification |
|---|---|---|---|---|---|---|
| _Pull transcript from product discovery meeting_ | H | L | H | Below | · | Easy to pull transcript, no work being done |
| _Synthesize transcript into notes for review_ | H | L | H | Below | . | Allow it to run, get the trace |
| _Draft or update an existing PRD for review_ | M | L | M | Below | . | Allow it to run, get the trace |
| _Once PRD committed, develop User Stories from the PRD_ | H | L | H | Below | . | Allow it to run, get the trace |
| _Once User Stories reviewied, upload to JIRA_ | M | H | H | Above | required | Final check before user stories committed |

## Agent anatomy (sketch)

- **Model:** one fast/cheap default (`claude-haiku-4-5`, matching `CORTEX_MODEL`) for all four below-the-line skills — `summarize-product-discovery-transcript`, `draft-PRD`, `draft-user-stories` — since the design already puts a full human review in front of the one thing that matters (the JIRA push), a per-row escalation ladder isn't buying much yet. Revisit this if the JIRA-push review starts rejecting batches often: at that point, escalate `draft-PRD` and `draft-user-stories` specifically to a frontier model, since those two are the artifacts actually under review, not the transcript pull or the notes synthesis.
- **Tools:** named to match the skills in `loop-spec.md` so the two docs stay in sync.
  - `summarize-product-discovery-transcript` — read tool, pulls the meeting transcript (the hook trigger) and produces synthesized notes.
  - `draft-PRD` — drafts or updates a PRD from those notes, grounded against `get_roadmap` / `get_norms` (reused from `tools.py`) so scope and confidentiality checks aren't re-invented here.
  - `draft-user-stories` — decomposes a committed PRD into user stories.
  - **Connector nuance worth flagging:** `loop-spec.md` lists JIRA as `read/write`, but "the connector supports writes" is not the same as "the agent's autonomous loop may call the write." The tool exposed to Cortex for the JIRA step should be a queue/propose action (mirrors `propose_stories`'s "creates nothing, queues a request" pattern) — the actual `jira.create_issue` call only fires after the row-5 human review passes, never inside the model's own tool-calling loop.
  - OneDrive/SharePoint, M365 — read/write, for pulling and drafting the PRD document itself per `loop-spec.md`.
- **Memory:** `loop-spec.md`'s State section already answers most of this — handled task IDs (dedupe by event ID), attempts made, position in the approval flow, PRD scope, and user stories created, scoped per-PRD and retained 30 days. That retention window is what the hook+cron backup design depends on: the cron leg needs to know what it already handled to avoid re-drafting a PRD or re-generating a duplicate story batch on retry. What does *not* need to persist past the run that produced it: the raw transcript text itself — once `summarize-product-discovery-transcript` has produced notes, the transcript isn't needed again, only the synthesized output and the dedupe/state fields above.
- **Loop:** _placeholder, defined in M2 loop-spec.md_
- **Bounds:** _placeholder, defined in M5 bounds-and-evals.md_
- **Evals:** _placeholder, defined in M5 bounds-and-evals.md_

## The golden rule, applied

_One sentence per above-the-line decision: why it stays human (which of reversibility / blast radius / measurability failed)._

- **Upload to JIRA:** Blast radius fails — pushing creates real, ID-bearing tickets that fire notifications and enter sprint planning, so even though the batch itself is easy to *measure* (read the stories, check they trace to the PRD), the consequence of a wrong push isn't something a rule can catch after the fact. Reversibility is scored M rather than L because nothing is externally visible until this step fires — which is exactly why it's the one row worth gating hard.

## Hardest call

_Your toughest "above vs below" decision and how you resolved it. (Share this in `#cohort-channel`.)_

The hardest call was whether "Draft or update an existing PRD for review" needed its own HITL checkpoint, given its own name says "for review." Scoring it Below with no required check means Cortex can draft a PRD *and* immediately generate user stories from it in the same run, with no human touching either artifact until the JIRA-push gate. I resolved it by trusting the loop's own definition of done — "a drafted set of user stories, ready for upload into JIRA" — and its single escalate condition (stop and let a human review before pushing to JIRA): one downstream gate that reviews the PRD and the stories together is simpler than two separate approval points, and it matches the "get the trace, don't gate every step" justification already used for the other Below rows. The tradeoff: if the PRD itself goes sideways, that only surfaces at the very end, right before JIRA — worth revisiting if that turns out to waste more review time than a mid-pipeline PRD checkpoint would have saved.
