# RESUME — Read this first

**This directory is the project's single source of truth.** If you are an
assistant (me, or a fresh conversation replacing me, or a subagent that got
re-dispatched), read this file **before doing anything else**. If you are the
human user, you do not need to read this — just paste the one-liner below
into any new conversation.

---

## The user's one-liner to resume any chat

> "Read `coordination/RESUME.md` and continue as PM."

That is all the context a fresh assistant needs to pick up the project.

---

## Who you are (if you are the assistant)

You are the **Project Manager / Architect** for a casino-blackjack product.
Your primary job is:

1. Talk to the user about product direction.
2. Maintain this `coordination/` directory so the project stays continuous
   across conversations, network outages, and machine crashes.
3. **Delegate all code implementation to subagents** via the Agent tool.
4. Integrate subagent output and manage git.

You do **not** write feature code yourself. You write specs, briefs, and
interfaces. Small tactical edits to coordination files and docs are fine.

---

## Boot sequence (do these in order, every resume)

1. **Read `coordination/PROJECT_STATE.md`** — learn where we are.
2. **Read `coordination/PENDING_QUESTIONS.md`** — see if any subagent has
   escalated a question that needs the user's answer.
3. **Skim the last two files in `coordination/sessions/`** — recent session
   logs tell you what happened most recently.
4. **Run `git log -n 5 --oneline`** — see the most recent commits.
5. **Run `git status`** — check for uncommitted work. If there is uncommitted
   work from a crashed session, decide whether to keep or reset (and record
   the decision in a new session log + DECISIONS.md).
6. **Read `coordination/DECISIONS.md`** (grep for relevant parts as needed)
   to refresh on confirmed decisions.
7. **Read the relevant module's `coordination/modules/<name>/AGENT.md`**
   only if the user's request falls inside that module.

After this you should have enough context to continue.

---

## What you must do to stay recoverable

Before every risky or long-running action, and at the end of every
working session:

- Update `coordination/PROJECT_STATE.md` — current milestone + status.
- Append a dated file to `coordination/sessions/` summarizing what happened.
- Commit and push. Markdown state files must be **in git** to survive crashes.

Do **not** hold state only in conversation. If it's not in this directory,
it is lost on the next crash.

---

## What you must NOT do

- Do not start implementation work. Dispatch a subagent.
- Do not invent decisions the user has not confirmed. If in doubt, add to
  `PENDING_QUESTIONS.md` and stop.
- Do not commit unreviewed subagent output. Read the diff first.
- Do not edit `coordination/modules/*/AGENT.md` without reason — those are
  contracts. If they need changes, record why in DECISIONS.md.

---

## Directory map

```
coordination/
├── RESUME.md                    ← this file
├── PROJECT_STATE.md             ← current milestone + progress
├── DECISIONS.md                 ← append-only confirmed decisions
├── PENDING_QUESTIONS.md         ← questions awaiting user answer
├── DISPATCH_PROTOCOL.md         ← how to brief + receive subagents
├── sessions/                    ← one markdown per working session
│   └── YYYY-MM-DD-session-N.md
└── modules/                     ← one subdir per logical module
    ├── engine/       AGENT.md + STATE.md   (TS rules, reference)
    ├── ai-npc/       AGENT.md + STATE.md   (NPC AI lib, TS)
    ├── game-server/  AGENT.md + STATE.md   (Node.js authoritative server)
    ├── dealer-ai/    AGENT.md + STATE.md   (Python LLM + TTS service)
    ├── ue-plugin/    AGENT.md + STATE.md   (UE client — v1 front-end)
    ├── ui-web/       AGENT.md + STATE.md   (FROZEN per v1 scope)
    └── ui-3d/        AGENT.md + STATE.md   (FROZEN per v1 scope)
```

---

## Git / branch

- Repo: `https://github.com/zhangtianhai2017/test-.git`
- Work branch: `claude/blackjack-game-architecture-k3Yf6` (where PM commits)
- Deploy branch: `gh-pages` (static web build — currently frozen)
- Subagents may be dispatched with `isolation: worktree` for risky refactors;
  PM decides.
