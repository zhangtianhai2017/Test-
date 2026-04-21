/**
 * Engine → wire event bridge (M4a).
 *
 * Subscribes to each `Table.game` event stream and fans the events out as
 * `ServerFrame` broadcasts to every session seated at the table. This is the
 * half of the M4 game-loop work that pushes state OUT of the engine; M4b
 * wires human action frames IN, and M4c drives NPC seats.
 *
 * Design notes:
 *  - The bridge is a thin, stateless-per-table translator: no engine logic
 *    lives here. If a given wire frame needs information the engine event
 *    does not directly carry, we read `table.game.getState()` inside the
 *    callback (all emissions are synchronous within `dispatch`, so the
 *    snapshot is consistent with the emission).
 *  - Hole-card secrecy (game-server AGENT.md §Key invariants): when
 *    `CARD_DEALT.faceDown === true` the emitted frame MUST NOT carry the
 *    `card` field. This is enforced by the protocol schema's `.superRefine`,
 *    but we also take care here to never construct one.
 *  - Per-table teardown: `attach` returns an unsubscribe function that the
 *    caller (dispatch or lobby on delete) must invoke to stop listening.
 *  - Some engine events do NOT directly carry `seatIndex` (`BET_SETTLED`,
 *    `NATURAL_BLACKJACK`, `HAND_BUST`, `PLAYER_ACTION`, `CARD_DEALT`
 *    to="player", `BANKROLL_CHANGED`, `SIDEBET_WIN`). We resolve seat in
 *    this order of preference:
 *      1. Tail of `state.roundResults` — authoritative during settlement
 *         (populated per M1c.4b with `HandResult.seatIndex`).
 *      2. `state.activeSeatIndex` — the engine advances active seat only
 *         after a hand's last action, so player-turn events point at the
 *         correct seat before that transition.
 *      3. For `BANKROLL_CHANGED`/`SIDEBET_WIN`: a per-seat cached bankroll
 *         map — the seat whose bankroll changed since the last observed
 *         value is the one this delta applies to. Only one seat's bankroll
 *         mutates per `adjustBankrollFor` call so this is unambiguous.
 *  - `SEAT_CLAIMED` / `SEAT_RELEASED` engine events are deliberately IGNORED
 *    here: `dispatch.ts` already broadcasts `SEAT_ASSIGNED` / `SEAT_RELEASED`
 *    wire frames with richer payload (playerName, bankroll). Mirroring them
 *    from the bridge would double-broadcast and cause clients to race.
 */
import type { EngineEvent, GameSnapshot } from "@blackjack/engine";

import type { Table } from "../lobby/table.js";
import { log } from "../log.js";
import { PROTOCOL_VERSION } from "../protocol/frames.js";
import type {
  BankrollChangedFrame,
  BetSettledFrame,
  CardDealtFrame,
  DealerActionFrame,
  ErrorFrame,
  GestureMadeFrame,
  HandBustFrame,
  HandResultPayload,
  HoleCardRevealedFrame,
  NaturalBlackjackFrame,
  PhaseChangedFrame,
  PlayerActionFrame,
  RoundOverFrame,
  ServerFrame,
  ShoeShuffledFrame,
  SidebetWinFrame,
} from "../protocol/server.js";

export interface EventBridge {
  /** Subscribe to engine events on this table and broadcast them. Returns an unsubscribe function. */
  attach(table: Table): () => void;
}

/**
 * Map engine `PLAYER_ACTION.action` strings to the protocol's HIT/STAND/
 * DOUBLE/SPLIT/SURRENDER enum. The engine emits strings like "HIT", "STAND"
 * which already match the wire enum, but we narrow the set so an unknown
 * value doesn't slip through the schema.
 */
const PLAYER_ACTION_WHITELIST = new Set([
  "HIT",
  "STAND",
  "DOUBLE",
  "SPLIT",
  "SURRENDER",
]);

