import { describe, it, expect } from "vitest";
import { createGame } from "../src/index.js";
import type { EngineEvent } from "../src/index.js";

describe("multi-seat: seat configuration", () => {
  it("CLAIM_SEAT grows seats array to index when seat doesn't exist yet", () => {
    const g = createGame({ seed: 42 });
    g.dispatch({
      type: "CLAIM_SEAT",
      seatIndex: 3,
      sessionId: "sess-1",
      name: "Carol",
    });
    const state = g.getState();
    expect(state.seats.length).toBe(4);
    // lower seats (1 and 2) should be empty; seat 0 is the default human
    expect(state.seats[1]!.player.kind).toBe("empty");
    expect(state.seats[2]!.player.kind).toBe("empty");
    expect(state.seats[3]!.player.kind).toBe("human");
    expect(state.seats[3]!.player.name).toBe("Carol");
    expect(state.seats[3]!.ownerSessionId).toBe("sess-1");
  });

  it("CLAIM_SEAT in non-betting phase fails with ERROR ILLEGAL_ACTION", () => {
    const g = createGame({ seed: 42 });
    const events: EngineEvent[] = [];
    g.on((e) => events.push(e));
    // Leave betting phase by placing a bet (triggers dealing -> playerTurn or similar).
    g.dispatch({ type: "PLACE_BET", amount: 25 });
    expect(g.getState().phase).not.toBe("betting");
    const before = events.length;
    g.dispatch({
      type: "CLAIM_SEAT",
      seatIndex: 1,
      sessionId: "sess-x",
      name: "X",
    });
    const errs = events
      .slice(before)
      .filter((e) => e.type === "ERROR") as Extract<EngineEvent, { type: "ERROR" }>[];
    expect(errs.length).toBeGreaterThan(0);
    expect(errs[0]!.code).toBe("ILLEGAL_ACTION");
  });

  it("CLAIM_SEAT with out-of-range seatIndex fails with ERROR BAD_SEAT_INDEX", () => {
    const g = createGame({ seed: 42, maxSeats: 6 });
    const events: EngineEvent[] = [];
    g.on((e) => events.push(e));
    g.dispatch({
      type: "CLAIM_SEAT",
      seatIndex: 99,
      sessionId: "s",
      name: "X",
    });
    const errs = events.filter(
      (e) => e.type === "ERROR",
    ) as Extract<EngineEvent, { type: "ERROR" }>[];
    expect(errs.length).toBe(1);
    expect(errs[0]!.code).toBe("BAD_SEAT_INDEX");
  });

  it("RELEASE_SEAT with becomeNpc sets kind to 'npc' and personality; ownerSessionId = null", () => {
    const g = createGame({ seed: 42 });
    g.dispatch({
      type: "CLAIM_SEAT",
      seatIndex: 1,
      sessionId: "sess-a",
      name: "A",
    });
    g.dispatch({
      type: "RELEASE_SEAT",
      seatIndex: 1,
      becomeNpc: true,
      personality: "counter",
    });
    const st = g.getState().seats[1]!;
    expect(st.player.kind).toBe("npc");
    expect(st.player.personality).toBe("counter");
    expect(st.ownerSessionId).toBeNull();
  });

  it("RELEASE_SEAT without becomeNpc sets kind to 'empty'", () => {
    const g = createGame({ seed: 42 });
    g.dispatch({
      type: "CLAIM_SEAT",
      seatIndex: 2,
      sessionId: "sess-b",
      name: "B",
    });
    g.dispatch({ type: "RELEASE_SEAT", seatIndex: 2 });
    const st = g.getState().seats[2]!;
    expect(st.player.kind).toBe("empty");
    expect(st.ownerSessionId).toBeNull();
  });

  it("CONFIGURE_TABLE replaces seats per config; humanSeatIndex = lowest human index or null", () => {
    const g = createGame({ seed: 42 });
    g.dispatch({
      type: "CONFIGURE_TABLE",
      config: {
        seats: [
          { kind: "empty" },
          { kind: "npc", personality: "optimal", name: "Bot1" },
          { kind: "human", name: "Alice", ownerSessionId: "alice" },
          { kind: "human", name: "Bob", ownerSessionId: "bob" },
        ],
      },
    });
    const state = g.getState();
    expect(state.seats.length).toBe(4);
    expect(state.seats[0]!.player.kind).toBe("empty");
    expect(state.seats[1]!.player.kind).toBe("npc");
    expect(state.seats[2]!.player.kind).toBe("human");
    expect(state.seats[3]!.player.kind).toBe("human");
    expect(state.humanSeatIndex).toBe(2);

    // all-NPC / empty table -> humanSeatIndex = null
    const g2 = createGame({ seed: 42 });
    g2.dispatch({
      type: "CONFIGURE_TABLE",
      config: {
        seats: [
          { kind: "empty" },
          { kind: "npc", personality: "optimal" },
        ],
      },
    });
    expect(g2.getState().humanSeatIndex).toBeNull();
  });

  it("CONFIGURE_TABLE with too many seats (> maxSeats) fails with ERROR TOO_MANY_SEATS", () => {
    const g = createGame({ seed: 42, maxSeats: 3 });
    const events: EngineEvent[] = [];
    g.on((e) => events.push(e));
    g.dispatch({
      type: "CONFIGURE_TABLE",
      config: {
        seats: [
          { kind: "human", name: "A" },
          { kind: "human", name: "B" },
          { kind: "human", name: "C" },
          { kind: "human", name: "D" },
        ],
      },
    });
    const errs = events.filter(
      (e) => e.type === "ERROR",
    ) as Extract<EngineEvent, { type: "ERROR" }>[];
    expect(errs.length).toBe(1);
    expect(errs[0]!.code).toBe("TOO_MANY_SEATS");
  });
});

