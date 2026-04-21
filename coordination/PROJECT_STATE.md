# PROJECT_STATE

> Updated by PM at every major state transition. Never read this file for
> historical detail — use `sessions/` or `git log` for that. This file is a
> **snapshot of now**.

## One-line summary

**v1 COMPLETE (2026-04-21).** All 13 milestones shipped. A multi-player
networked casino blackjack product with authoritative game server, native
UE 5 client, bilingual conversational AI dealer (local LLM + GPU TTS), and
full psychological-layer mechanics (heat / morale / bluff / tells). Ready
for Windows integration testing per `docs/DEPLOY_V1.md`.

## v1 scope (per DECISIONS.md D-004, D-016..D-022)

**Active & done**:
- `engine` — TS rules, multi-seat, 57 tests
- `ai-npc` — basic strategy + Hi-Lo + bet policies + 7 personalities +
  tilt + tells. 93 tests
- `game-server` — Node.js authoritative WebSocket server. Lobby, seat
  claiming, full game loop with NPC auto-drive. 64 tests
- `dealer-ai` — Python FastAPI. LLM quips via llama.cpp, TTS via
  CosyVoice 2, session-based dealer-state evolution. 17 tests
- `ue-plugin/BlackjackUE` — 12+ new C++ classes. UBlackjackNetClient
  (WebSocket, 21 server-frame delegates), ABlackjackNetTableActor
  (scene driver), UBlackjackAudioClient (TTS playback), heat /
  morale / pit boss / decision timer / gesture library / tell /
  trust / perception wiring.

**Frozen (bug-fix only, per D-004, D-021)**:
- `ui-web` (2D) — gh-pages deployment preserved
- `ui-3d` (Three.js) — gh-pages deployment preserved
- `ue-plugin/BlackjackCore` (C++ rules port) — demoted in v1.

**Total automated tests**: 231 (57 + 93 + 64 + 17) all green in the sandbox.

## Post-v1 validation required (user's Windows + UE machine)

- Compile the UE plugin (sandbox has no UE toolchain — all UE C++ is
  source-complete but not compile-verified here).
- Integration test via `docs/DEPLOY_V1.md`:
  - `packaging/build-all.ps1`
  - `packaging/installer/install.ps1`
  - Smoke test: /health, WS HELLO, two-client round, UE connect +
    round with dealer quip (+ audio if GPU).
- CosyVoice latency on real GPU.
- Qwen model size + latency trade-off on target hardware.

## Post-v1 backlog (see `docs/FUTURE_FEATURES.md`)

F1 team play + covert signals (MIT Blackjack Team)
F2 rigged dealer / cheating modes (Ocean's Thirteen)
F3 comps / impairment (Casino)
F4 Rain Man focus mode
F5 Mahowny compulsion mode
F6 Molly's Game VIP rooms
F7 Hard Eight mentor mode
F8 Pai Gow / mahjong sister games
F9 tournaments / seasonal events

## Current milestone

**NONE IN FLIGHT.** v1 closed. Await user validation or new direction.

## Active subagent tasks

None.

## Blockers

- None blocking v1 close.
- Pending user action: run `packaging/build-all.ps1` on a Windows box
  with a UE 5.3+ toolchain to produce shipping artifacts.

## Open questions awaiting user

See `PENDING_QUESTIONS.md`. Currently: 0 open.
