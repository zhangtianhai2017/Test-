# AGENT — engine module

You are the maintainer of the `packages/engine` module. Read this whole file
before touching code. If anything below is unclear, append to
`coordination/PENDING_QUESTIONS.md` and stop.

## Purpose

This is the **authoritative reference implementation** of all blackjack
rules. Every other module (ai-npc, ue-plugin C++ port, ui-web, ui-3d) must
agree with this. TS is the spec; C++ is a follower.

## Scope — what you own

- `packages/engine/src/*.ts`  — rules, shoe, hand, state machine, events
- `packages/engine/test/*.ts` — Vitest unit tests
- Conformance vector generation logic (shared with `conformance` package)

## Scope — what you do NOT own

- NPC AI logic (lives in `packages/ai-npc` — separate module)
- Any UI code
- Any Python code
- C++ port (in `packages/ue-plugin/Source/BlackjackCore/`)

## Key architectural invariants (do not break)

1. **Zero runtime dependencies on DOM, Node APIs beyond built-in, or Three.js.**
   Engine must import-clean in any JS environment.
2. **Deterministic with seed.** Same `seed` + same action sequence = same
   cards and outcomes, byte-for-byte. This is how conformance is verified.
3. **Action dispatch + event bus, no hidden state.** External code only
   touches the engine via `dispatch(action)` and `on(listener)`.
4. **All new features extend, never break, the snapshot format.** Adding
   fields to `GameSnapshot` is fine; renaming or removing fields is not —
   downstream code (ui-web, ui-3d) would snap.

## Multi-seat extension (in flight)

The engine is being refactored from single-player-multi-hand to multi-seat.
Target shape (see M1 milestone):

```typescript
interface GameSnapshot {
  // ... existing fields
  seats: Seat[];
  activeSeatIndex: number;
  humanSeatIndex: number | null;   // which seat is the user
  // legacy single-seat convenience fields stay — return values from seats[humanSeatIndex]
  hands: PlayerHand[];             // = seats[activeSeatIndex].hands
  pendingBet: number;              // = seats[activeSeatIndex].pendingBet
  sideBets: SideBets;              // = seats[activeSeatIndex].sideBets
  insuranceBet: number;            // = seats[activeSeatIndex].insuranceBet
}

interface Seat {
  index: number;
  player: Player;
  hands: PlayerHand[];
  activeHandIndex: number;
  pendingBet: number;
  sideBets: SideBets;
  insuranceBet: number;
  gestures: Gesture[];             // recent gestures; for bluff system
  tilt: number;                    // 0-1, emotional state; for NPC
  ownerSessionId: string | null;   // which client owns this seat (D-017). null = NPC or empty.
}

interface Player {
  id: string;
  name: string;
  kind: "human" | "empty" | "npc";
  bankroll: number;
  personality?: NpcPersonality;    // set when kind = "npc"
}
```

Backward-compat rule: all existing top-level snapshot fields remain valid
and reflect the active seat. Tests from the pre-refactor era must still
pass (single-player games = 1-seat games).

## Tests

Run:

```bash
npm run test --workspace=@blackjack/engine
```

Coverage target: every new mechanic ships with a Vitest case.

## Code style

- TypeScript strict mode, no `any` unless justified in a code comment.
- No classes unless state-bearing and necessary; prefer functions +
  closures (see `createGame`, `createShoe`).
- Public API goes through `packages/engine/src/index.ts`.
- Comment WHY, not WHAT. No comments for obvious code.

## How to add a new game mechanic (checklist)

1. Update the relevant type in `src/*.ts`.
2. Update `createGame` state machine if the phase flow changes.
3. Add events to `src/events.ts` if new event types are needed.
4. Add Vitest cases in `test/*.test.ts`.
5. Run `npm run test --workspace=@blackjack/engine`.
6. If protocol-visible, update `packages/dealer-ai/src/dealer_ai/schema.py`
   **by raising an escalation** (cross-module change — PM re-plans).
7. Update `packages/conformance/src/export.ts` if new test vectors are
   warranted.
8. Write what changed to `coordination/modules/engine/STATE.md`.

## Escalation triggers

- Change affects the snapshot shape in a non-backward-compatible way.
- Change requires a matching change in `ai-npc` or `ue-plugin/BlackjackCore`.
- A ruleset you'd like to add isn't in `DECISIONS.md` yet.

In all three cases: append to `PENDING_QUESTIONS.md` and stop.
