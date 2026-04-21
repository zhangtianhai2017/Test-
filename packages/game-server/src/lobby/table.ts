/**
 * One live table (M3d).
 *
 * A `Table` pairs server bookkeeping (meta, seat ownership keyed by sessionId)
 * with an `@blackjack/engine` `Game` instance. Ownership lives here — the
 * engine itself cares about seat kinds and game state, not which WS session
 * chose each seat. Keeping these separate lets the session layer release a
 * disconnecting user's seats without reaching inside engine state.
 */
import { createGame, type Game, type RuleSetId } from "@blackjack/engine";

/**
 * Immutable metadata describing one table. `language` / `dealerPersona` are
 * only surfaced to the UE client (D-014, D-003) — the engine is language-
 * agnostic, so we carry them here.
 */
export interface TableMeta {
  tableId: string;
  ruleSet: RuleSetId;
  maxSeats: number;
  dealerPersona: string;
  language: "zh" | "en";
  createdAt: number;
}

/**
 * A live table plus its engine instance and a parallel array mapping
 * `seatIndex -> ownerSessionId`. `null` entries are empty or NPC-driven seats
 * (NPC seats have no human session behind them, so they stay null here).
 */
export interface Table {
  meta: TableMeta;
  game: Game;
  /** Which sessionId owns each seat index (or null for empty/NPC). */
  seatOwners: (string | null)[];
}

/**
 * Build a wired `Table`: construct the engine with the meta's ruleSet and
 * seed, initialize `seatOwners` as `[null, null, ...]` of length `maxSeats`.
 */
export function createTable(meta: TableMeta, seed?: number): Table {
  const game = createGame({
    ruleSetId: meta.ruleSet,
    ...(seed !== undefined ? { seed } : {}),
    maxSeats: meta.maxSeats,
  });
  const seatOwners: (string | null)[] = new Array(meta.maxSeats).fill(null);
  return { meta, game, seatOwners };
}
