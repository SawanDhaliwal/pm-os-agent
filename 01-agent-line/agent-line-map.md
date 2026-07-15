# Agent Line Map: Cortex PM Chief-of-Staff Agent

> Module 1 · The Agent Line

## The workflow, decision by decision

List every discrete decision or action in your agent's workflow, then score each one and place it **above** the line (a human owns it) or **below** (the agent owns it). Borderline calls get an HITL checkpoint.

| Decision / action | Reversibility (H/M/L) | Blast radius (H/M/L) | Measurability (H/M/L) | Above / Below | HITL? |
|---|---|---|---|---|---|
| _Pull transcript from product discovery meeting_ | H | L | H | Below | · |
| _Synthesize transcript into notes for review_ | H | L | H | Below | required |
| _Draft or update an existing PRD for review_ | M | L | M | Below | required |
| _Once PRD committed, develop User Stories from the PRD_ | H | L | H | below | required |
| _Once User Stories reviewied, upload to JIRA_ | M | H | H | Above | required |
| _…_ | | | | | |

## Agent anatomy (sketch)

- **Model:** _your default fast model + when you escalate to a frontier model, and why_
- **Tools:** _project + activity lookup (read) · past-update search · roadmap · team norms · story proposal (capped) …_
- **Memory:** _what persists across runs (roadmap, decisions, norms) vs. purged_
- **Loop:** _placeholder, defined in M2 loop-spec.md_
- **Bounds:** _placeholder, defined in M5 bounds-and-evals.md_
- **Evals:** _placeholder, defined in M5 bounds-and-evals.md_

## The golden rule, applied

_One sentence per above-the-line decision: why it stays human (which of reversibility / blast radius / measurability failed)._

## Hardest call

_Your toughest "above vs below" decision and how you resolved it. (Share this in `#cohort-channel`.)_
