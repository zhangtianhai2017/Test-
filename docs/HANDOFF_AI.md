# AI Handoff — Blackjack Project

This is a single-page briefing for a fresh AI agent (or a fresh conversation
with the same AI) to pick up the Blackjack product from where the previous
session left off. **Paste the "Handoff prompt" block below** into the new
conversation and the assistant will boot into PM mode with full context.

---

## Handoff prompt (paste this exactly)

```
You are taking over as Project Manager for the Blackjack product.

Repo:    https://github.com/zhangtianhai2017/test-.git
Branch:  claude/blackjack-game-architecture-k3Yf6

Do these in order before replying to me:

1.  Clone (or pull) the repo and checkout the branch above.
2.  Read `coordination/RESUME.md` end to end.
3.  Read `coordination/PROJECT_STATE.md` (current snapshot).
4.  Read `coordination/PENDING_QUESTIONS.md` (should be empty).
5.  Read the last 1-2 files in `coordination/sessions/`.
6.  Run `git log -n 10 --oneline` and `git status`.
7.  Verify the canary test suites still pass:
        npm install
        npm run test --workspace=@blackjack/engine      # 57 tests
        npm run test --workspace=@blackjack/ai-npc      # 93 tests
        npm run test --workspace=@blackjack/game-server # 64 tests
        cd packages/dealer-ai && python3 -m pytest -q   # 17 tests

Report the results of step 7 back to me. Do not start implementation
work until I give you a direction.

Working method is defined in `coordination/DISPATCH_PROTOCOL.md` and
decision D-012 (PM delegates code to subagents) + D-024 (up to 3
subagents in parallel). Do not write feature code yourself; dispatch.

Module contracts live in `coordination/modules/<module>/AGENT.md`.
Locked files and non-touchable modules are listed in each AGENT.md.
```

---

## Notes for the human handing off

The above prompt is meant for a capable coding assistant (GPT-4-class or
better) with filesystem + shell + git access. If the recipient AI is
weaker or lacks tools, you'll need to run the clone + test commands
yourself and paste the outputs into the chat.

The recipient should *not* need any secrets. The repo is public. No
cloud credentials or API keys are required for the core dev work; GPU
and model downloads are only needed when actually running the Windows
build, not when iterating on code.

### Environment that the recipient AI needs

- Shell (bash or PowerShell)
- git
- Node.js ≥ 20 (for engine, ai-npc, game-server)
- Python 3.10–3.12 (for dealer-ai)
- ~2 GB disk for node_modules + Python venv
- NO GPU, NO UE toolchain, NO Windows required for normal dev;
  the UE plugin is source-only in the sandbox and compiles on
  your Windows machine

### What state the repo is in right now (snapshot)

- **v1 complete.** 231 automated tests green across 4 packages.
- **M14 complete.** UE 5.6-ready plugin + pure-C++ SampleProject
  (no Blueprint assets needed for dev flow).
- **UE plugin is source-complete but uncompiled in sandbox.** The
  first Windows validation run will likely surface real compile
  errors — fixing those is the most valuable near-term work.
- Web UIs (`ui-web`, `ui-3d`) are **frozen** per D-004, still deployed
  to GitHub Pages at `https://zhangtianhai2017.github.io/test-/`.
- Decisions log has 24 entries D-001..D-024. None open.
- No open PENDING_QUESTIONS.

### Typical next tasks the human might assign

1. **Real Windows compile** of the UE plugin (blocked on user's
   machine — AI can't do it directly, but can fix errors iteratively).
2. **Packaging dry run** — run `packaging/build-all.ps1` on the
   Windows box, see what fails.
3. **v1.5 features from `docs/FUTURE_FEATURES.md`** — F1..F9
   backlog items (team play, rigged dealer, comps, focus mode,
   compulsion mode, VIP rooms, mentor mode, sister games,
   tournaments).
4. **Bug fixes** surfaced by the Windows validation round.
5. **New content** — more personas, more rule variants, localization
   beyond zh/en.

### Working method the recipient should follow

- PM does **not** write feature code. Dispatch a subagent per
  `coordination/DISPATCH_PROTOCOL.md`.
- Up to 3 subagents in parallel, distinct files per D-024.
- Commit after every completed subtask with a message that names the
  milestone (e.g. "M14.1: xyz"). Push on every commit — this is how
  the human follows progress from their iPad.
- If a subagent hits a real product question, it writes to
  `coordination/PENDING_QUESTIONS.md` and stops. PM relays to human.
- Update `coordination/PROJECT_STATE.md` at every milestone transition.
- Append a session log to `coordination/sessions/YYYY-MM-DD-session-N.md`
  at the end of each working session.

---

## One-line test the human can run to verify handoff

After the recipient AI does step 7 above and reports "231 tests passing",
the handoff is complete and you can direct them at a new task.
