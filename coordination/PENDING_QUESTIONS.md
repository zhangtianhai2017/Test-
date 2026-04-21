# PENDING QUESTIONS — awaiting user answer

> When a subagent hits a design question it cannot resolve from its
> `AGENT.md`, it must **not** invent an answer. It appends to this file and
> stops. The PM reviews and relays to the user. User's answer gets recorded
> in `DECISIONS.md` with a new `D-NNN` id, and this file's entry is deleted.
>
> Format per entry:
>
> ```
> ## Q-NNN — short title
> Raised: YYYY-MM-DD by <subagent task id or PM>
> From: <module or milestone>
> Question: clear, self-contained, no context references
> Options considered:
>   - A) ... (implications)
>   - B) ... (implications)
> Subagent recommendation: A / B / none
> PM recommendation: (filled by PM before relay)
> ```

## Q-001 — STAND (and HIT/DOUBLE/SPLIT/SURRENDER) hardcoded to seats[0]
Raised: 2026-04-21 by M1d (engine multi-seat tests)
From: packages/engine — multi-seat play flow

Question: The legacy action handlers `hit()`, `stand()`, `doubleDown()`,
`split()`, `surrender()` all compute `const s = seat()` where
`seat = () => seats[0]!`. They then mutate seat 0's hand and dispatch
`dealCardTo("player", activeSeatIndex, ...)` — a mix of seat 0 state and
the multi-seat `activeSeatIndex`. When more than one seat is active:
  1. Dispatch STAND — marks seat 0's hand as stood, calls advanceHand,
     which moves `activeSeatIndex` to seat 1.
  2. Dispatch STAND again — still targets seat 0 (already stood), so
     advanceHand runs but seat 0 has no more playable hands; seat 1's
     hand is never marked `stood`, so the loop returns early at seat 1
     (the actual active seat has a live hand awaiting action). We are
     stuck in `playerTurn` with no way to advance seat 1/2 via STAND.

Minimal repro (fails on main):
```ts
const g = createGame({ seed: 42 });
g.dispatch({
  type: "CONFIGURE_TABLE",
  config: { seats: [
    { kind: "human", name: "A" },
    { kind: "human", name: "B" },
    { kind: "human", name: "C" },
  ]},
});
g.dispatch({ type: "PLACE_BET_FOR_SEAT", seatIndex: 0, amount: 25 });
g.dispatch({ type: "PLACE_BET_FOR_SEAT", seatIndex: 1, amount: 25 });
g.dispatch({ type: "PLACE_BET_FOR_SEAT", seatIndex: 2, amount: 25 });
// Loop STAND while phase === "playerTurn" — never terminates / stalls;
// phase never reaches "roundOver".
```

Options considered:
  - A) Change `seat()` helpers to read `seats[activeSeatIndex]` so HIT/
       STAND/DOUBLE/SPLIT/SURRENDER act on whichever seat currently
       holds the turn. Preserves single-seat semantics (seat 0 is the
       only active seat in legacy mode). Low risk, clearly correct for
       multi-seat play.
  - B) Add a new PLAYER_ACTION_FOR_SEAT dispatcher and keep legacy HIT/
       STAND targeting seat 0. More churn; forces every caller to
       distinguish legacy vs multi-seat; does not fix the bug on its
       own since the single-seat actions still won't drive a multi-seat
       round to completion.

Subagent recommendation: A
PM recommendation: (filled by PM before relay)

Impact on M1d tests:
  - `test/multiSeat.test.ts` tests #12 and #13 (three-seat STAND round
    and per-seat bankroll) are marked `.skip` with a comment pointing
    to Q-001. All other 12 new tests pass.
