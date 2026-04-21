# engine — STATE

Updated: 2026-04-21 (PM)

## Files
- src/: 9 files, ~925 lines TS
- test/: 5 files, 43 tests, all green as of commit 894c2d4

## Recent work
- Initial engine build with Vegas/Spanish21/Pontoon/SuperFun21 rulesets
- Side bets 21+3, Perfect Pairs, Lucky Ladies
- Split/double/surrender/insurance all implemented
- Seeded RNG (mulberry32), deterministic shoe

## Known unfinished / upcoming
- **Multi-seat refactor** (M1, in dispatch)
- `gestures[]` field on Seat (M2d)
- `tilt` field on Seat (M2b)
- NPC personality field on Player (M2a/b — but AI logic lives in ai-npc module)

## Conformance vectors
- 8 single-player vectors in `packages/conformance/vectors/*.json`
- Must be regenerated after M1 lands (multi-seat schema)

## Open issues on this module
None right now.
