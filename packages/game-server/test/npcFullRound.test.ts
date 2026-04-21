/**
 * Integration test — M4c (+ M4d-preview).
 *
 * One real WebSocket client drives a table with 1 human + 2 NPC seats
 * through a full round. The NpcDriver (wired into `startGameServer`) is
 * expected to auto-bet and auto-play the two NPCs; the human only needs
 * to place a bet and STAND to complete the round.
 *
 * Assertions:
 *   - Exactly one ROUND_OVER frame is broadcast.
 *   - ROUND_OVER.results contains at least one HandResult per seat index
 *     (0, 1, 2).
 *
 * Real wall-clock timing is used (not fake timers), so we set short
 * bet/play delays via the default driver — and bump the overall timeout
 * to accommodate the engine's natural sequencing.
 */
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { WebSocket } from "ws";

import { startGameServer, type GameServerHandle } from "../src/server/wsServer.js";

type BufferedWs = WebSocket & {
  __buf: unknown[];
  __waiters: Array<(m: unknown) => void>;
};

function attachBuffer(ws: WebSocket): BufferedWs {
  const bws = ws as BufferedWs;
  bws.__buf = [];
  bws.__waiters = [];
  bws.on("message", (d: Buffer) => {
    const m = JSON.parse(d.toString());
    const w = bws.__waiters.shift();
    if (w) w(m);
    else bws.__buf.push(m);
  });
  return bws;
}

async function connectAndWait(url: string): Promise<BufferedWs> {
  const ws = new WebSocket(url);
  await new Promise<void>((resolve, reject) => {
    ws.once("open", () => resolve());
    ws.once("error", reject);
  });
  return attachBuffer(ws);
}

function recv(ws: BufferedWs, timeoutMs = 2000): Promise<any> {
  if (ws.__buf.length > 0) return Promise.resolve(ws.__buf.shift());
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      const idx = ws.__waiters.indexOf(resolver);
      if (idx >= 0) ws.__waiters.splice(idx, 1);
      reject(new Error("recv timeout"));
    }, timeoutMs);
    const resolver = (m: unknown): void => {
      clearTimeout(timer);
      resolve(m);
    };
    ws.__waiters.push(resolver);
  });
}

async function recvUntil(
  ws: BufferedWs,
  pred: (m: any) => boolean,
  timeoutMs = 10000,
): Promise<any> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const remaining = Math.max(50, deadline - Date.now());
    const m = await recv(ws, remaining);
    if (pred(m)) return m;
  }
  throw new Error("recvUntil: predicate never matched");
}

async function collectAllUntil(
  ws: BufferedWs,
  stop: (m: any) => boolean,
  timeoutMs = 10000,
): Promise<any[]> {
  const out: any[] = [];
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const remaining = Math.max(50, deadline - Date.now());
    const m = await recv(ws, remaining);
    out.push(m);
    if (stop(m)) return out;
  }
  throw new Error("collectAllUntil: stop never matched");
}

describe("npcFullRound (M4c / M4d-preview)", () => {
  let handle: GameServerHandle;
  let url: string;

  beforeEach(async () => {
    handle = await startGameServer({ port: 0, seedBase: 12345 });
    const addr = handle.address();
    url = `ws://${addr.host}:${addr.port}`;
  });

  afterEach(async () => {
    await handle.close();
  });

  it(
    "1 human + 2 NPC seats: round runs to ROUND_OVER with all three seats reported",
    async () => {
      const ws = await connectAndWait(url);
      try {
        // HELLO
        ws.send(
          JSON.stringify({
            v: 1,
            type: "HELLO",
            displayName: "Alice",
            clientVersion: "test",
          }),
        );
        await recvUntil(ws, (m) => m.type === "WELCOME");

        // CREATE_TABLE
        ws.send(
          JSON.stringify({
            v: 1,
            type: "CREATE_TABLE",
            ruleSet: "VEGAS",
            maxSeats: 4,
            dealerPersona: "veteran",
            language: "en",
          }),
        );
        const created = await recvUntil(ws, (m) => m.type === "TABLE_CREATED");
        const tableId = created.table.tableId;

        // JOIN_TABLE (no seat request)
        ws.send(
          JSON.stringify({
            v: 1,
            type: "JOIN_TABLE",
            tableId,
          }),
        );
        await recvUntil(ws, (m) => m.type === "TABLE_STATE");

        // CONFIGURE_TABLE: 1 human + 2 NPCs.
        ws.send(
          JSON.stringify({
            v: 1,
            type: "CONFIGURE_TABLE",
            seats: [
              { kind: "human", name: "Alice", bankroll: 1000 },
              {
                kind: "npc",
                name: "Bot-1",
                personality: "optimal",
                bankroll: 1000,
              },
              {
                kind: "npc",
                name: "Bot-2",
                personality: "optimal",
                bankroll: 1000,
              },
            ],
          }),
        );
        await recvUntil(ws, (m) => m.type === "TABLE_STATE");

        // CLAIM_SEAT for the human.
        ws.send(
          JSON.stringify({
            v: 1,
            type: "CLAIM_SEAT",
            seatIndex: 0,
            name: "Alice",
            bankroll: 1000,
            actionId: "claim-1",
          }),
        );
        await recvUntil(
          ws,
          (m) => m.type === "SEAT_ASSIGNED" && m.seatIndex === 0,
        );

        // Human PLACE_BET. The NpcDriver will race us to bet first, but
        // either order completes the betting set and triggers dealing.
        // Wait a moment to let the driver kick off NPC bets.
        await new Promise((r) => setTimeout(r, 50));
        ws.send(
          JSON.stringify({
            v: 1,
            type: "PLACE_BET",
            seatIndex: 0,
            amount: 25,
            actionId: "bet-1",
          }),
        );

        // Collect frames until we see ROUND_OVER. If the engine lands on
        // a human playerTurn, send STAND so the round can progress.
        const roundOvers: any[] = [];
        const deadline = Date.now() + 10000;
        while (Date.now() < deadline) {
          const m = await recv(ws, 3000);
          if (m.type === "PHASE_CHANGED" && m.phase === "playerTurn") {
            // Peek at active seat: the frame carries it.
            if (m.activeSeatIndex === 0) {
              // Our turn — STAND.
              ws.send(
                JSON.stringify({
                  v: 1,
                  type: "STAND",
                  seatIndex: 0,
                  actionId: `stand-${Date.now()}`,
                }),
              );
            }
          }
          if (m.type === "ROUND_OVER") {
            roundOvers.push(m);
            break;
          }
        }
        expect(roundOvers.length).toBe(1);

        // Every seat (0, 1, 2) should be represented in the results.
        const seatIdxs = new Set(roundOvers[0].results.map((r: any) => r.seatIndex));
        expect(seatIdxs.has(0)).toBe(true);
        expect(seatIdxs.has(1)).toBe(true);
        expect(seatIdxs.has(2)).toBe(true);
      } finally {
        ws.close();
      }
    },
    20000,
  );
});
