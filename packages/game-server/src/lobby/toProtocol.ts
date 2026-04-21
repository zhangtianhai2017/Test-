/**
 * Engine snapshot → wire-protocol `TABLE_STATE` translation (M3d).
 *
 * The engine exposes a `GameSnapshot`; the wire format `TableStateFrame`
 * shares most of the shape but differs in two places:
 *   1. Dealer hole card: when `dealerHoleHidden`, the hole slot on the wire
 *      becomes `{faceDown: true}` — the real rank/suit never leaves the
 *      server (game-server AGENT.md invariant).
 *   2. Seat payloads strip engine-only flags (`settled`) and add
 *      `ownerSessionId` resolved from the server-side `Table.seatOwners`
 *      map (engine's `seat.ownerSessionId` is also populated, but we prefer
 *      the server map as authoritative for live seat ownership).
 */
import type { GameSnapshot } from "@blackjack/engine";

import { PROTOCOL_VERSION } from "../protocol/frames.js";
import type {
  DealerPayload,
  HandPayload,
  MaybeHiddenCard,
  SeatPayload,
  TableStateFrame,
} from "../protocol/server.js";
import type { Table } from "./table.js";

function buildDealer(snap: GameSnapshot): DealerPayload {
  const cards: MaybeHiddenCard[] = snap.dealer.map((c, idx) => {
    // The hole is always index 1. Replace with placeholder while hidden.
    if (snap.dealerHoleHidden && idx === 1) {
      return { faceDown: true } as const;
    }
    return { rank: c.rank, suit: c.suit };
  });
  const dv = snap.dealerValue;
  return {
    cards,
    total: dv.total,
    soft: dv.soft,
    isBust: dv.isBust,
    holeHidden: snap.dealerHoleHidden,
  };
}

function buildSeat(
  seat: GameSnapshot["seats"][number],
  ownerSessionId: string | null,
): SeatPayload {
  const hands: HandPayload[] = seat.hands.map((h, i) => {
    // Engine stores Card with {rank, suit, id?}; the wire payload is strict
    // so we strip any extra fields.
    const cards = h.cards.map((c) => ({ rank: c.rank, suit: c.suit }));
    // Re-evaluate here? The engine snapshot has `handValues` per-seat but
    // only for the active seat. For non-active seats we don't have values
    // pre-baked, so compute a minimal total from the card count. In M4 the
    // engine will likely surface per-seat values — for M3d most seats are
    // pre-round (empty hands) so this suffices.
    let total = 0;
    let soft = false;
    let aces = 0;
    for (const c of h.cards) {
      if (c.rank === "A") {
        total += 1;
        aces += 1;
      } else if (["J", "Q", "K"].includes(c.rank)) {
        total += 10;
      } else {
        total += parseInt(c.rank, 10);
      }
    }
    if (aces > 0 && total + 10 <= 21) {
      total += 10;
      soft = true;
    }
    const isBust = total > 21;
    const hp: HandPayload = {
      handIndex: i,
      cards,
      bet: h.bet,
      doubled: h.doubled,
      surrendered: h.surrendered,
      stood: h.stood,
      splitFromAces: h.splitFromAces,
      total,
      soft,
      isBust,
    };
    return hp;
  });
  const payload: SeatPayload = {
    index: seat.index,
    kind: seat.player.kind,
    playerName: seat.player.name,
    bankroll: seat.player.bankroll,
    ownerSessionId,
    hands,
    activeHandIndex: seat.activeHandIndex,
    pendingBet: seat.pendingBet,
    sideBets: {
      perfectPairs: seat.sideBets.perfectPairs,
      twentyOneP3: seat.sideBets.twentyOneP3,
      luckyLadies: seat.sideBets.luckyLadies,
    },
    insuranceBet: seat.insuranceBet,
    gestures: seat.gestures.slice(),
    tilt: seat.tilt,
  };
  if (seat.player.personality !== undefined) {
    payload.personality = seat.player.personality;
  }
  return payload;
}

/**
 * Build a full `TABLE_STATE` frame for the given table. Accepts the table
 * itself (owners map, meta) and optionally the requesting session; the
 * session isn't currently used for filtering (we send the same snapshot to
 * everyone) but is kept in the signature for future per-viewer redaction
 * (e.g. private notes, side-bet hints).
 */
export function buildTableStateFrame(table: Table): TableStateFrame {
  const snap = table.game.getState();
  const seats: SeatPayload[] = snap.seats
    .slice(0, table.meta.maxSeats)
    .map((s) =>
      buildSeat(s, table.seatOwners[s.index] ?? s.ownerSessionId ?? null),
    );
  const activeSeatIndex: number | null =
    snap.phase === "playerTurn" ? snap.activeSeatIndex : null;
  return {
    v: PROTOCOL_VERSION,
    type: "TABLE_STATE",
    tableId: table.meta.tableId,
    phase: snap.phase,
    ruleSet: table.meta.ruleSet,
    language: table.meta.language,
    dealerPersona: table.meta.dealerPersona,
    seats,
    dealer: buildDealer(snap),
    activeSeatIndex,
    maxSeats: table.meta.maxSeats,
  };
}
