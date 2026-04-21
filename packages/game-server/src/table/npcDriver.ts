/**
 * NpcDriver (M4c) — auto-drives NPC seats via @blackjack/ai-npc.
 *
 * Responsibilities:
 *  - Subscribe to a table's engine events.
 *  - Maintain a per-table Hi-Lo CounterState, fed every face-up CARD_DEALT.
 *  - On entering "betting": schedule one auto-bet per NPC seat (staggered).
 *  - On entering/advancing "playerTurn": if the active seat is an NPC,
 *    schedule an auto-play decision; dispatch HIT/STAND/DOUBLE/SPLIT/SURRENDER.
 *  - On entering "insurance": if the active seat is an NPC, decline insurance
 *    after a short delay. (Engine currently routes insurance to humanSeatIndex
 *    only, per D-023; dispatching DECLINE is a safe no-op if already declined.)
 *
 * Timer management:
 *  - Every scheduled timer is registered in a per-table Set so we can clear
 *    the lot on unsubscribe, or when the phase changes to something that
 *    invalidates pending work (e.g. a CONFIGURE_TABLE mid-flight sends us
 *    back to betting with a fresh seat layout).
 *
 * CONFIGURE_TABLE gotcha:
 *  - The engine's CONFIGURE_TABLE action rewrites the seat array but does
 *    NOT emit a PHASE_CHANGED or any other signal. Since we subscribe to
 *    engine events only, the driver can't auto-detect the layout change.
 *    `notifyTableConfigured(table)` is exposed for the dispatch layer to
 *    call after handling a CONFIGURE_TABLE frame; it nudges the driver to
 *    re-scan the seats and schedule bets / plays.
 *
 * Determinism:
 *  - The NPC agent is seeded. We use a monotonically-increasing counter per
 *    driver instance XOR'd with the seat index so repeat decisions on the
 *    same seat don't reuse the same noise roll. (Tests can use fake timers
 *    to make the whole pipeline deterministic end-to-end.)
 *
 * Out of scope:
 *  - Dealer-ai / TTS hooks (later milestone).
 *  - Per-seat insurance routing for multi-NPC tables (engine-side D-023).
 */
import type { Card, EngineEvent, Seat, HandResult } from "@blackjack/engine";
import { isPair } from "@blackjack/engine";
import {
  npcDecideBet,
  npcDecidePlay,
  newCounter,
  observe,
  updateTilt,
  passiveDecay,
  PERSONALITIES,
  type CounterState,
} from "@blackjack/ai-npc";

import type { Table } from "../lobby/table.js";
import { log } from "../log.js";

export interface NpcDriver {
  /** Attach to a table: subscribe to engine events and auto-drive NPC seats. Returns an unsubscribe. */
  attach(table: Table): () => void;
  /**
   * Signal that a table's seat layout may have changed in a way the engine
   * did NOT emit an event for (notably: CONFIGURE_TABLE during betting).
   * The driver re-inspects the current phase and schedules auto-bets /
   * auto-plays as appropriate. No-op if no attach is active for this table.
   */
  notifyTableConfigured(table: Table): void;
  /**
   * Test-inspection helper: read the tracked tilt for an NPC seat on a table.
   * Returns `undefined` if the driver isn't attached to the table or the seat
   * has no tracked tilt entry.
   */
  getSeatTilt(table: Table, seatIndex: number): number | undefined;
}

export interface NpcDriverOptions {
  /** Delay between NPC bets during the betting phase (staggered). Default 600ms. */
  betDelayMs?: number;
  /** Delay before an NPC plays during a playerTurn. Default 700ms. */
  playDelayMs?: number;
  /** Injectable for tests; defaults to global setTimeout. */
  setTimeoutFn?: typeof setTimeout;
  /** Injectable for tests; defaults to global clearTimeout. */
  clearTimeoutFn?: typeof clearTimeout;
}

/** Default timing knobs — exported so tests can assert expected deadlines. */
export const DEFAULT_BET_DELAY_MS = 600;
export const DEFAULT_PLAY_DELAY_MS = 700;

/** Per-table driver state; one instance per `attach` call. */
interface TableDriver {
  rescanAndSchedule: () => void;
  detach: () => void;
  tilts: Map<number, number>;
}