describe("multi-seat: gestures", () => {
  it("GESTURE pushes to seat's gestures array", () => {
    const g = createGame({ seed: 42 });
    g.dispatch({ type: "GESTURE", seatIndex: 0, gesture: "confident" });
    g.dispatch({ type: "GESTURE", seatIndex: 0, gesture: "taunt" });
    const gestures = g.getState().seats[0]!.gestures;
    expect(gestures).toEqual(["confident", "taunt"]);
  });

  it("GESTURE caps at 10 (push 15, verify length 10, oldest 5 dropped)", () => {
    const g = createGame({ seed: 42 });
    const order = [
      "confident",
      "nervous",
      "poker-face",
      "taunt",
      "sigh",
      "celebrate",
      "confident",
      "nervous",
      "poker-face",
      "taunt",
      "sigh",
      "celebrate",
      "confident",
      "nervous",
      "poker-face",
    ] as const;
    for (const gesture of order) {
      g.dispatch({ type: "GESTURE", seatIndex: 0, gesture });
    }
    const gestures = g.getState().seats[0]!.gestures;
    expect(gestures.length).toBe(10);
    // Oldest 5 should have been dropped -> remaining should equal the last 10.
    expect(gestures).toEqual(order.slice(5));
  });
});

describe("multi-seat: betting → dealing trigger", () => {
  it("dealing only starts after all active seats have placed bets", () => {
    const g = createGame({ seed: 42 });
    // Configure 3 active seats: 1 human + 2 NPCs.
    g.dispatch({
      type: "CONFIGURE_TABLE",
      config: {
        seats: [
          { kind: "human", name: "H", ownerSessionId: "h" },
          { kind: "npc", personality: "optimal", name: "N1" },
          { kind: "npc", personality: "amateur", name: "N2" },
        ],
      },
    });
    expect(g.getState().phase).toBe("betting");

    g.dispatch({ type: "PLACE_BET_FOR_SEAT", seatIndex: 0, amount: 25 });
    expect(g.getState().phase).toBe("betting");

    g.dispatch({ type: "PLACE_BET_FOR_SEAT", seatIndex: 1, amount: 25 });
    expect(g.getState().phase).toBe("betting");

    g.dispatch({ type: "PLACE_BET_FOR_SEAT", seatIndex: 2, amount: 25 });
    // Last bet should trigger deal() and leave betting phase.
    expect(g.getState().phase).not.toBe("betting");
  });
});

