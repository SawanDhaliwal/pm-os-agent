# Cortex for Claude Code: your PM team in every repo

`00-build/` is Cortex as a **program**: Python that calls the Claude API, with bounds and human gates enforced in code.
This folder is the same team as **Claude Code configuration**: agent and skill files that Claude Code loads while you work
in any product repo (Tyche today, the next product tomorrow). Same five roles, built two ways.

## 1. The building blocks

| Piece | What it is | File | When it loads |
|---|---|---|---|
| **Agent** (subagent) | A worker with its own fresh context, its own tools and its own model | `agents/<name>.md` | When the main Claude hands it a job, or you ask for it by name |
| **Skill** | A playbook: the steps for a repeatable task | `skills/<name>/SKILL.md` | Only when its `description` matches what you ask, or you type `/<name>` |
| **CLAUDE.md** | Standing rules for one product | the product repo's root | Every session in that repo |

The reason for the split is **context**: Claude's working memory per conversation is limited. A skill costs almost nothing until
it's needed, because only its one-line description is loaded up front. An agent runs in a separate context and returns a summary,
so its digging doesn't crowd your conversation, and because it starts fresh it really hasn't seen another agent's reasoning.
That's what makes the validator independent.

## 2. How the roles map

| Cortex role (`00-build/fleet/`) | Here | Tools it gets | Model |
|---|---|---|---|
| Router (`router.py`) | `skills/pm-intake`, run by your main Claude session | whatever the session has | your session's |
| Research (`research.py`) | `agents/pm-researcher.md` | read files, web search | sonnet |
| PRD (`prd.py`) | `agents/prd-writer.md` | read and write files | opus |
| User Story (`stories.py`) | `agents/story-writer.md` | read and write files | sonnet |
| Validator (`validator.py`) | `agents/pm-validator.md` | read only | sonnet |
| Human gates (`gates.py`, `executor.py`) | `status: draft` → `approved`, changed only by you | | |

The model column is the same **tiering** idea as `config.py`: spend the strongest model where judgement matters most (the PRD),
and a cheaper one where the task is narrower.

**The important difference.** In Cortex, "a PRD needs a human's approval" is enforced in Python: no agent has a tool that can
commit. Here it's a rule in a prompt, plus the fact that the validator is read-only. A prompt rule is usually followed but not
guaranteed. When a rule must hold every time, you move it into code: in Claude Code that means a **hook** (a script that runs before
a tool call and can block it). Adding one that stops any agent from writing `status: approved` is a good later exercise.

## 3. Where things go in a product repo

The team writes into the product it's working on, so PRDs live next to the code they describe and go through pull requests:

```
<product repo>/docs/product/
  prds/<short-name>.md        written by prd-writer, status: draft until you approve
  stories/<short-name>.md     written by story-writer, only for approved PRDs
```

## 4. Install (once per Mac, and again after you edit a file here)

```bash
cd ~/pm-os-agent            # wherever you cloned this repo
./claude-team/install.sh --dry-run   # see what it would change
./claude-team/install.sh
```

It copies the agents and skills into `~/.claude/` (your **personal** level, which every repo sees).
Pieces that only make sense for one product belong in that product's own `.claude/` folder instead (the **project** level, committed
to that repo). Edit here, not in `~/.claude`, so git keeps the history, then re-run the script.

## 5. Check it works

1. Open a **new** session in a product repo: `cd ~/tyche && claude`. Agents and skills are read at startup.
2. Type `/agents`. You should see `pm-researcher`, `prd-writer`, `story-writer` and `pm-validator`.
3. **Trigger test**, without naming the skill: "Here are my notes from thinking about bill reminders: … What should we build?"
   You should see `pm-intake` load, then the agents run one after another, and it should stop at the approval gate.
4. **Non-trigger test**: "What does pipeline.py do?" No PM skill should load.
5. **Gate test**: ask for stories for the PRD while it still says `status: draft`. The story-writer should refuse.
6. If a skill misfires, fix its `description`. That one sentence is all Claude sees when deciding.

## 6. Exercises

1. Read one agent file and its Cortex twin in `00-build/fleet/prompts.py`. What did the Python version need that this doesn't, and why?
2. Run the team on a real Tyche idea. Read the PRD, edit it, and approve it yourself.
3. Change `story-writer`'s model to `haiku`, rerun, and compare the stories. That's a cost and quality trade-off you can now measure.
4. Write a skill for the PM task you repeat most each week.
