# PROJECT_STATE

> Updated by PM at every major state transition. Never read this file for
> historical detail — use `sessions/` or `git log` for that. This file is a
> **snapshot of now**.

## One-line summary

Casino blackjack product: UE 3D client(s) ↔ authoritative Node.js game
server ↔ Python AI service (LLM + CosyVoice TTS). Supports 1–6 real players
per table (multi-terminal), plus NPCs. Single-player is the same pipeline
via 127.0.0.1 loopback.

## v1 scope (frozen — see `DECISIONS.md` D-004, D-016..D-022)

**Active modules**:
- `engine` — TS rules, authoritative reference; multi-seat per D-007
- `ai-npc` — basic strategy + Hi-Lo + 7 personalities + tilt (D-008)
- `game-server` — **NEW** Node.js authoritative server with WebSocket
  protocol (D-016, D-020). Owns shoe/dealer/state. Multi-terminal
  multi-player + local loopback single-player.
- `dealer-ai` — Python FastAPI: LLM quips + CosyVoice TTS (D-006)
- `ue-plugin/BlackjackUE` — UE client actors + new `UBlackjackNetClient`
  (WebSocket). Primary v1 front-end (D-004).

**Frozen modules** (bug-fix only, no new features):
- `ui-web` (2D web) — current gh-pages deployment preserved
- `ui-3d` (Three.js web) — current gh-pages deployment preserved
- `ue-plugin/BlackjackCore` (C++ rules port) — demoted per D-021

**Explicitly not in v1** (see `docs/FUTURE_FEATURES.md`):
- F1–F9 backlog
- Account system (guest-only per D-019)
- Commercial hosting (self-hosted per D-016)

## Current milestone

**M1 — TS engine multi-seat refactor (reference)**
Status: Ready to dispatch. Will be dispatched to a subagent this session.

## Milestone list (v1, re-ordered after D-016..D-022)

**Phase 1 — TS core (server-side brain)**
1. **M1** — TS engine multi-seat refactor (`engine`)
2. **M2** — NPC AI core: basic strategy + Hi-Lo + bet policies + 7 personalities (`ai-npc`)
3. **M3** — `game-server` scaffolding + WebSocket protocol + schemas
4. **M4** — `game-server` full game loop: lobby, table, seat ownership, NPC driver, reconnect

**Phase 2 — UE client**
5. **M5** — UE `UBlackjackNetClient` (WebSocket client, replaces local BlackjackCore use)
6. **M6** — UE scene actors: 6 seats, dealer character, cards, chip stacks, NPC player models
7. **M7** — UE psychological systems: heat meter, morale bar, decision timer, gesture input
8. **M8** — UE tell/bluff/perception visuals

**Phase 3 — Dealer AI enrichment**
9. **M9** — `dealer-ai` extended events (heat/bluff/morale/dealer-state) + prompts
10. **M10** — CosyVoice TTS integration in `dealer-ai`
11. **M11** — UE audio playback (dealer TTS over WebSocket/HTTP)

**Phase 4 — Polish & ship**
12. **M12** — NPC tilt + dealer-state evolution (server-side + dealer-ai side)
13. **M13** — Windows installer + service registration + integration testing

## Active subagent tasks

(none — M1 about to be dispatched)

## Blockers

None.

## Open questions awaiting user

See `PENDING_QUESTIONS.md`. Currently: 0.
