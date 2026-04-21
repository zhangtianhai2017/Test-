# PROJECT_STATE

> Updated by PM at every major state transition. Never read this file for
> historical detail — use `sessions/` or `git log` for that. This file is a
> **snapshot of now**.

## One-line summary

Casino blackjack product with a C++/Unreal-Engine front-end as the primary
experience, driven by a TS reference rules engine, a Python AI dealer service
(LLM + TTS), and a suite of psychological / NPC mechanics inspired by real
casino play and classic gambling films.

## v1 scope (frozen 2026-04-21 — see `DECISIONS.md` D-004)

**Active**:
- `engine` — TS rules, authoritative reference
- `ai-npc` — basic strategy + Hi-Lo + 7 personalities + tilt
- `dealer-ai` — Python FastAPI service (LLM + CosyVoice TTS)
- `ue-plugin` — **primary front-end**. C++ BlackjackCore + BlackjackUE
  (actors, components, gestures, heat, morale, tells, bluff)

**Frozen until v1.5** (no new features, bug-fix only):
- `ui-web` (2D) — current gh-pages deployment preserved
- `ui-3d` (Three.js) — current gh-pages deployment preserved

**Explicitly not in v1** (see `docs/FUTURE_FEATURES.md`):
- F1–F9 backlog (team play, rigged dealer, comps, focus mode, etc.)

## Current milestone

**M1 — engine multi-seat refactor (TS side, reference)**
Status: Not started. Being dispatched to a subagent this session.

## Milestone list (order)

1. M1 — TS engine multi-seat refactor (`engine`)
2. M2 — NPC AI core: basic strategy + Hi-Lo + bet policies (`ai-npc`) — TS first
3. M3 — C++ BlackjackCore sync to multi-seat + NPC AI (`ue-plugin/BlackjackCore`)
4. M4 — UE scene: seats, pit boss, CCTV, dealer character (`ue-plugin/BlackjackUE`)
5. M5 — UE psychological systems: heat, morale, timer, gestures (`ue-plugin/BlackjackUE`)
6. M6 — UE perception/tell/bluff (`ue-plugin/BlackjackUE` + `ai-npc`)
7. M7 — dealer-ai service extended events (`dealer-ai`)
8. M8 — CosyVoice TTS integration (`dealer-ai`)
9. M9 — UE dealer-ai HTTP client + audio playback (`ue-plugin/BlackjackUE`)
10. M10 — NPC tilt + dealer-state evolution (`ai-npc` + `dealer-ai`)
11. M11 — Conformance vectors extended (`engine` + `ue-plugin`)
12. M12 — Windows installer + integration testing (`dealer-ai` + `ue-plugin`)

## Active subagent tasks

(none right now — will be filled in when M1 is dispatched)

## Blockers

None.

## Open questions awaiting user

See `PENDING_QUESTIONS.md`. Currently: 0.
