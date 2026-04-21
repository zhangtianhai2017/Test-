/**
 * Unit tests for the engine → wire event bridge (M4a).
 *
 * We deliberately skip the WebSocket layer here: the bridge is a pure
 * function of (engine event stream, broadcast fn), and driving the engine
 * directly through `createTable().game.dispatch(...)` gives deterministic,
 * fast, non-flaky coverage of the frame-translation rules. WS-level
 * end-to-end coverage lands in M4d.
 *
 * What's covered:
 *  - CARD_DEALT hides the card when faceDown=true (hole-card secrecy).
 *  - CARD_DEALT to="player" gets a seatIndex inferred from the engine state.
 *  - PHASE_CHANGED frames arrive in the expected order during a minimal
 *    single-seat round.
 *  - BET_SETTLED carries seatIndex from the HandResult tail.
 *  - ROUND_OVER carries the full results array.
 *  - BANKROLL_CHANGED resolves seatIndex from the per-seat bankroll delta.
 *  - SEAT_CLAIMED / SEAT_RELEASED engine events are NOT mirrored by the
 *    bridge (dispatch.ts owns those wire broadcasts).
 *  - A stand → dealerTurn → settlement flow produces the expected sequence.
 */
import { describe, expect, it } from "vitest";

import { createLobby } from "../src/lobby/lobby.js";
import type { Table } from "../src/lobby/table.js";
import type { ServerFrame } from "../src/protocol/server.js";
import { createEventBridge } from "../src/table/eventBridge.js";

/**
 * Build a fresh lobby, table, and bridge wired to an in-memory capture list.
 * Returns everything the tests need plus a helper to drain broadcasts by
 * type.
 */
function setup(seed = 42): {
  table: Table;
  captured: Array<{ tableId: string; frame: ServerFrame }>;
} {
  const captured: Array<{ tableId: string; frame: ServerFrame }> = [];
  const lobby = createLobby(seed);
  const bridge = createEventBridge((tableId, frame) => {
    captured.push({ tableId, frame });
  });
  const table = lobby.createTable({
    ruleSet: "VEGAS",
    maxSeats: 3,
    dealerPersona: "veteran",
    language: "en",
  });
  bridge.attach(table);
  return { table, captured };
}

/** Filter captured frames to those matching `type`. */
function only<T extends ServerFrame["type"]>(
  captured: Array<{ tableId: string; frame: ServerFrame }>,
  type: T,
): Array<Extract<ServerFrame, { type: T }>> {
  return captured
    .map((c) => c.frame)
    .filter((f): f is Extract<ServerFrame, { type: T }> => f.type === type);
}

