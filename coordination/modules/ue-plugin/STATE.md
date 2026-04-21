# ue-plugin — STATE

Updated: 2026-04-21 (PM)

## Files
- `Source/BlackjackCore/`   — 14 files (7 headers + 7 cpp + build.cs + 1 test spec)
- `Source/BlackjackUE/`     — 14 files (components, actors, BP library)
- `SampleProject/`          — minimal .uproject with sample GameMode
- Total: ~2100 lines of C++

## Recent work
- Source-complete C++ port of the TS rules engine (single-seat version)
- UBlackjackGameComponent + actors + dealer character
- Conformance spec framework in place (loads TS-emitted JSON vectors)

## Known unfinished / upcoming
- Never compiled yet — sandbox has no UE. User must build on Windows.
- Multi-seat sync (M3) waits on M1 (TS multi-seat)
- Scene redesign (M4) — pit boss, CCTV, NPC player characters
- Psychological systems (M5) — heat, morale, timer, gestures
- Tell/bluff/perception (M6)
- dealer-ai HTTP client (M9)

## Open issues on this module
- **Requires user validation** on Windows + UE 5.3+ build before M3 starts.
  PM needs to confirm that the current source-complete code compiles cleanly
  on target OS before dispatching the first C++ refactor subagent.

## External dependencies
- UE 5.3+ runtime
- No model/AI deps here (those live in dealer-ai)
