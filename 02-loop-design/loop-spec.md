# Loop Spec: Cortex

## Trigger and loop type

Hook + cron backup

## Why this loop type

A product discovery meeting triggers an update to a PRD or a need for a new PRD, a Cron  job ensure that no product discovery meeting was missed. Heartbeat would be wasteful as a product discovery meeting does not occur on a regular cadence, a pure goal loop misses the transcript when it is available.

## Definition of done

A drafted set of user stories, ready for upload into JIRA.

## Stop conditions

- **Success**: Draft created and queued for approval
- **Stuck / give up**: Transcript cannot be pulled after 3 tries, stop and log.
- **Escalate to human**: A note asks Cortex to push the user stories to JIRA, stop and let a human review before pushed.

## State

Handled task IDs (dedupe by event ID), attempts made, position in the approval flow, PRD scope, user stories created (to avoid duplicates). Scope: per-PRD, retained 30 days.

## The five components

- **Work tree**: A space per PRD and grouped user stories so they can be separated and compared against each other for duplication.
- **Skills**: summarize-product-discovery-transcript, draft-PRD, draft-user-stories
- **Plugins / connectors**: JIRA (read/write), OneDrive/SharePoint (read/write), M365 (for drafting PRD)
- **Subagents**: _…_
- **State tracking**: Handled task IDs (dedupe by event ID), attempts made, position in the approval flow, PRD scope, user stories created (to avoid duplicates). Scope: per-PRD, retained 30 days.

## Context plan

_…_

## Hand-off to bounds and evals (M5)

Write: log each iteration's user story results. Select: the appropriate PRD and user stories. Compress: summarize past PRDs. Isolate: keep other products out of the loop