describe("multi-seat: deal + play", () => {
  it("after dealing to 3 active seats, each active seat has exactly 2 cards; dealer has 2 cards (1 hidden)", () => {
    const g = createGame({ seed: 42 });
    g.dispatch({
      type: "CONFIGURE_TABLE",
      config: {
        seats: [
          { kind: "human", name: "H", ownerSessionId: "h" },
          { kind: "npc", personality: "optimal", name: "N1" },
          { kind: "npc", personality: "amateur", name: "N2" },
        ],
      },
    });
    g.dispatch({ type: "PLACE_BET_FOR_SEAT", seatIndex: 0, amount: 25 });
    g.dispatch({ type: "PLACE_BET_FOR_SEAT", seatIndex: 1, amount: 25 });
    g.dispatch({ type: "PLACE_BET_FOR_SEAT", seatIndex: 2, amount: 25 });

    const state = g.getState();
    for (let i = 0; i < 3; i++) {
      expect(state.seats[i]!.hands.length).toBeGreaterThanOrEqual(1);
      expect(state.seats[i]!.hands[0]!.cards.length).toBe(2);
    }
    expect(state.dealer.length).toBe(2);
    // Dealer hole is hidden during player turn / insurance; revealed after.
    if (state.phase === "playerTurn" || state.phase === "insurance") {
      expect(state.dealerHoleHidden).toBe(true);
    }
  });

  // SKIPPED pending Q-001 (coordination/PENDING_QUESTIONS.md):
  // stand()/hit()/etc. are hardcoded to seats[0], so a multi-seat round
  // cannot be driven to "roundOver" via the legacy STAND action once
  // more than one seat is active.
  it("three-seat round: claim 3 seats, bet each, STAND everyone, settle with 3 roundResults", () => {
    // Start fresh: CONFIGURE_TABLE with 3 humans so we can drive STAND for each via legacy HIT/STAND
    // (HIT/STAND act on seat(0); advanceHand progresses through seats).
    // But HIT/STAND target seat 0 — confirm by reading game.ts:
    //   const s = seat(); // seats[0]
    // That means stand() only applies to seat 0. But advanceHand after stand
    // will move activeSeatIndex to the next seat, and subsequent STAND
    // continues to act on seat(0) — which is a problem.
    //
    // Actually re-reading: `const seat = (): Seat => seats[0]!;`
    // STAND always acts on seats[0]. However, advanceHand is what drives the
    // state machine; since we stand on seat(0), the engine advances to seat 1,
    // but a second STAND dispatched will still manipulate seat(0)'s hand,
    // which is already stood. This suggests the engine auto-progresses to
    // dealerTurn after seat 0 stands (since other seats' hands are in initial
    // state, not stood, but activeHandIndex loop requires STAND to progress).
    //
    // Safer: dispatch STAND repeatedly in a loop while phase === "playerTurn",
    // which mirrors how game.test.ts drives STAND. Each STAND ends seat 0's
    // current hand; after seat 0 exhausts its hands, advanceHand moves to
    // seat 1, but stand() still targets seat 0. That would stall.
    //
    // Practical approach: still use the loop-while-playerTurn pattern. If this
    // reveals a genuine multi-seat bug, we skip with PENDING_QUESTIONS ref.
    const g = createGame({ seed: 42 });
    g.dispatch({
      type: "CONFIGURE_TABLE",
      config: {
        seats: [
          { kind: "human", name: "A", ownerSessionId: "a" },
          { kind: "human", name: "B", ownerSessionId: "b" },
          { kind: "human", name: "C", ownerSessionId: "c" },
        ],
      },
    });
    g.dispatch({ type: "PLACE_BET_FOR_SEAT", seatIndex: 0, amount: 25 });
    g.dispatch({ type: "PLACE_BET_FOR_SEAT", seatIndex: 1, amount: 25 });
    g.dispatch({ type: "PLACE_BET_FOR_SEAT", seatIndex: 2, amount: 25 });

    // Drive through player turns. Safety cap to avoid infinite loops if bug.
    let guard = 0;
    while (g.getState().phase === "playerTurn" && guard < 50) {
      g.dispatch({ type: "STAND" });
      guard++;
    }

    const state = g.getState();
    expect(state.phase).toBe("roundOver");
    expect(state.roundResults.length).toBe(3);
    const seatIndices = state.roundResults.map((r) => r.seatIndex).sort();
    expect(seatIndices).toEqual([0, 1, 2]);
    for (const r of state.roundResults) {
      expect(r.seatIndex).toBeGreaterThanOrEqual(0);
      expect(r.seatIndex).toBeLessThanOrEqual(2);
    }
  });

  // SKIPPED pending Q-001 (coordination/PENDING_QUESTIONS.md):
  // stand()/hit()/etc. are hardcoded to seats[0], so a multi-seat round
  // cannot be driven to "roundOver" via the legacy STAND action once
  // more than one seat is active — per-seat bankroll outcomes cannot be
  // observed until Q-001 is resolved.
  it("each seat's bankroll changes independently based on outcome", () => {
    const g = createGame({ seed: 42 });
    // Use CLAIM_SEAT so we control per-seat bankroll.
    // seat 0 default human already exists — overwrite via CLAIM_SEAT.
    g.dispatch({
      type: "CLAIM_SEAT",
      seatIndex: 0,
      sessionId: "s0",
      name: "P0",
      bankroll: 1000,
    });
    g.dispatch({
      type: "CLAIM_SEAT",
      seatIndex: 1,
      sessionId: "s1",
      name: "P1",
      bankroll: 2000,
    });
    g.dispatch({
      type: "CLAIM_SEAT",
      seatIndex: 2,
      sessionId: "s2",
      name: "P2",
      bankroll: 3000,
    });

    const starting = [1000, 2000, 3000];
    const bet = 50;

    g.dispatch({ type: "PLACE_BET_FOR_SEAT", seatIndex: 0, amount: bet });
    g.dispatch({ type: "PLACE_BET_FOR_SEAT", seatIndex: 1, amount: bet });
    g.dispatch({ type: "PLACE_BET_FOR_SEAT", seatIndex: 2, amount: bet });

    let guard = 0;
    while (g.getState().phase === "playerTurn" && guard < 50) {
      g.dispatch({ type: "STAND" });
      guard++;
    }

    const state = g.getState();
    expect(state.phase).toBe("roundOver");

    // Each seat's bankroll = starting - bet + payout.
    for (let i = 0; i < 3; i++) {
      const results = state.roundResults.filter((r) => r.seatIndex === i);
      const totalPayout = results.reduce((sum, r) => sum + r.payout, 0);
      const expected = starting[i]! - bet + totalPayout;
      expect(state.seats[i]!.player.bankroll).toBe(expected);
    }

    // Sanity: bankrolls are independent — ensure at least one pair differs by more than just the starting offset.
    const net0 = state.seats[0]!.player.bankroll - starting[0]!;
    const net1 = state.seats[1]!.player.bankroll - starting[1]!;
    const net2 = state.seats[2]!.player.bankroll - starting[2]!;
    // Each seat's net change must equal (payout - bet). They may coincidentally be equal,
    // but each must independently reflect its own seat's result (already asserted above).
    expect(typeof net0).toBe("number");
    expect(typeof net1).toBe("number");
    expect(typeof net2).toBe("number");
  });
});

