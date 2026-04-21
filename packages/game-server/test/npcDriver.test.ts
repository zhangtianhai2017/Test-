/**
 * Unit tests for the NpcDriver (M4c).
 *
 * These run without WebSockets; they drive the engine directly via
 * `createTable().game.dispatch(...)` and observe the NPC driver's reactions
 * under fake timers. The driver reacts to engine events synchronously
 * (subscribe + schedule), then waits `betDelayMs` / `playDelayMs` before
 * dispatching — `vi.advanceTimersByTime` lets us make that wait deterministic.
 *
 * Coverage:
 *  1. During betting, each NPC seat gets a staggered auto-bet.
 *  2. A full 1-human + 2-NPC round runs to `roundOver` with only one
 *     external human STAND input. Each seat produces exactly one
 *     HandResult.
 *  3. The per-table counter observes dealt cards (spy on npcDecideBet).
 *  4. Unsubscribe cancels still-pending timers.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { createLobby } from "../src/lobby/lobby.js";
import { createNpcDriver } from "../src/table/npcDriver.js";
import type { Table } from "../src/lobby/table.js";

// We need to spy on npcDecideBet/npcDecidePlay in one of the tests. vitest
// module-mock is the cleanest way to do that across the sibling workspace.
import * as aiNpc from "@blackjack/ai-npc";

/** Configure 1 human (seat 0) + 2 NPCs (seats 1, 2) via CONFIGURE_TABLE. */
function configure1H2N(table: Table): void {
  table.game.dispatch({
    type: "CONFIGURE_TABLE",
    config: {
      seats: [
        { kind: "human", name: "Alice", bankroll: 1000 },
        { kind: "npc", name: "Bot-1", personality: "optimal", bankroll: 1000 },
        { kind: "npc", name: "Bot-2", personality: "optimal", bankroll: 1000 },
      ],
    },
  });
}