export function createNpcDriver(opts: NpcDriverOptions = {}): NpcDriver {
  const betDelayMs = opts.betDelayMs ?? DEFAULT_BET_DELAY_MS;
  const playDelayMs = opts.playDelayMs ?? DEFAULT_PLAY_DELAY_MS;
  const setTimeoutFn = opts.setTimeoutFn ?? setTimeout;
  const clearTimeoutFn = opts.clearTimeoutFn ?? clearTimeout;

  // Map tableId → per-table driver state so external callers (dispatch.ts)
  // can look us up by table for out-of-band notifications.
  const drivers = new Map<string, TableDriver>();

  function attachInner(table: Table): TableDriver {
    // ------------------------------------------------------------------
    // Per-table state
    // ------------------------------------------------------------------
    const rules0 = table.game.getState().ruleSet;
    let counter: CounterState = newCounter(rules0.decks);

    // All pending timers for this table, so we can clear them on unsub or
    // on an invalidating state change (e.g. CONFIGURE_TABLE resets seats).
    const pending: Set<ReturnType<typeof setTimeout>> = new Set();

    // Monotonic seed so repeat NPC decisions (e.g. after a HIT) don't reuse
    // the exact same seeded roll. Seat index is folded into the seed at
    // call-time to further decorrelate seats.
    let decisionCounter = 0;
    const nextSeed = (seatIndex: number): number => {
      decisionCounter = (decisionCounter + 1) | 0;
      const rnd = Math.floor(Math.random() * 2 ** 31);
      return (rnd ^ (decisionCounter * 2654435761) ^ (seatIndex * 0x9e3779b1)) | 0;
    };

    // Guard against "we just scheduled a bet for this seat in this betting
    // round" so PHASE_CHANGED→betting re-entries don't double-schedule.
    let betRoundToken = 0;
    const betsScheduledThisRound: Set<number> = new Set();

    // Track whether a play-decision is already scheduled for the currently
    // active NPC seat, so rapid-fire engine events (PHASE_CHANGED +
    // PLAYER_ACTION) don't queue duplicates.
    let playScheduled = false;

    // Insurance: fire at most once per insurance phase.
    let insuranceScheduled = false;

    // --------------------------------------------------------------
    // Tilt tracking (M12, Part A).
    //
    // The engine's getState() returns deep-copied seat snapshots, so
    // mutating `seat.tilt` on a snapshot has no effect on subsequent
    // reads. Instead we maintain an in-driver tilt map keyed by seat
    // index. Decision calls should consult this map (falling back to 0)
    // rather than the seat snapshot's `tilt` field.
    //
    // Lifecycle:
    //   - BET_SETTLED: buffer per-seat aggregate for this round
    //   - ROUND_OVER:  apply updateTilt() per NPC seat, clear buffer
    //   - PHASE_CHANGED → betting: apply passiveDecay() per NPC seat
    //   - SEAT_RELEASED / RULESET_CHANGED: clear the affected entries
    // --------------------------------------------------------------
    const tilts = new Map<number, number>();

    interface SeatRoundBuffer {
      outcome: HandResult["outcome"];
      netDelta: number; // aggregated payout - bet across all hands
      bigLoss: boolean; // retained the worst single-hand netDelta magnitude
    }
    // seatIndex -> accumulated hand settlement summary for the current round
    const roundBuffer = new Map<number, SeatRoundBuffer>();
    // Outcome priority for aggregation across split hands — pick the most
    // emotionally "loud" outcome when one seat settles multiple hands.
    const outcomePriority: Record<HandResult["outcome"], number> = {
      bust: 5,
      surrender: 4,
      loss: 3,
      push: 2,
      win: 1,
      blackjack: 0,
    };
    const recordSettlement = (
      seatIndex: number,
      outcome: HandResult["outcome"],
      bet: number,
      payout: number,
    ): void => {
      const netDelta = payout - bet;
      const existing = roundBuffer.get(seatIndex);
      if (!existing) {
        roundBuffer.set(seatIndex, {
          outcome,
          netDelta,
          bigLoss: netDelta < 0,
        });
        return;
      }
      existing.netDelta += netDelta;
      if (outcomePriority[outcome] > outcomePriority[existing.outcome]) {
        existing.outcome = outcome;
      }
    };

    const applyTiltsForRound = (): void => {
      const snap = table.game.getState();
      for (const s of snap.seats) {
        if (s.player.kind !== "npc") continue;
        const buf = roundBuffer.get(s.index);
        if (!buf) continue;
        const personalityId = s.player.personality ?? "optimal";
        const cfg = PERSONALITIES[personalityId];
        const unit = snap.ruleSet.minBet * cfg.betUnitMultiplier;
        const current = tilts.get(s.index) ?? 0;
        const next = updateTilt(current, buf.outcome, buf.netDelta, unit, {
          sensitivity: cfg.tiltSensitivity,
        });
        tilts.set(s.index, next);
      }
      roundBuffer.clear();
    };

    const applyPassiveDecayForBetting = (): void => {
      const snap = table.game.getState();
      for (const s of snap.seats) {
        if (s.player.kind !== "npc") continue;
        const current = tilts.get(s.index);
        if (current === undefined) continue;
        const personalityId = s.player.personality ?? "optimal";
        const cfg = PERSONALITIES[personalityId];
        tilts.set(
          s.index,
          passiveDecay(current, { sensitivity: cfg.tiltSensitivity }),
        );
      }
    };

    // ------------------------------------------------------------------
    // Timer helpers
    // ------------------------------------------------------------------
    const schedule = (fn: () => void, ms: number): void => {
      const handle = setTimeoutFn(() => {
        pending.delete(handle);
        try {
          fn();
        } catch (err) {
          log.error(
            { err, tableId: table.meta.tableId },
            "npcDriver: scheduled callback threw",
          );
        }
      }, ms);
      pending.add(handle);
    };

    const clearAllPending = (): void => {
      for (const h of pending) clearTimeoutFn(h);
      pending.clear();
    };

    // ------------------------------------------------------------------
    // Betting phase
    // ------------------------------------------------------------------
    const scheduleNpcBetsForBetting = (): void => {
      const snap = table.game.getState();
      if (snap.phase !== "betting") return;
      const myToken = betRoundToken;
      let stagger = 0;
      for (const s of snap.seats) {
        if (s.player.kind !== "npc") continue;
        if (s.pendingBet > 0) continue;
        if (betsScheduledThisRound.has(s.index)) continue;
        betsScheduledThisRound.add(s.index);
        stagger += 1;
        const seatIdx = s.index;
        const delay = betDelayMs * stagger;
        schedule(() => {
          if (betRoundToken !== myToken) return;
          const now = table.game.getState();
          if (now.phase !== "betting") return;
          const seat = now.seats[seatIdx];
          if (!seat || seat.player.kind !== "npc") return;
          if (seat.pendingBet > 0) return;
          const personality = seat.player.personality ?? "optimal";
          let amount: number;
          try {
            amount = npcDecideBet(
              {
                seat,
                rules: now.ruleSet,
                counter,
                currentBet: 0,
                streak: 0,
              },
              personality,
              nextSeed(seatIdx),
            );
          } catch (err) {
            log.error(
              { err, tableId: table.meta.tableId, seatIdx },
              "npcDriver: npcDecideBet threw",
            );
            return;
          }
          if (amount < now.ruleSet.minBet) return;
          if (amount > seat.player.bankroll) return;
          table.game.dispatch({
            type: "PLACE_BET_FOR_SEAT",
            seatIndex: seatIdx,
            amount,
          });
        }, delay);
      }
    };

    // ------------------------------------------------------------------
    // Play phase
    // ------------------------------------------------------------------
    const scheduleNpcPlayIfActive = (): void => {
      if (playScheduled) return;
      const snap = table.game.getState();
      if (snap.phase !== "playerTurn") return;
      const seat = snap.seats[snap.activeSeatIndex];
      if (!seat || seat.player.kind !== "npc") return;
      playScheduled = true;
      const seatIdx = seat.index;
      schedule(() => {
        playScheduled = false;
        const now = table.game.getState();
        if (now.phase !== "playerTurn") return;
        if (now.activeSeatIndex !== seatIdx) return;
        const liveSeat = now.seats[seatIdx];
        if (!liveSeat || liveSeat.player.kind !== "npc") return;
        const hand = liveSeat.hands[liveSeat.activeHandIndex];
        if (!hand) return;
        const dealerUp: Card | undefined = now.dealer[0];
        if (!dealerUp) return;
        const rules = now.ruleSet;
        const cards = hand.cards;
        const canDouble =
          cards.length === 2 &&
          !hand.splitFromAces &&
          liveSeat.player.bankroll >= hand.bet;
        const canSplit =
          cards.length === 2 &&
          isPair(cards) &&
          liveSeat.hands.length - 1 < rules.maxSplits &&
          liveSeat.player.bankroll >= hand.bet;
        const canSurrender =
          rules.allowSurrender &&
          liveSeat.hands.length === 1 &&
          cards.length === 2;
        const personality = liveSeat.player.personality ?? "optimal";
        let action: ReturnType<typeof npcDecidePlay>;
        try {
          action = npcDecidePlay(
            {
              seat: liveSeat,
              dealerUp,
              rules,
              counter,
              canDouble,
              canSplit,
              canSurrender,
            },
            personality,
            nextSeed(seatIdx),
          );
        } catch (err) {
          log.error(
            { err, tableId: table.meta.tableId, seatIdx },
            "npcDriver: npcDecidePlay threw",
          );
          return;
        }
        switch (action) {
          case "hit":
            table.game.dispatch({ type: "HIT" });
            break;
          case "stand":
            table.game.dispatch({ type: "STAND" });
            break;
          case "double":
            table.game.dispatch({ type: "DOUBLE" });
            break;
          case "split":
            table.game.dispatch({ type: "SPLIT" });
            break;
          case "surrender":
            table.game.dispatch({ type: "SURRENDER" });
            break;
        }
        // After dispatching, the engine may have silently advanced the
        // active seat to another NPC (no explicit event is emitted when
        // `advanceHand` moves between seats). Re-check so multi-NPC tables
        // flow without an external nudge.
        const afterDispatch = table.game.getState();
        if (afterDispatch.phase === "playerTurn") {
          scheduleNpcPlayIfActive();
        }
      }, playDelayMs);
    };

    // ------------------------------------------------------------------
    // Insurance phase
    // ------------------------------------------------------------------
    const scheduleNpcInsuranceDecline = (): void => {
      if (insuranceScheduled) return;
      const snap = table.game.getState();
      if (snap.phase !== "insurance") return;
      const humanIdx = snap.humanSeatIndex;
      const activeSeat = snap.seats[snap.activeSeatIndex];
      const shouldDrive =
        humanIdx === null ||
        (activeSeat !== undefined && activeSeat.player.kind === "npc");
      if (!shouldDrive) return;
      insuranceScheduled = true;
      schedule(() => {
        const now = table.game.getState();
        if (now.phase !== "insurance") return;
        table.game.dispatch({ type: "DECLINE_INSURANCE" });
      }, playDelayMs);
    };

    /**
     * Re-scan the table and schedule whatever is appropriate for the
     * current phase. Called from:
     *  - attach-time initial sync
     *  - notifyTableConfigured (dispatch.ts CONFIGURE_TABLE handler)
     */
    const rescanAndSchedule = (): void => {
      const snap = table.game.getState();
      if (snap.phase === "betting") {
        // Reset per-round bookkeeping; any prior schedule was for a
        // different seat layout.
        betRoundToken++;
        betsScheduledThisRound.clear();
        clearAllPending();
        scheduleNpcBetsForBetting();
      } else if (snap.phase === "playerTurn") {
        playScheduled = false;
        scheduleNpcPlayIfActive();
      } else if (snap.phase === "insurance") {
        insuranceScheduled = false;
        scheduleNpcInsuranceDecline();
      }
    };

    // ------------------------------------------------------------------
    // Engine event listener
    // ------------------------------------------------------------------
    const unsubscribe = table.game.on((ev: EngineEvent) => {
      try {
        handleEvent(ev);
      } catch (err) {
        log.error(
          { err, tableId: table.meta.tableId, evType: ev.type },
          "npcDriver: handler threw",
        );
      }
    });

    function handleEvent(ev: EngineEvent): void {
      switch (ev.type) {
        case "CARD_DEALT": {
          if (!ev.faceDown) {
            counter = observe(counter, ev.card);
          }
          return;
        }

        case "HOLE_CARD_REVEALED": {
          // The hole card was dealt face-down (not counted at deal-time).
          // Now that it's revealed, feed it into the counter.
          counter = observe(counter, ev.card);
          return;
        }

        case "SHOE_SHUFFLED": {
          const snap = table.game.getState();
          counter = newCounter(snap.ruleSet.decks);
          return;
        }

        case "RULESET_CHANGED": {
          const snap = table.game.getState();
          counter = newCounter(snap.ruleSet.decks);
          betRoundToken++;
          betsScheduledThisRound.clear();
          clearAllPending();
          return;
        }

        case "PHASE_CHANGED": {
          if (ev.phase === "betting") {
            betRoundToken++;
            betsScheduledThisRound.clear();
            clearAllPending();
            // Passive tilt decay while the table was idle between rounds.
            applyPassiveDecayForBetting();
            scheduleNpcBetsForBetting();
            return;
          }
          if (ev.phase === "insurance") {
            insuranceScheduled = false;
            scheduleNpcInsuranceDecline();
            return;
          }
          if (ev.phase === "playerTurn") {
            playScheduled = false;
            scheduleNpcPlayIfActive();
            return;
          }
          // Any other phase (dealing, dealerTurn, settlement, roundOver):
          // cancel pending work.
          clearAllPending();
          playScheduled = false;
          insuranceScheduled = false;
          return;
        }

        case "BET_SETTLED": {
          // Find the seatIndex + per-hand bet from the live engine state.
          // BET_SETTLED fires during settlement; the hand's `bet` field is
          // still readable from the snapshot because the engine writes the
          // HandResult before advancing (see game.ts settlement loop).
          const snap = table.game.getState();
          let matched = false;
          for (const s of snap.seats) {
            if (s.player.kind !== "npc") continue;
            const hand = s.hands[ev.handIndex];
            if (!hand) continue;
            // Multiple seats can share a handIndex; prefer the one whose
            // roundResults already lists this handIndex as its own.
            const result = snap.roundResults.find(
              (r) => r.handIndex === ev.handIndex && r.seatIndex === s.index,
            );
            if (!result) continue;
            recordSettlement(s.index, ev.outcome, hand.bet, ev.payout);
            matched = true;
            break;
          }
          // Fallback: if no HandResult mapping exists yet (ordering edge
          // case), just attribute to any NPC seat holding this handIndex.
          if (!matched) {
            for (const s of snap.seats) {
              if (s.player.kind !== "npc") continue;
              const hand = s.hands[ev.handIndex];
              if (!hand) continue;
              recordSettlement(s.index, ev.outcome, hand.bet, ev.payout);
              break;
            }
          }
          return;
        }

        case "ROUND_OVER": {
          // Use the engine's own HandResult list as the source of truth —
          // it carries seatIndex directly and survives snapshot copying.
          for (const r of ev.results) {
            if (r.seatIndex === undefined) continue;
            const snap = table.game.getState();
            const seat = snap.seats[r.seatIndex];
            if (!seat || seat.player.kind !== "npc") continue;
            const hand = seat.hands[r.handIndex];
            const bet = hand?.bet ?? 0;
            recordSettlement(r.seatIndex, r.outcome, bet, r.payout);
          }
          applyTiltsForRound();
          return;
        }

        case "SEAT_RELEASED": {
          tilts.delete(ev.seatIndex);
          roundBuffer.delete(ev.seatIndex);
          return;
        }

        case "SEAT_CLAIMED": {
          // Starting a seat from a clean slate. If an NPC was previously at
          // this seat, its tilt bookkeeping shouldn't follow a new occupant.
          tilts.delete(ev.seatIndex);
          roundBuffer.delete(ev.seatIndex);
          return;
        }

        case "PLAYER_ACTION":
        case "HAND_BUST":
        case "NATURAL_BLACKJACK": {
          // These events fire BEFORE the engine's synchronous
          // `advanceHand` completes, so `activeSeatIndex` may still point
          // at the acting seat. Queue a 0-ms check so the state is
          // allowed to settle (advanceHand may move the active seat to
          // another NPC without emitting another event) before we look.
          schedule(() => {
            const snap = table.game.getState();
            if (snap.phase === "playerTurn") {
              scheduleNpcPlayIfActive();
            }
          }, 0);
          return;
        }

        default:
          return;
      }
    }

    // Initial sync for defensive edge cases.
    rescanAndSchedule();

    const detach = (): void => {
      clearAllPending();
      unsubscribe();
      tilts.clear();
      roundBuffer.clear();
    };

    return { rescanAndSchedule, detach, tilts };
  }

  return {
    attach(table: Table): () => void {
      const driver = attachInner(table);
      drivers.set(table.meta.tableId, driver);
      return (): void => {
        driver.detach();
        // Only drop from the map if it still refers to *this* driver
        // (a subsequent attach would have overwritten it).
        if (drivers.get(table.meta.tableId) === driver) {
          drivers.delete(table.meta.tableId);
        }
      };
    },

    notifyTableConfigured(table: Table): void {
      const driver = drivers.get(table.meta.tableId);
      if (!driver) return;
      driver.rescanAndSchedule();
    },

    getSeatTilt(table: Table, seatIndex: number): number | undefined {
      const driver = drivers.get(table.meta.tableId);
      if (!driver) return undefined;
      return driver.tilts.get(seatIndex);
    },
  };
}

// Re-export the Seat type so callers don't have to import from @blackjack/engine
// just to typecheck internal option-wiring. (Low cost; keeps call sites tidy.)
export type { Seat };