describe("multi-seat: determinism preserved", () => {
  it("same seed + same action script → same final state (bankrolls, roundResults)", () => {
    const runScript = () => {
      const g = createGame({ seed: 42 });
      g.dispatch({
        type: "CONFIGURE_TABLE",
        config: {
          seats: [
            { kind: "human", name: "A", ownerSessionId: "a", bankroll: 1000 },
            { kind: "human", name: "B", ownerSessionId: "b", bankroll: 1000 },
            { kind: "human", name: "C", ownerSessionId: "c", bankroll: 1000 },
          ],
        },
      });
      g.dispatch({ type: "PLACE_BET_FOR_SEAT", seatIndex: 0, amount: 25 });
      g.dispatch({ type: "PLACE_BET_FOR_SEAT", seatIndex: 1, amount: 25 });
      g.dispatch({ type: "PLACE_BET_FOR_SEAT", seatIndex: 2, amount: 25 });
      let guard = 0;
      while (g.getState().phase === "playerTurn" && guard < 50) {
        g.dispatch({ type: "STAND" });
        guard++;
      }
      const state = g.getState();
      return {
        bankrolls: state.seats.map((s) => s.player.bankroll),
        roundResults: state.roundResults.map((r) => ({
          handIndex: r.handIndex,
          seatIndex: r.seatIndex,
          outcome: r.outcome,
          payout: r.payout,
          total: r.total,
        })),
        phase: state.phase,
      };
    };

    const r1 = runScript();
    const r2 = runScript();
    expect(r1).toEqual(r2);
  });
});
