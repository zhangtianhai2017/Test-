# engine — STATE

Updated: 2026-04-21 after M1 complete (PM)

## Files
- src/: 9 files
  - game.ts ~780 lines (was 566 pre-M1)
  - plus cards.ts, hand.ts, rules.ts, dealer.ts, events.ts, sidebets.ts,
    rng.ts, index.ts
- test/: 6 files, **57 tests**, 0 skipped, 0 failed
  - NEW: test/multiSeat.test.ts (14 tests for multi-seat API)

## Recent work
- **M1 complete** — engine is now multi-seat capable:
  - Seat / Player / Gesture / NpcPersonality types added
  - Internal state stored in seats[] with backward-compat top-level fields
  - 5 new actions: CONFIGURE_TABLE, CLAIM_SEAT, RELEASE_SEAT,
    PLACE_BET_FOR_SEAT, GESTURE
  - Multi-seat flow: betting→dealing waits for all active bets,
    round-robin dealing, playerTurn iterates through seats,
    settlement per seat, side-bets per seat, newRound resets per seat
  - HandResult.seatIndex field for routing
  - SEAT_CLAIMED / SEAT_RELEASED / GESTURE_MADE events
- Commit chain: 196438f (M1a) → 1f69a09 (M1b) → 6cf9a68 (M1c.1) →
  a9059fd (M1c.2) → fb80efb (M1c.3) → 3f52257 (M1c.4a) →
  2f5b9aa (M1c.4b) → 085f46e (M1d) → 62198ba (M1c.5 bug fix / D-023)

## Known unfinished / upcoming
- M11 conformance vectors need regeneration for multi-seat (scheduled)
- Per-seat insurance handlers are a future concern; INSURE/DECLINE
  still target humanSeatIndex ?? 0 in legacy fashion (game-server
  will loop over seats if per-NPC insurance is needed)
- Engine is passive for NPC decisions — external code (game-server
  using @blackjack/ai-npc) must dispatch HIT/STAND etc. for NPC seats.
  The engine never auto-plays. This is intentional; stays that way.

## Conformance vectors
- 8 single-player vectors in `packages/conformance/vectors/*.json`
- Must be regenerated after ai-npc (M2) and multi-seat scenarios land
  (M11's job)

## Open issues on this module
None. Q-001 resolved as D-023, fix committed in 62198ba.
