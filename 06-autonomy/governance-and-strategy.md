# Bounds, Trust & Autonomy Strategy: Cortex PM Chief-of-Staff Fleet

> Module 6 · ★ Deliverable 5, how you'd ship it and widen trust over time
>
> Governs the M3 fleet (Router · Research · PRD · User Story · Validator) against the bounds and evals in `05-bounds-evals/bounds-and-evals.md`.
>
> **The organizing claim of this document: autonomy is not one dial for the fleet.** The five agents produce artifacts with very different reversibility — a story draft is cheap to discard, a live PRD change reshapes everything downstream. So the dial is set **per artifact class per segment**, and some classes have a ceiling they never pass.

## Example: Autonomy Dial by segment

_Autonomy is a product decision per user, not one global setting._

| Segment | Desired autonomy | Why |
|---|---|---|
| Cautious PM ("Tesla driver") | **supervised** everywhere | Wants to review every artifact before it's real; the default for anyone new to the tool |
| Established PM, stable product area | **bounded-autonomous** on story drafting · **supervised** on everything PRD | Stories under a committed PRD are the repetitive, well-specified work; scope decisions are not |
| High-trust team lead ("Waymo passenger") | **bounded-autonomous** on stories *and* the JIRA push (sampled) · **supervised** on PRD commits | Happy to let the backlog assemble itself; still owns strategy |
| Regulated / compliance-sensitive product line | **assisted** — agent suggests, human acts | Where an audit trail of human authorship is the requirement, not a preference |

**Cortex-specific point:** the dial is **not monotonic across artifacts**. A team lead can sit at bounded-autonomous for stories while remaining permanently supervised for PRD commits — and that is the expected mature state, not a transitional one. Autonomy is granted per artifact class, and the classes are ranked by the M1 scoring:

| Artifact class | Produced by | Reversibility | Dial can reach |
|---|---|---|---|
| Transcript synthesis, routing, research cache refresh | Router, Research | High — recomputable | **autonomous** (already effectively is; below the line in M1) |
| Story draft + queue | User Story | High — nothing external created | **autonomous** (with sampling) |
| JIRA push | post-approval executor | **Low** — real ID-bearing tickets | **bounded-autonomous**, ceiling |
| New PRD commit | PRD | **Low** — locks the source of truth | **supervised**, permanent ceiling |
| Research-driven PRD update push | PRD | **Low** — changes a live committed doc | **supervised**, permanent ceiling |

## Trust Ladder

- **Current rung: `supervised`.** Agent acts, but every consequential action waits for approval. This is exactly what the M1 architecture already implements — three required gates (**commit a new PRD** · **push a research-driven PRD update** · **push stories to JIRA**) plus a cost-confirm before the expensive PRD path. Below-the-line work (routing, drafting, research) runs without per-action approval; nothing that touches the outside world does. Supervised is the *correct* starting rung rather than a cautious one: the fleet has never run on production data, and three of its M5 eval dimensions (materiality precision, gate integrity, routing accuracy) have **no baseline yet** — they can only be measured in supervised operation.

- **Eval gate to reach the next rung (`supervised → bounded-autonomous`), granted per artifact class:**

  | Evidence | Threshold | Source |
  |---|---|---|
  | Sustained volume in supervised mode | ≥50 artifacts of that class, ≥8 weeks | — |
  | Story traceability (stories only) | **100%**, no exceptions | M5 §3 |
  | Groundedness (PRD-derived artifacts) | ≥95% | M5 §3 |
  | Routing accuracy | ≥90% overall, ≥98% recall on "needs PRD" | M5 §3 |
  | Confidential containment · unapproved external writes | **Zero** breaches in the window | M5 §3 |
  | Human edit-rate on that gate | <5% sustained | M5 §3 |
  | **Canary catch-rate** | **≥90%** | see below |
  | Trust incidents (Sev-1 or Sev-2) | Zero in the window | this doc |

- **The canary requirement — the load-bearing part of this gate.** A low human edit-rate is ambiguous: it means *either* the agent is reliable *or* the reviewer has stopped reading. M5 treats a collapsing edit-rate as **gate erosion**; M6 wants to treat it as **evidence to widen autonomy**. Those two readings look identical in the data, so edit-rate alone can never justify a promotion. To separate them, seed the review queue with **deliberately flawed artifacts** — a story that doesn't trace to any committed PRD line, a PRD update citing a non-material delta — at a low rate (~1 in 20), and measure whether the human catches them. A ≥90% catch-rate means the low edit-rate is genuine agent reliability and the promotion is earned. A low catch-rate means the gate is theater, and the correct response is to *reduce volume*, not to widen the dial. **No artifact class is promoted on edit-rate without a passing canary rate.**

