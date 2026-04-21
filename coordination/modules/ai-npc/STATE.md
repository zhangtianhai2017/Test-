# ai-npc — STATE

Updated: 2026-04-21 after M2 complete (PM)

## Files
- `src/`: 7 files
  - basicStrategy.ts  — H17 + S17 canonical WoO lookup tables
  - hiLoCounter.ts    — Hi-Lo count + true count
  - betPolicies.ts    — flat / kelly / reverse-martingale / unit-spread
  - personalities.ts  — 7 personality configs
  - tells.ts          — per-personality tell banks + seeded picker
  - tilt.ts           — tilt scalar + update/decay
  - npcAgent.ts       — top-level npcDecidePlay / npcDecideBet
  - index.ts          — public API exports
- `test/`: 8 files, **93 tests**, 0 skipped, 0 failed

## Public API

```typescript
import {
  npcDecidePlay, npcDecideBet,
  decideBasicStrategy,
  newCounter, observe, trueCount,
  decideBet,
  PERSONALITIES,
  PERSONALITY_TELLS, pickTell,
  updateTilt, DEFAULT_TILT,
} from "@blackjack/ai-npc";
```

## Recent work
- **M2 complete** — full NPC AI library:
  - Canonical basic strategy in lookup tables (H17/S17 variants)
  - Hi-Lo counter with running + true count
  - 4 bet policies (flat/Kelly/reverse-martingale/unit-spread)
  - 7 personalities (optimal, counter, amateur, chaser, superstitious, ritualistic, risk_averse)
    each with their own bet policy, deviation rules, tilt response, tell bank
  - Tilt model with outcome-driven updates + passive decay
  - Tell generator (seeded, per-personality)
  - npcAgent top-level that integrates all of the above

## Commit chain
64433ea (M2a scaffold) → dcf37d8 (M2b basic strategy) →
44f8df3 (M2c counter+bets) → 134209a (M2d personalities+tilt+tells) →
664e768 (M2e source, partial) → 1f0f988 (M2e tests, complete)

## Known unfinished / upcoming
- M12: NPC tilt integration with real game events + dealer-state evolution
  (cross-module; involves game-server feeding tilt deltas into each NPC)
- Future: tells refined into personality-specific animations / timings for UE

## Open issues on this module
None.

## Gotchas for future work
- `npcDecideBet` seed parameter is accepted but unused currently (API
  symmetry only). Safe to pass 0.
- Chaser reverse-martingale is capped at 4×unit. With unit=5 (minBet 5),
  max bet from chaser = 20. Change `betUnitMultiplier` in
  personalities.ts to raise the cap.
- Kelly ramp is linear `floor(trueCount - 0.5)` clamped [1,8], not
  the common 1-2-4-8 doubling. Documented in M2c commit.