export function createEventBridge(
  broadcast: (tableId: string, frame: ServerFrame) => void,
): EventBridge {
  return {
    attach(table: Table): () => void {
      const tableId = table.meta.tableId;

      // Per-seat last-observed bankroll. Seeded from the current state so
      // the first `BANKROLL_CHANGED` delta can still be attributed.
      const lastBankroll = new Map<number, number>();
      const seedBankroll = (): void => {
        const snap = table.game.getState();
        for (const s of snap.seats) {
          lastBankroll.set(s.index, s.player.bankroll);
        }
      };
      seedBankroll();

      /** Resolve seatIndex for BANKROLL_CHANGED / SIDEBET_WIN. */
      const resolveSeatByBankroll = (
        snap: GameSnapshot,
        delta: number,
      ): number | null => {
        for (const s of snap.seats) {
          const prev = lastBankroll.get(s.index);
          if (prev === undefined) continue;
          if (s.player.bankroll - prev === delta) {
            return s.index;
          }
        }
        return null;
      };

      /** Sync the cache after a successful resolution. */
      const syncBankrollCache = (snap: GameSnapshot): void => {
        for (const s of snap.seats) {
          lastBankroll.set(s.index, s.player.bankroll);
        }
      };

      // Track the most-recent seat a SIDEBET_WIN / BANKROLL_CHANGED flowed
      // through. This lets SIDEBET_WIN re-use the seat we just resolved for
      // its preceding BANKROLL_CHANGED (they're emitted as a pair inside
      // `settleSideBets`).
      let lastBankrollSeat: number | null = null;

      const unsubscribe = table.game.on((ev: EngineEvent): void => {
        try {
          handleEvent(ev);
        } catch (err) {
          log.error(
            { err, tableId, evType: ev.type },
            "eventBridge: handler threw",
          );
        }
      });

      function handleEvent(ev: EngineEvent): void {
        switch (ev.type) {
          case "PHASE_CHANGED": {
            const snap = table.game.getState();
            const frame: PhaseChangedFrame = {
              v: PROTOCOL_VERSION,
              type: "PHASE_CHANGED",
              phase: ev.phase,
            };
            // Only include activeSeatIndex when the phase implies one.
            if (ev.phase === "playerTurn") {
              frame.activeSeatIndex = snap.activeSeatIndex;
            }
            broadcast(tableId, frame);
            return;
          }

          case "RULESET_CHANGED": {
            // No direct wire frame; client picks up the change on the next
            // TABLE_STATE. Log at debug so the test harness can spot it.
            log.debug(
              { tableId, ruleSet: ev.ruleSet },
              "eventBridge: RULESET_CHANGED (no wire frame)",
            );
            return;
          }

          case "BET_PLACED": {
            // BANKROLL_CHANGED covers the bankroll side; a PLAYER_ACTION-
            // style "bet" frame would add no client-visible state, so skip.
            return;
          }

          case "CARD_DEALT": {
            const snap = table.game.getState();
            // For player deals, activeSeatIndex at emission time is the
            // seat being dealt to (deal() loops over active seats, but
            // each dealCardTo happens in the activeSeats iteration before
            // the playerTurn transition — at "dealing" phase activeSeatIndex
            // hasn't yet been reset to the first seat. Fortunately, the
            // engine records the per-seat hand state and we can use the
            // handIndex to locate it. The cleanest signal we have is that
            // the engine calls dealCardTo(seatIndex) for the seat; but the
            // event doesn't carry it. We look up by matching the newest
            // card in each active seat's hand.)
            const frame: CardDealtFrame = {
              v: PROTOCOL_VERSION,
              type: "CARD_DEALT",
              to: ev.to,
              handIndex: ev.handIndex,
              faceDown: ev.faceDown,
            };
            if (!ev.faceDown) {
              frame.card = { rank: ev.card.rank, suit: ev.card.suit };
            }
            if (ev.to === "player") {
              const seatIdx = findSeatForJustDealtCard(snap, ev.card, ev.handIndex);
              if (seatIdx === null) {
                // Shouldn't happen; skip rather than invent a seatIndex.
                log.warn(
                  { tableId },
                  "eventBridge: could not resolve seatIndex for CARD_DEALT to=player",
                );
                return;
              }
              frame.seatIndex = seatIdx;
            }
            broadcast(tableId, frame);
            return;
          }

          case "HOLE_CARD_REVEALED": {
            const frame: HoleCardRevealedFrame = {
              v: PROTOCOL_VERSION,
              type: "HOLE_CARD_REVEALED",
              card: { rank: ev.card.rank, suit: ev.card.suit },
              // Engine hole is always index 1 in dealer.cards.
              cardIndex: 1,
            };
            broadcast(tableId, frame);
            return;
          }

          case "PLAYER_ACTION": {
            if (!PLAYER_ACTION_WHITELIST.has(ev.action)) {
              log.warn(
                { tableId, action: ev.action },
                "eventBridge: dropping unknown PLAYER_ACTION",
              );
              return;
            }
            const snap = table.game.getState();
            const frame: PlayerActionFrame = {
              v: PROTOCOL_VERSION,
              type: "PLAYER_ACTION",
              seatIndex: snap.activeSeatIndex,
              handIndex: ev.handIndex,
              action: ev.action as PlayerActionFrame["action"],
            };
            broadcast(tableId, frame);
            return;
          }

          case "HAND_BUST": {
            const snap = table.game.getState();
            const seat = snap.seats[snap.activeSeatIndex];
            const hand = seat?.hands[ev.handIndex];
            // Total from engine evaluate helper would duplicate logic;
            // the snapshot's handValues is only for the active seat's
            // hands, which is exactly what we want here.
            const total =
              snap.activeSeatIndex === seat?.index
                ? snap.handValues[ev.handIndex]?.total ?? 0
                : 0;
            void hand;
            const frame: HandBustFrame = {
              v: PROTOCOL_VERSION,
              type: "HAND_BUST",
              seatIndex: snap.activeSeatIndex,
              handIndex: ev.handIndex,
              total,
            };
            broadcast(tableId, frame);
            return;
          }

          case "NATURAL_BLACKJACK": {
            const snap = table.game.getState();
            const frame: NaturalBlackjackFrame = {
              v: PROTOCOL_VERSION,
              type: "NATURAL_BLACKJACK",
              seatIndex: snap.activeSeatIndex,
              handIndex: ev.handIndex,
            };
            broadcast(tableId, frame);
            return;
          }

          case "DEALER_ACTION": {
            const frame: DealerActionFrame = {
              v: PROTOCOL_VERSION,
              type: "DEALER_ACTION",
              action: ev.action,
              total: ev.total,
              soft: ev.soft,
            };
            broadcast(tableId, frame);
            return;
          }

          case "ROUND_OVER": {
            const results: HandResultPayload[] = ev.results.map((r) => {
              // HandResult.seatIndex is populated by the engine per M1c.4b;
              // default to 0 if for some reason it's missing (older engine).
              const seatIndex = r.seatIndex ?? 0;
              const out: HandResultPayload = {
                seatIndex,
                handIndex: r.handIndex,
                outcome: r.outcome,
                payout: r.payout,
                total: r.total,
              };
              if (r.label !== undefined) out.label = r.label;
              return out;
            });
            const frame: RoundOverFrame = {
              v: PROTOCOL_VERSION,
              type: "ROUND_OVER",
              results,
            };
            broadcast(tableId, frame);
            return;
          }

          case "BET_SETTLED": {
            // Engine pushes a HandResult (with seatIndex) immediately before
            // emitting BET_SETTLED; the tail of roundResults is authoritative.
            const snap = table.game.getState();
            const tail = snap.roundResults[snap.roundResults.length - 1];
            const seatIndex = tail?.seatIndex;
            if (seatIndex === undefined) {
              log.warn(
                { tableId, handIndex: ev.handIndex },
                "eventBridge: BET_SETTLED without roundResults tail; skipping",
              );
              return;
            }
            const frame: BetSettledFrame = {
              v: PROTOCOL_VERSION,
              type: "BET_SETTLED",
              seatIndex,
              handIndex: ev.handIndex,
              outcome: ev.outcome,
              payout: ev.payout,
            };
            if (tail?.label !== undefined) frame.label = tail.label;
            broadcast(tableId, frame);
            return;
          }

          case "BANKROLL_CHANGED": {
            const snap = table.game.getState();
            const seatIndex = resolveSeatByBankroll(snap, ev.delta);
            // Sync cache whether or not we resolved so we stay accurate
            // for the next event.
            syncBankrollCache(snap);
            if (seatIndex === null) {
              log.warn(
                { tableId, delta: ev.delta },
                "eventBridge: could not resolve seatIndex for BANKROLL_CHANGED",
              );
              return;
            }
            lastBankrollSeat = seatIndex;
            const frame: BankrollChangedFrame = {
              v: PROTOCOL_VERSION,
              type: "BANKROLL_CHANGED",
              seatIndex,
              bankroll: ev.bankroll,
              delta: ev.delta,
            };
            broadcast(tableId, frame);
            return;
          }

          case "SIDEBET_WIN": {
            // SIDEBET_WIN is emitted immediately after a BANKROLL_CHANGED for
            // the same seat (see settleSideBets). Re-use the resolved seat.
            if (lastBankrollSeat === null) {
              log.warn(
                { tableId, kind: ev.kind },
                "eventBridge: SIDEBET_WIN without preceding BANKROLL_CHANGED; skipping",
              );
              return;
            }
            const frame: SidebetWinFrame = {
              v: PROTOCOL_VERSION,
              type: "SIDEBET_WIN",
              seatIndex: lastBankrollSeat,
              kind: ev.kind,
              payout: ev.payout,
              label: ev.label,
            };
            broadcast(tableId, frame);
            return;
          }

          case "SHOE_SHUFFLED": {
            const frame: ShoeShuffledFrame = {
              v: PROTOCOL_VERSION,
              type: "SHOE_SHUFFLED",
            };
            broadcast(tableId, frame);
            return;
          }

          case "ERROR": {
            // Mirror dealer-server style: broadcast to everyone so all
            // clients can surface the fault (e.g. a split that ran out of
            // funds). No actionIdRef available since the engine event
            // doesn't carry one.
            const frame: ErrorFrame = {
              v: PROTOCOL_VERSION,
              type: "ERROR",
              code: ev.code,
              message: ev.message,
            };
            broadcast(tableId, frame);
            return;
          }

          case "SEAT_CLAIMED":
          case "SEAT_RELEASED": {
            // Intentionally not broadcast — dispatch.ts owns those wire
            // frames with richer payloads. We DO refresh the bankroll cache
            // so later BANKROLL_CHANGED events on the newly-claimed seat
            // can be correlated (claimSeat assigns the initial bankroll
            // before emitting, so the snapshot here is authoritative).
            syncBankrollCache(table.game.getState());
            return;
          }

          case "GESTURE_MADE": {
            const frame: GestureMadeFrame = {
              v: PROTOCOL_VERSION,
              type: "GESTURE_MADE",
              seatIndex: ev.seatIndex,
              gesture: ev.gesture,
            };
            broadcast(tableId, frame);
            return;
          }

          default: {
            // Exhaustiveness guard — the engine's event union is closed, so
            // hitting this branch means a new variant was added without
            // updating the bridge.
            const _exhaustive: never = ev;
            void _exhaustive;
            log.warn({ tableId, ev }, "eventBridge: unhandled engine event");
            return;
          }
        }
      }

      return unsubscribe;
    },
  };
}

/**
 * Locate the seat whose most-recently-dealt card matches the one the engine
 * just emitted. Used to attach `seatIndex` to `CARD_DEALT to="player"`
 * frames where the engine event itself does not carry the seat.
 *
 * The engine deals at most one card per event, so the seat whose active
 * hand's last card is `card` is unambiguously the target. We also require
 * the `handIndex` to match to rule out a rare case of identical cards
 * across seats in the dealing ladder.
 */
function findSeatForJustDealtCard(
  snap: GameSnapshot,
  card: { rank: string; suit: string },
  handIndex: number,
): number | null {
  // Walk in seat order to keep deterministic ties.
  for (const s of snap.seats) {
    if (s.player.kind === "empty") continue;
    const h = s.hands[handIndex];
    if (!h || h.cards.length === 0) continue;
    const last = h.cards[h.cards.length - 1];
    if (last && last.rank === card.rank && last.suit === card.suit) {
      return s.index;
    }
  }
  return null;
}