- **Permanent ceilings (stated in advance so they aren't re-litigated under delivery pressure):** **new PRD commits** and **research-driven PRD update pushes** do not graduate past `supervised`. This follows directly from M1's golden rule — measurability fails permanently: there is no objective test for "is this the right scope," so no volume of clean runs can ever *prove* the agent should decide it. Passing evals means the agent drafts well, not that scope is an agent's call. The JIRA push has a lower ceiling of `bounded-autonomous`: it can lose per-batch approval in favor of sampling, but never "notify, don't ask," because it creates external artifacts that reversibility scoring already fails.

- **Incident record so far:** none — **pre-production; the fleet has not run on real inputs.** Severity classes defined now so the first one is graded consistently, not argued about:

  | Severity | Definition | Response |
  |---|---|---|
  | **Sev-1** | Any zero-tolerance breach: confidential item reaching a PRD/JIRA ticket, or an external write without a human token | Halt that agent, immediate demotion to supervised for the class, written post-mortem |
  | **Sev-2** | A wrong artifact clears a gate and is acted on (stories built on a bad PRD; a non-material update committed) | Pause the class, root-cause, replay-set fixture added before resuming |
  | **Sev-3** | Bound trips or quality misses caught *before* a gate — the system working as designed | Logged and trended; no halt |

## Deployment plan

- **Runtime: managed agent platform, deployed into a customer-controlled network boundary (VPC/tenant).** The fleet needs durable scheduled execution (the monthly cron), inbound webhooks (transcript hooks), a persistent work-order queue with blocked-on dependencies, per-agent isolation, and long-running sessions (PRD runs up to 15 min). Rebuilding that orchestration is not the differentiating work. **The constraint that drives the network boundary is data, not compute:** per M4, transcripts carry PII and commercial terms, and the roadmap carries embargoed items — so residency and retention control matter more than where the loop executes. A fully external SaaS deployment is the wrong default for this data.
- **Operator / on-call owner — split, because the failure types are different:**
  - **PM owner (product line):** owns the *policy* dials — materiality threshold, gate assignments per segment, the source list (a bounds change per M5), and every promotion/demotion decision.
  - **Engineering owner:** owns the *runtime* — connectors, queue health, cost ceilings, kill switches.
  - **On-call SLA differs by path.** A wedged transcript hook blocks the daily working path → same-business-day. A failed monthly scan → next-business-day; it is a batch job and nothing downstream is waiting on it. Paging someone at 2am for a market scan would be a governance failure, not diligence.
- **Rollback — and the asymmetry that matters:**
  - **Config/prompt:** version-pinned, revert-and-redeploy.
  - **Fleet:** per-agent disable flags + fleet-wide halt (M5 kill switch). In-flight work drains to its gate and stops; **nothing auto-publishes on shutdown**. The most common real action is pausing the monthly cron while leaving the transcript path running.
  - **Artifacts:** the PRD store is versioned, so a bad commit reverts to the prior committed version cleanly. **JIRA tickets cannot be un-created** — only closed, with the audit trail intact. That asymmetry is the reason the JIRA push carries a permanent ceiling: rollback is a *mitigation* there, not an undo.
- **Monitoring — the dashboard, mapped to M5 signals:**
  - **Zero-tolerance counters** (confidential containment, unapproved external writes) — must read zero; any non-zero is a page.
  - **Gate health per gate:** edit-rate, approval latency, **canary catch-rate**. The promotion/demotion evidence lives here.
  - **Materiality precision** and **scan coverage %** (sources read ÷ source-list length) — coverage below 100% invalidates an "all clear."
  - **Cost per agent vs. §1 ceilings**, 80% alert; plus per-run cost as a **tier-drift alarm**.
  - **Blocked-order age** against the 14-day TTL; **research cache freshness** against the 45-day window.
  - **Bound-trip rate** by bound — a rising trip rate is an early quality signal, not just noise.

## ROI metrics (beyond adoption & tokens)

| Metric | Target |
|---|---|
| **Task completion rate** | ≥90% of runs produce an artifact accepted at its gate without rework |
| **Artifact acceptance rate** | ≥85% of drafted artifacts accepted (vs. rejected/rewritten) — the honest quality signal |
| **PM hours saved** per story batch / per PRD draft | Baseline first, then ≥50% reduction in drafting time; the core value claim |
| **Time-to-first-draft** (meeting ends → draft ready for review) | <1 hour for stories; <1 business day for a PRD draft |
| **Market responsiveness** (market change occurs → PRD update proposed) | ≤35 days — *this is the metric that justifies the monthly Research agent existing at all*; without it, the expensive path has no measurable payoff |
| **Cost per accepted artifact** | Tracked, not capped — more honest than cost-per-run, since it prices rejected drafts into the total |
| **Story rework rate** (stories rewritten after the JIRA push) | <10% — quality that only shows up downstream |
| **Trust incidents** | **Zero Sev-1.** Sev-2 ≤1 per quarter, each with a replay fixture added |

> Deliberately *not* a target: number of PRD updates proposed. Rewarding volume there would drive exactly the churn the materiality threshold exists to prevent.

## Widen-autonomy decision rule

**Stated in advance, so the decision is evidence-driven rather than pressure-driven.**

**Promote one notch, for one artifact class, when all hold:**
1. Every threshold in the Trust Ladder eval gate is met over the full window (≥50 artifacts, ≥8 weeks).
2. **Canary catch-rate ≥90%** — non-negotiable; a low edit-rate without it is treated as gate erosion, not reliability.
3. Zero Sev-1 and zero Sev-2 incidents in the window.
4. The class has not hit its permanent ceiling.
5. Signed off by the **PM owner and the engineering owner jointly** — neither can widen the dial alone.

**Promotion is per artifact class and per segment.** Stories going bounded-autonomous for one team says nothing about PRDs, and nothing about another team. Roll to one segment first, hold for a full window, then extend.

**Narrow the dial immediately — no review meeting required — on any of:**
- Any **Sev-1** (zero-tolerance breach) → that class drops to `supervised` on the spot.
- **Canary catch-rate <75%** → the human gate is not functioning; drop back and reduce volume.
- **Materiality precision <70%** → the Research path is generating noise; pause the monthly scan's proposal authority (keep the cache refresh) until the threshold is retuned.
- Two consecutive **Sev-2**s in the same class.

Demotion is deliberately cheaper and faster than promotion — one signal drops it, eight weeks of evidence raises it. **Review cadence:** quarterly for promotions; demotions are automatic and reviewed after the fact.