describe("NpcDriver (M4c)", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("auto-bets during betting phase for every NPC seat", () => {
    const lobby = createLobby(7);
    const table = lobby.createTable({
      ruleSet: "VEGAS",
      maxSeats: 4,
      dealerPersona: "veteran",
      language: "en",
    });
    const driver = createNpcDriver({ betDelayMs: 100, playDelayMs: 100 });
    const detach = driver.attach(table);
    try {
      configure1H2N(table);
      // CONFIGURE_TABLE doesn't emit an engine event, so we nudge the driver
      // to re-scan (mirrors what dispatch.ts does in production).
      driver.notifyTableConfigured(table);

      expect(table.game.getState().seats[1]!.pendingBet).toBe(0);
      expect(table.game.getState().seats[2]!.pendingBet).toBe(0);

      // Advance past the first stagger (seat 1's bet at 100ms).
      vi.advanceTimersByTime(150);
      expect(table.game.getState().seats[1]!.pendingBet).toBeGreaterThan(0);
      expect(table.game.getState().phase).toBe("betting");

      // Advance past the second stagger (seat 2's bet at 200ms).
      vi.advanceTimersByTime(150);
      expect(table.game.getState().seats[2]!.pendingBet).toBeGreaterThan(0);
      expect(table.game.getState().phase).toBe("betting");
    } finally {
      detach();
    }
  });

  it("runs a full 1-human + 2-NPC round to roundOver with one human STAND", () => {
    const lobby = createLobby(7);
    const table = lobby.createTable({
      ruleSet: "VEGAS",
      maxSeats: 4,
      dealerPersona: "veteran",
      language: "en",
    });
    const driver = createNpcDriver({ betDelayMs: 50, playDelayMs: 50 });
    const detach = driver.attach(table);
    try {
      configure1H2N(table);
      driver.notifyTableConfigured(table);

      // Advance timers to let NPCs auto-bet.
      vi.advanceTimersByTime(300);
      expect(table.game.getState().seats[1]!.pendingBet).toBeGreaterThan(0);
      expect(table.game.getState().seats[2]!.pendingBet).toBeGreaterThan(0);

      // Human places bet — this completes the betting set and deals.
      table.game.dispatch({
        type: "PLACE_BET_FOR_SEAT",
        seatIndex: 0,
        amount: 25,
      });

      // Loop: advance a small slice at a time, dispatch human STAND when
      // it's the human's turn, until we hit roundOver.
      const maxTicks = 200;
      for (let tick = 0; tick < maxTicks; tick++) {
        const snap = table.game.getState();
        if (snap.phase === "roundOver") break;
        if (
          snap.phase === "playerTurn" &&
          snap.activeSeatIndex === 0 &&
          snap.seats[0]!.player.kind === "human"
        ) {
          table.game.dispatch({ type: "STAND" });
          continue;
        }
        vi.advanceTimersByTime(60);
      }

      const finalSnap = table.game.getState();
      expect(finalSnap.phase).toBe("roundOver");
      const seatIdxsInResults = new Set(
        finalSnap.roundResults.map((r) => r.seatIndex),
      );
      expect(seatIdxsInResults.has(0)).toBe(true);
      expect(seatIdxsInResults.has(1)).toBe(true);
      expect(seatIdxsInResults.has(2)).toBe(true);
    } finally {
      detach();
    }
  });

  it("feeds dealt cards into the CounterState passed to npcDecideBet", () => {
    // Spy on npcDecideBet. We want to see that once a full round has played
    // out (cards dealt, counter observed), a subsequent NEW_ROUND + betting
    // phase passes a counter with cardsSeen > 0 into npcDecideBet.
    const spy = vi.spyOn(aiNpc, "npcDecideBet");

    const lobby = createLobby(7);
    const table = lobby.createTable({
      ruleSet: "VEGAS",
      maxSeats: 4,
      dealerPersona: "veteran",
      language: "en",
    });
    const driver = createNpcDriver({ betDelayMs: 50, playDelayMs: 50 });
    const detach = driver.attach(table);
    try {
      configure1H2N(table);
      driver.notifyTableConfigured(table);

      // Round 1.
      vi.advanceTimersByTime(300);
      table.game.dispatch({
        type: "PLACE_BET_FOR_SEAT",
        seatIndex: 0,
        amount: 25,
      });
      for (let tick = 0; tick < 200; tick++) {
        const snap = table.game.getState();
        if (snap.phase === "roundOver") break;
        if (
          snap.phase === "playerTurn" &&
          snap.activeSeatIndex === 0 &&
          snap.seats[0]!.player.kind === "human"
        ) {
          table.game.dispatch({ type: "STAND" });
          continue;
        }
        vi.advanceTimersByTime(60);
      }
      expect(table.game.getState().phase).toBe("roundOver");

      const round1Calls = spy.mock.calls.length;
      expect(round1Calls).toBeGreaterThan(0);

      // Round 2 — the driver will call npcDecideBet again; the counter
      // now carries the round-1 observations.
      table.game.dispatch({ type: "NEW_ROUND" });
      vi.advanceTimersByTime(300);

      const round2Calls = spy.mock.calls.slice(round1Calls);
      expect(round2Calls.length).toBeGreaterThan(0);
      const first = round2Calls[0]!;
      const counterArg = first[0]!.counter;
      expect(counterArg).toBeDefined();
      expect(counterArg!.cardsSeen).toBeGreaterThan(0);
    } finally {
      detach();
    }
  });

  it("auto-declines insurance when the active seat is an NPC (and eventually advances phase)", () => {
    // Build an all-NPC table; with no human, humanSeatIndex === null and
    // the driver should drive DECLINE_INSURANCE if the engine peeks. We
    // don't force a specific shoe here — the invariant is just that the
    // driver doesn't leave the engine stuck in insurance.
    const lobby = createLobby(1);
    const table = lobby.createTable({
      ruleSet: "VEGAS",
      maxSeats: 3,
      dealerPersona: "veteran",
      language: "en",
    });
    const driver = createNpcDriver({ betDelayMs: 10, playDelayMs: 10 });
    const detach = driver.attach(table);
    try {
      table.game.dispatch({
        type: "CONFIGURE_TABLE",
        config: {
          seats: [
            { kind: "npc", name: "Bot-A", personality: "optimal", bankroll: 1000 },
            { kind: "npc", name: "Bot-B", personality: "optimal", bankroll: 1000 },
          ],
        },
      });
      driver.notifyTableConfigured(table);

      // Iterate through several rounds; between each, advance timers so the
      // driver has a chance to act on betting / insurance / playerTurn.
      for (let round = 0; round < 5; round++) {
        for (let tick = 0; tick < 400; tick++) {
          const snap = table.game.getState();
          if (snap.phase === "roundOver") break;
          vi.advanceTimersByTime(30);
        }
        const snap = table.game.getState();
        // Invariant: we must never be stuck in insurance after settling.
        expect(snap.phase).not.toBe("insurance");
        if (snap.phase === "roundOver") {
          table.game.dispatch({ type: "NEW_ROUND" });
        } else {
          break;
        }
      }
    } finally {
      detach();
    }
  });

  it("tracks tilt after round settlement for an NPC seat", () => {
    // Chaser personality has non-zero tiltSensitivity so losses do bump.
    const lobby = createLobby(7);
    const table = lobby.createTable({
      ruleSet: "VEGAS",
      maxSeats: 3,
      dealerPersona: "veteran",
      language: "en",
    });
    const driver = createNpcDriver({ betDelayMs: 20, playDelayMs: 20 });
    const detach = driver.attach(table);
    try {
      table.game.dispatch({
        type: "CONFIGURE_TABLE",
        config: {
          seats: [
            { kind: "human", name: "Alice", bankroll: 1000 },
            { kind: "npc", name: "Bot-1", personality: "chaser", bankroll: 1000 },
          ],
        },
      });
      driver.notifyTableConfigured(table);

      // Before any round has settled, tilt tracking has no entry.
      expect(driver.getSeatTilt(table, 1)).toBeUndefined();

      // Run rounds until we observe either a loss or a win — chaser has
      // nonzero tilt sensitivity, so any non-push outcome moves tilt.
      let rounds = 0;
      let tiltChanged = false;
      while (rounds < 10 && !tiltChanged) {
        rounds++;
        // Advance bets.
        vi.advanceTimersByTime(300);
        table.game.dispatch({
          type: "PLACE_BET_FOR_SEAT",
          seatIndex: 0,
          amount: 25,
        });
        for (let tick = 0; tick < 300; tick++) {
          const snap = table.game.getState();
          if (snap.phase === "roundOver") break;
          if (
            snap.phase === "playerTurn" &&
            snap.activeSeatIndex === 0 &&
            snap.seats[0]!.player.kind === "human"
          ) {
            table.game.dispatch({ type: "STAND" });
            continue;
          }
          vi.advanceTimersByTime(30);
        }
        // After ROUND_OVER, tilt should be recorded (even at 0 after a win).
        const tilt = driver.getSeatTilt(table, 1);
        expect(tilt).toBeDefined();
        if (tilt !== undefined && tilt > 0) {
          tiltChanged = true;
        }
        table.game.dispatch({ type: "NEW_ROUND" });
      }
      expect(tiltChanged).toBe(true);
    } finally {
      detach();
    }
  });

  it("decays tilt on idle between rounds via passiveDecay at betting phase", () => {
    // Drive to a state where a chaser seat has tilt > 0, then verify the
    // next betting-phase entry applies passiveDecay.
    const lobby = createLobby(7);
    const table = lobby.createTable({
      ruleSet: "VEGAS",
      maxSeats: 3,
      dealerPersona: "veteran",
      language: "en",
    });
    const driver = createNpcDriver({ betDelayMs: 20, playDelayMs: 20 });
    const detach = driver.attach(table);
    try {
      table.game.dispatch({
        type: "CONFIGURE_TABLE",
        config: {
          seats: [
            { kind: "human", name: "Alice", bankroll: 1000 },
            { kind: "npc", name: "Bot-1", personality: "chaser", bankroll: 1000 },
          ],
        },
      });
      driver.notifyTableConfigured(table);

      // Build up tilt by running rounds until seat 1 has tilt > 0.05.
      let guard = 0;
      while ((driver.getSeatTilt(table, 1) ?? 0) < 0.05 && guard < 20) {
        guard++;
        vi.advanceTimersByTime(300);
        table.game.dispatch({
          type: "PLACE_BET_FOR_SEAT",
          seatIndex: 0,
          amount: 25,
        });
        for (let tick = 0; tick < 300; tick++) {
          const snap = table.game.getState();
          if (snap.phase === "roundOver") break;
          if (
            snap.phase === "playerTurn" &&
            snap.activeSeatIndex === 0 &&
            snap.seats[0]!.player.kind === "human"
          ) {
            table.game.dispatch({ type: "STAND" });
            continue;
          }
          vi.advanceTimersByTime(30);
        }
        if (table.game.getState().phase === "roundOver") {
          // Don't dispatch NEW_ROUND on the very last iteration so we can
          // assert the pre-decay value; if we need more tilt, keep looping.
          if ((driver.getSeatTilt(table, 1) ?? 0) < 0.05) {
            table.game.dispatch({ type: "NEW_ROUND" });
          }
        }
      }

      const before = driver.getSeatTilt(table, 1) ?? 0;
      expect(before).toBeGreaterThan(0);

      // Starting a new round emits PHASE_CHANGED→betting, which applies decay.
      table.game.dispatch({ type: "NEW_ROUND" });
      const after = driver.getSeatTilt(table, 1) ?? 0;
      expect(after).toBeLessThan(before);
    } finally {
      detach();
    }
  });

  it("drops tilt tracking on SEAT_RELEASED", () => {
    const lobby = createLobby(7);
    const table = lobby.createTable({
      ruleSet: "VEGAS",
      maxSeats: 3,
      dealerPersona: "veteran",
      language: "en",
    });
    const driver = createNpcDriver({ betDelayMs: 20, playDelayMs: 20 });
    const detach = driver.attach(table);
    try {
      table.game.dispatch({
        type: "CONFIGURE_TABLE",
        config: {
          seats: [
            { kind: "human", name: "Alice", bankroll: 1000 },
            { kind: "npc", name: "Bot-1", personality: "chaser", bankroll: 1000 },
          ],
        },
      });
      driver.notifyTableConfigured(table);

      // Run one round to populate the tilt entry.
      vi.advanceTimersByTime(300);
      table.game.dispatch({
        type: "PLACE_BET_FOR_SEAT",
        seatIndex: 0,
        amount: 25,
      });
      for (let tick = 0; tick < 300; tick++) {
        const snap = table.game.getState();
        if (snap.phase === "roundOver") break;
        if (
          snap.phase === "playerTurn" &&
          snap.activeSeatIndex === 0 &&
          snap.seats[0]!.player.kind === "human"
        ) {
          table.game.dispatch({ type: "STAND" });
          continue;
        }
        vi.advanceTimersByTime(30);
      }
      expect(driver.getSeatTilt(table, 1)).toBeDefined();

      // RELEASE_SEAT is only legal during the betting phase — return there
      // first by starting a new round.
      if (table.game.getState().phase === "roundOver") {
        table.game.dispatch({ type: "NEW_ROUND" });
      }
      expect(table.game.getState().phase).toBe("betting");

      // Release the seat (becomeNpc: false empties it → SEAT_RELEASED).
      table.game.dispatch({ type: "RELEASE_SEAT", seatIndex: 1 });
      expect(driver.getSeatTilt(table, 1)).toBeUndefined();
    } finally {
      detach();
    }
  });

  it("unsubscribe clears pending NPC bet timers", () => {
    const lobby = createLobby(7);
    const table = lobby.createTable({
      ruleSet: "VEGAS",
      maxSeats: 4,
      dealerPersona: "veteran",
      language: "en",
    });
    const driver = createNpcDriver({ betDelayMs: 200, playDelayMs: 200 });
    const detach = driver.attach(table);
    try {
      configure1H2N(table);
      driver.notifyTableConfigured(table);
      // A bet timer is pending for seat 1 (at 200ms) and seat 2 (at 400ms).
      vi.advanceTimersByTime(50);
      detach();
      // Now tick well past both delays; neither should fire.
      vi.advanceTimersByTime(1000);
      expect(table.game.getState().seats[1]!.pendingBet).toBe(0);
      expect(table.game.getState().seats[2]!.pendingBet).toBe(0);
    } finally {
      /* detach already called above */
    }
  });
});
