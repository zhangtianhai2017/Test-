/**
 * Lobby registry (M3d).
 *
 * The `Lobby` holds every live `Table` by `tableId` and is the single place
 * the dispatcher looks tables up. We also centralize cross-table bookkeeping
 * that's awkward to do elsewhere — notably `releaseSeatsFor(sessionId)` which
 * the session expirer calls to clean up after a dropped user.
 *
 * ID strategy: `crypto.randomUUID()` trimmed to 8 hex chars. Short enough to
 * read in logs, long enough that collision within a single server run is
 * astronomically unlikely (16M ids for a 1% birthday collision risk).
 */
import type { RuleSetId } from "@blackjack/engine";

import { createTable, type Table, type TableMeta } from "./table.js";

export interface LobbyTableSummary {
  tableId: string;
  ruleSet: RuleSetId;
  occupiedSeats: number;
  maxSeats: number;
  phase: string;
  language: "zh" | "en";
  dealerPersona: string;
}

export interface CreateTableOpts {
  ruleSet: RuleSetId;
  maxSeats: number;
  dealerPersona: string;
  language: "zh" | "en";
}

export interface Lobby {
  listSummaries(): LobbyTableSummary[];
  createTable(opts: CreateTableOpts): Table;
  get(tableId: string): Table | null;
  delete(tableId: string): boolean;
  /**
   * Release every seat this session currently owns, across every table. Used
   * by the session expirer on grace timeout. Returns one descriptor per seat
   * cleared so the caller can broadcast `SEAT_RELEASED` appropriately.
   *
   * `tableIdFilter` scopes the release to a single table (used by LEAVE_TABLE
   * so we don't accidentally release seats on other tables — even though the
   * current model only allows one table per session, belt-and-braces).
   */
  releaseSeatsFor(
    sessionId: string,
    tableIdFilter?: string,
  ): Array<{ tableId: string; seatIndex: number }>;
}

/**
 * Create an empty lobby. `seedBase` is used as the starting seed for the
 * first created table; subsequent tables get `seedBase + n`. In production we
 * leave it undefined so each table uses `Date.now()`-style seeding; tests
 * pass a fixed value for deterministic shoes.
 */
export function createLobby(seedBase?: number): Lobby {
  const tables = new Map<string, Table>();
  let createdCount = 0;

  const shortId = (): string => {
    // crypto.randomUUID is globally available in Node ≥ 19; the WS server
    // already relies on it (session.ts).
    const uuid = globalThis.crypto.randomUUID();
    // Take the first block of the UUID (8 hex chars). Drop the dash.
    return uuid.replace(/-/g, "").slice(0, 8);
  };

  const lobby: Lobby = {
    listSummaries() {
      const out: LobbyTableSummary[] = [];
      for (const t of tables.values()) {
        const occupied = t.seatOwners.reduce<number>(
          (acc, owner) => acc + (owner !== null ? 1 : 0),
          0,
        );
        const snap = t.game.getState();
        out.push({
          tableId: t.meta.tableId,
          ruleSet: t.meta.ruleSet,
          occupiedSeats: occupied,
          maxSeats: t.meta.maxSeats,
          phase: snap.phase,
          language: t.meta.language,
          dealerPersona: t.meta.dealerPersona,
        });
      }
      return out;
    },

    createTable(opts) {
      // Guarantee a unique id even if randomUUID ever collides.
      let tableId = shortId();
      while (tables.has(tableId)) tableId = shortId();
      const meta: TableMeta = {
        tableId,
        ruleSet: opts.ruleSet,
        maxSeats: opts.maxSeats,
        dealerPersona: opts.dealerPersona,
        language: opts.language,
        createdAt: Date.now(),
      };
      const seed =
        seedBase !== undefined ? seedBase + createdCount : undefined;
      createdCount += 1;
      const table = createTable(meta, seed);
      tables.set(tableId, table);
      return table;
    },

    get(tableId) {
      return tables.get(tableId) ?? null;
    },

    delete(tableId) {
      return tables.delete(tableId);
    },

    releaseSeatsFor(sessionId, tableIdFilter) {
      const released: Array<{ tableId: string; seatIndex: number }> = [];
      for (const t of tables.values()) {
        if (tableIdFilter !== undefined && t.meta.tableId !== tableIdFilter) {
          continue;
        }
        for (let i = 0; i < t.seatOwners.length; i++) {
          if (t.seatOwners[i] === sessionId) {
            t.seatOwners[i] = null;
            // Best-effort engine release. Only safe during betting phase per
            // the engine; if we're mid-round we still clear server ownership
            // so the seat doesn't stay stuck, and the engine seat stays
            // whatever it was (settlement will still work).
            try {
              t.game.dispatch({ type: "RELEASE_SEAT", seatIndex: i });
            } catch {
              /* engine guards against bad phase; we swallow. */
            }
            released.push({ tableId: t.meta.tableId, seatIndex: i });
          }
        }
      }
      return released;
    },
  };

  return lobby;
}
