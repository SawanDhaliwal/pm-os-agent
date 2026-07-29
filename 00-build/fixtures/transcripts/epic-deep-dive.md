# Product working session — Northstar onboarding
Date: 2026-07-21 · Attendees: PM (you), Eng lead (Dara), Design (Wren), Support lead (Ines)

**Dara:** We shipped the checklist and the step-completion events last sprint, so we
finally have data. The drop-off is concentrated in one place: people land on an empty
project and just… stop.

**Ines:** Support sees the same thing. The top ticket theme this month is "I signed up,
now what." Fourteen tickets in three weeks, all the same shape.

**Wren:** So we're talking about the empty-state guidance work. That's already in the
PRD — the third epic, I think. We don't need to change scope, we just need to actually
break it down and build it.

**PM:** Right, this is EPIC-ONBOARD-03. Let's dig into what it actually needs.

**Wren:** Three things, concretely. First, the empty project view needs a real starting
state — a sample project the user can poke at, not a blank canvas. Second, contextual
tips that appear at the point of confusion rather than a tour up front; the tour data
says people skip it. Third, we need the tips to be dismissible and to not come back
once dismissed, because that was the loudest complaint about the old tooltips.

**Dara:** Add instrumentation on tip dismissal too, otherwise we're guessing again.

**Ines:** One more from support: when someone dismisses everything and is still stuck,
there should be an obvious way to get help that isn't "open a ticket."

**PM:** Good. That's enough to write stories against. Nothing here changes the PRD
itself — the scope was already agreed, we're just decomposing the epic.

**Dara:** Agreed. No scope change needed.