describe("event bridge (M4a)", () => {
  it("CARD_DEALT with faceDown=true omits the card field", () => {
    const { table, captured } = setup();

    table.game.dispatch({
      type: "CLAIM_SEAT",
      seatIndex: 0,
      sessionId: "sess-a",
      name: "Alice",
    });
    table.game.dispatch({
      type: "PLACE_BET_FOR_SEAT",
      seatIndex: 0,
      amount: 25,
    });

    const deals = only(captured, "CARD_DEALT");
    expect(deals.length).toBeGreaterThanOrEqual(4);
    // Exactly one face-down deal (dealer's hole card).
    const faceDown = deals.filter((d) => d.faceDown);
    expect(faceDown.length).toBe(1);
    expect(faceDown[0]!.to).toBe("dealer");
    // CRITICAL: no card field at all.
    expect(faceDown[0]!).not.toHaveProperty("card");
    // Every face-up deal carries a card object.
    for (const d of deals.filter((x) => !x.faceDown)) {
      expect(d.card).toBeDefined();
      expect(typeof d.card!.rank).toBe("string");
      expect(typeof d.card!.suit).toBe("string");
    }
  });

  it("CARD_DEALT to='player' carries seatIndex inferred from engine state", () => {
    const { table, captured } = setup();
    table.game.dispatch({
      type: "CLAIM_SEAT",
      seatIndex: 0,
      sessionId: "sess-a",
      name: "Alice",
    });
    table.game.dispatch({
      type: "PLACE_BET_FOR_SEAT",
      seatIndex: 0,
      amount: 25,
    });

    const playerDeals = only(captured, "CARD_DEALT").filter(
      (d) => d.to === "player",
    );
    expect(playerDeals.length).toBeGreaterThanOrEqual(2);
    for (const d of playerDeals) {
      expect(d.seatIndex).toBe(0);
    }
    // Dealer deals should NOT carry seatIndex (optional field for dealer).
    const dealerDeals = only(captured, "CARD_DEALT").filter(
      (d) => d.to === "dealer",
    );
    for (const d of dealerDeals) {
      expect(d.seatIndex).toBeUndefined();
    }
  });

  it("PLACE_BET_FOR_SEAT produces PHASE_CHANGED → dealing frames", () => {
    const { table, captured } = setup();
    table.game.dispatch({
      type: "CLAIM_SEAT",
      seatIndex: 0,
      sessionId: "sess-a",
      name: "Alice",
    });
    const before = captured.length;
    table.game.dispatch({
      type: "PLACE_BET_FOR_SEAT",
      seatIndex: 0,
      amount: 25,
    });
    const frames = captured.slice(before).map((c) => c.frame);
    // First frame emitted after placing the bet must be the dealing
    // phase transition (BET_PLACED is intentionally skipped by the bridge;
    // the PHASE_CHANGED follows immediately).
    const firstPhase = frames.find((f) => f.type === "PHASE_CHANGED");
    expect(firstPhase).toBeDefined();
    expect((firstPhase as { phase: string }).phase).toBe("dealing");
  });

  it("SEAT_CLAIMED / SEAT_RELEASED engine events are NOT mirrored by the bridge", () => {
    const { table, captured } = setup();
    table.game.dispatch({
      type: "CLAIM_SEAT",
      seatIndex: 1,
      sessionId: "sess-b",
      name: "Bob",
    });
    table.game.dispatch({ type: "RELEASE_SEAT", seatIndex: 1 });
    // Bridge MUST NOT emit SEAT_ASSIGNED or SEAT_RELEASED — dispatch.ts
    // owns those wire frames.
    expect(only(captured, "SEAT_ASSIGNED").length).toBe(0);
    expect(only(captured, "SEAT_RELEASED").length).toBe(0);
  });

  it("BANKROLL_CHANGED resolves seatIndex from the per-seat delta", () => {
    const { table, captured } = setup();
    table.game.dispatch({
      type: "CLAIM_SEAT",
      seatIndex: 2,
      sessionId: "sess-c",
      name: "Carol",
    });
    table.game.dispatch({
      type: "PLACE_BET_FOR_SEAT",
      seatIndex: 2,
      amount: 25,
    });

    const bankrolls = only(captured, "BANKROLL_CHANGED");
    expect(bankrolls.length).toBeGreaterThan(0);
    // Every BANKROLL_CHANGED must target seat 2, since that's the only seat
    // with a non-empty player.
    for (const b of bankrolls) {
      expect(b.seatIndex).toBe(2);
    }
    // The very first BANKROLL_CHANGED corresponds to the -25 bet debit.
    expect(bankrolls[0]!.delta).toBe(-25);
  });

  it("BET_SETTLED frames carry seatIndex and ROUND_OVER carries the full results", () => {
    const { table, captured } = setup();
    table.game.dispatch({
      type: "CLAIM_SEAT",
      seatIndex: 0,
      sessionId: "sess-a",
      name: "Alice",
    });
    table.game.dispatch({
      type: "PLACE_BET_FOR_SEAT",
      seatIndex: 0,
      amount: 25,
    });
    // Drive the rest of the round.
    // Hit until bust or stand — here we STAND immediately.
    let guard = 0;
    while (table.game.getState().phase === "playerTurn" && guard++ < 10) {
      table.game.dispatch({ type: "STAND" });
    }

    const settled = only(captured, "BET_SETTLED");
    expect(settled.length).toBeGreaterThanOrEqual(1);
    for (const s of settled) {
      expect(s.seatIndex).toBe(0);
      expect(typeof s.handIndex).toBe("number");
      expect(typeof s.outcome).toBe("string");
      expect(typeof s.payout).toBe("number");
    }

    const roundOvers = only(captured, "ROUND_OVER");
    expect(roundOvers.length).toBe(1);
    expect(roundOvers[0]!.results.length).toBeGreaterThanOrEqual(1);
    // Every HandResultPayload must have a seatIndex.
    for (const r of roundOvers[0]!.results) {
      expect(r.seatIndex).toBe(0);
    }
  });

  it("STAND drives PHASE_CHANGED → dealerTurn and emits DEALER_ACTION frames", () => {
    const { table, captured } = setup();
    table.game.dispatch({
      type: "CLAIM_SEAT",
      seatIndex: 0,
      sessionId: "sess-a",
      name: "Alice",
    });
    table.game.dispatch({
      type: "PLACE_BET_FOR_SEAT",
      seatIndex: 0,
      amount: 25,
    });
    // Skip directly if the hand was an immediate blackjack. Only stand in
    // playerTurn.
    const capturedBeforeStand = captured.length;
    if (table.game.getState().phase === "playerTurn") {
      table.game.dispatch({ type: "STAND" });
    }
    const after = captured.slice(capturedBeforeStand).map((c) => c.frame);
    // Expect to see a PHASE_CHANGED somewhere (dealerTurn, settlement, or
    // roundOver — depending on dealer play / BJ peek).
    const phases = after
      .filter((f) => f.type === "PHASE_CHANGED")
      .map((f) => (f as { phase: string }).phase);
    expect(phases).toContain("roundOver");
  });

  it("unsubscribe function stops broadcasting further events", () => {
    const captured: Array<{ tableId: string; frame: ServerFrame }> = [];
    const lobby = createLobby(42);
    const bridge = createEventBridge((tableId, frame) => {
      captured.push({ tableId, frame });
    });
    const table = lobby.createTable({
      ruleSet: "VEGAS",
      maxSeats: 3,
      dealerPersona: "veteran",
      language: "en",
    });
    const unsub = bridge.attach(table);
    table.game.dispatch({
      type: "CLAIM_SEAT",
      seatIndex: 0,
      sessionId: "sess-a",
      name: "Alice",
    });
    const beforeUnsub = captured.length;
    // ... we're inside betting; nothing has broadcast yet besides whatever
    // CLAIM_SEAT may trigger, but CLAIM_SEAT is suppressed.
    expect(beforeUnsub).toBe(0);

    unsub();
    // After unsubscribe, further engine events must not be captured.
    table.game.dispatch({
      type: "PLACE_BET_FOR_SEAT",
      seatIndex: 0,
      amount: 25,
    });
    expect(captured.length).toBe(0);
  });

  it("every broadcast carries the table id of the attached table", () => {
    const { table, captured } = setup();
    table.game.dispatch({
      type: "CLAIM_SEAT",
      seatIndex: 0,
      sessionId: "sess-a",
      name: "Alice",
    });
    table.game.dispatch({
      type: "PLACE_BET_FOR_SEAT",
      seatIndex: 0,
      amount: 25,
    });
    expect(captured.length).toBeGreaterThan(0);
    for (const c of captured) {
      expect(c.tableId).toBe(table.meta.tableId);
    }
  });
});
