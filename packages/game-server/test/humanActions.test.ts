/**
 * Integration tests for M4b (human-player game action handlers).
 *
 * Each test drives real `ws.WebSocket` clients through a lobby lifecycle —
 * HELLO → CREATE_TABLE → JOIN_TABLE → CLAIM_SEAT — and then exercises one
 * game-action frame (PLACE_BET, HIT, STAND, …) to confirm:
 *   • validation errors (NOT_IN_TABLE / NOT_SEAT_OWNER / WRONG_PHASE /
 *     NOT_YOUR_TURN) are returned to the caller only;
 *   • successful dispatches cause the M4a event bridge to broadcast
 *     state frames (PHASE_CHANGED, CARD_DEALT, ROUND_OVER, GESTURE_MADE)
 *     to every joined client.
 *
 * NPC-seat auto-drive (M4c) is deliberately NOT exercised; all tests use
 * 1–2 human seats to keep the engine waiting only on explicit actions.
 */
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { WebSocket } from "ws";

import { startGameServer, type GameServerHandle } from "../src/server/wsServer.js";

// ---------------------------------------------------------------------------
// Shared helpers (mirrors lobby.test.ts; each test file is standalone).
// ---------------------------------------------------------------------------

/**
 * Per-socket queue: attaches a persistent `message` listener as soon as we
 * connect and buffers every frame. `recv` pulls from the buffer; this way
 * we never miss a message that arrives between helper calls (the engine
 * emits several events in a single synchronous tick during dealing).
 */
type BufferedWs = WebSocket & {
  __buf: any[];
  __waiters: Array<(m: any) => void>;
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
    const resolver = (m: any): void => {
      clearTimeout(timer);
      resolve(m);
    };
    ws.__waiters.push(resolver);
  });
}

async function recvUntil(
  ws: BufferedWs,
  pred: (m: any) => boolean,
  timeoutMs = 3000,
): Promise<any> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const remaining = Math.max(50, deadline - Date.now());
    const m = await recv(ws, remaining);
    if (pred(m)) return m;
  }
  throw new Error("recvUntil: predicate never matched");
}

/** Collect every frame arriving on `ws` until a frame matches `stop`. */
async function collectUntil(
  ws: BufferedWs,
  stop: (m: any) => boolean,
  timeoutMs = 3000,
): Promise<any[]> {
  const out: any[] = [];
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const remaining = Math.max(50, deadline - Date.now());
    const m = await recv(ws, remaining);
    out.push(m);
    if (stop(m)) return out;
  }
  throw new Error("collectUntil: stop condition never matched");
}

function send(ws: BufferedWs, frame: any): void {
  ws.send(JSON.stringify(frame));
}

async function closeSocket(ws: BufferedWs): Promise<void> {
  if (ws.readyState === WebSocket.CLOSED) return;
  await new Promise<void>((resolve) => {
    ws.once("close", () => resolve());
    ws.close();
  });
}

function url(handle: GameServerHandle): string {
  const { host, port } = handle.address();
  return `ws://${host}:${port}`;
}

async function hello(
  handle: GameServerHandle,
  displayName: string,
): Promise<{ ws: BufferedWs; sessionId: string }> {
  const ws = await connectAndWait(url(handle));
  send(ws, {
    v: 1,
    type: "HELLO",
    displayName,
    clientVersion: "test-0",
  });
  const welcome = await recv(ws);
  if (welcome.type !== "WELCOME") {
    throw new Error(`expected WELCOME, got ${JSON.stringify(welcome)}`);
  }
  return { ws, sessionId: welcome.sessionId as string };
}

/**
 * Create a fresh table and return its id. Uses maxSeats=2 by default so
 * single-claim setups can bet and proceed to dealing immediately.
 */
async function createTable(ws: BufferedWs, maxSeats = 2): Promise<string> {
  send(ws, {
    v: 1,
    type: "CREATE_TABLE",
    ruleSet: "VEGAS",
    maxSeats,
    dealerPersona: "veteran",
    language: "zh",
  });
  const created = await recvUntil(ws, (m) => m.type === "TABLE_CREATED");
  return created.table.tableId as string;
}

async function join(ws: BufferedWs, tableId: string): Promise<void> {
  send(ws, { v: 1, type: "JOIN_TABLE", tableId });
  await recvUntil(ws, (m) => m.type === "TABLE_STATE");
}

async function claim(
  ws: BufferedWs,
  seatIndex: number,
  name: string,
): Promise<void> {
  send(ws, { v: 1, type: "CLAIM_SEAT", seatIndex, name });
  await recvUntil(
    ws,
    (m) => m.type === "SEAT_ASSIGNED" && m.seatIndex === seatIndex,
  );
}

// ---------------------------------------------------------------------------
// Fixture
// ---------------------------------------------------------------------------

describe("game-server / human action handlers (M4b)", () => {
  let handle: GameServerHandle;

  beforeEach(async () => {
    handle = await startGameServer({
      host: "127.0.0.1",
      port: 0,
      graceSeconds: 5,
      sweepIntervalMs: 100,
      seedBase: 42,
    });
  });

  afterEach(async () => {
    await handle.close();
  });

  // 1. PLACE_BET without a table → NOT_IN_TABLE.
  it("PLACE_BET without a table returns NOT_IN_TABLE", async () => {
    const { ws } = await hello(handle, "Alice");
    send(ws, { v: 1, type: "PLACE_BET", seatIndex: 0, amount: 10 });
    const err = await recv(ws);
    expect(err.type).toBe("ERROR");
    expect(err.code).toBe("NOT_IN_TABLE");
    await closeSocket(ws);
  });

  // 2. PLACE_BET on an unowned seat → NOT_SEAT_OWNER.
  it("PLACE_BET on an unowned seat returns NOT_SEAT_OWNER", async () => {
    const { ws } = await hello(handle, "Alice");
    const tableId = await createTable(ws);
    await join(ws, tableId);
    // Session never claimed any seat; seat 0 is still empty.
    send(ws, { v: 1, type: "PLACE_BET", seatIndex: 0, amount: 10 });
    const err = await recv(ws);
    expect(err.type).toBe("ERROR");
    expect(err.code).toBe("NOT_SEAT_OWNER");
    await closeSocket(ws);
  });

  // 3. PLACE_BET valid in betting phase → other clients see the resulting
  //    PHASE_CHANGED to "dealing" (since the single active seat has now bet).
  it("valid PLACE_BET broadcasts progress to both clients", async () => {
    const { ws: wsA } = await hello(handle, "Alice");
    const { ws: wsB } = await hello(handle, "Bob");
    const tableId = await createTable(wsA, 2);

    await join(wsA, tableId);
    await join(wsB, tableId);
    await claim(wsA, 0, "Alice");
    // Let B receive the SEAT_ASSIGNED broadcast.
    await recvUntil(wsB, (m) => m.type === "SEAT_ASSIGNED" && m.seatIndex === 0);

    send(wsA, {
      v: 1,
      type: "PLACE_BET",
      seatIndex: 0,
      amount: 25,
    });
    // Both clients see PHASE_CHANGED from the bridge — first to "dealing",
    // and eventually downstream phases as the round progresses.
    const phaseOnA = await recvUntil(
      wsA,
      (m) => m.type === "PHASE_CHANGED" && m.phase === "dealing",
    );
    expect(phaseOnA.type).toBe("PHASE_CHANGED");
    const phaseOnB = await recvUntil(
      wsB,
      (m) => m.type === "PHASE_CHANGED" && m.phase === "dealing",
    );
    expect(phaseOnB.type).toBe("PHASE_CHANGED");

    await closeSocket(wsA);
    await closeSocket(wsB);
  });

  // 4. HIT before any bet → WRONG_PHASE.
  it("HIT in wrong phase (before bet) returns WRONG_PHASE", async () => {
    const { ws } = await hello(handle, "Alice");
    const tableId = await createTable(ws);
    await join(ws, tableId);
    await claim(ws, 0, "Alice");
    send(ws, { v: 1, type: "HIT", seatIndex: 0 });
    const err = await recv(ws);
    expect(err.type).toBe("ERROR");
    expect(err.code).toBe("WRONG_PHASE");
    await closeSocket(ws);
  });

  // 5. HIT from the wrong seat when it's the other seat's turn → NOT_YOUR_TURN.
  it("HIT on a non-active seat returns NOT_YOUR_TURN", async () => {
    const { ws: wsA } = await hello(handle, "Alice");
    const { ws: wsB } = await hello(handle, "Bob");
    const tableId = await createTable(wsA, 2);

    await join(wsA, tableId);
    await join(wsB, tableId);
    await claim(wsA, 0, "Alice");
    await recvUntil(wsB, (m) => m.type === "SEAT_ASSIGNED" && m.seatIndex === 0);
    await claim(wsB, 1, "Bob");
    await recvUntil(wsA, (m) => m.type === "SEAT_ASSIGNED" && m.seatIndex === 1);

    // Both seats bet → engine deals → seat 0 is active first.
    send(wsA, { v: 1, type: "PLACE_BET", seatIndex: 0, amount: 25 });
    send(wsB, { v: 1, type: "PLACE_BET", seatIndex: 1, amount: 25 });

    // Wait until we see a "playerTurn" phase on wsA so we know dealing done.
    await recvUntil(
      wsA,
      (m) =>
        (m.type === "PHASE_CHANGED" && m.phase === "playerTurn") ||
        (m.type === "PHASE_CHANGED" && m.phase === "roundOver"),
      4000,
    );

    // Seat 1 (Bob) tries to HIT before it's his turn.
    send(wsB, { v: 1, type: "HIT", seatIndex: 1 });
    const err = await recvUntil(wsB, (m) => m.type === "ERROR");
    // Either NOT_YOUR_TURN (if we're in playerTurn) or WRONG_PHASE (if a
    // natural blackjack short-circuited the round to roundOver). Both are
    // valid refusals; the meaningful check is that the engine did NOT
    // accept the action from the non-active seat.
    expect(["NOT_YOUR_TURN", "WRONG_PHASE"]).toContain(err.code);

    await closeSocket(wsA);
    await closeSocket(wsB);
  });

  // 6. Full single-seat round: CLAIM → BET → (STAND) → ROUND_OVER.
  it("drives a single-seat round end-to-end via WS", async () => {
    const { ws } = await hello(handle, "Alice");
    const tableId = await createTable(ws, 1);
    await join(ws, tableId);
    await claim(ws, 0, "Alice");

    send(ws, { v: 1, type: "PLACE_BET", seatIndex: 0, amount: 25 });

    // Walk frames; the engine may short-circuit to roundOver on a natural
    // blackjack without ever entering playerTurn. Either path ends in a
    // ROUND_OVER broadcast.
    const deadline = Date.now() + 4000;
    let sawRoundOver = false;
    let standSent = false;
    while (Date.now() < deadline && !sawRoundOver) {
      const m = await recv(ws, Math.max(50, deadline - Date.now()));
      if (
        !standSent &&
        m.type === "PHASE_CHANGED" &&
        m.phase === "playerTurn"
      ) {
        send(ws, { v: 1, type: "STAND", seatIndex: 0 });
        standSent = true;
      }
      if (m.type === "ROUND_OVER") {
        expect(Array.isArray(m.results)).toBe(true);
        sawRoundOver = true;
      }
    }
    expect(sawRoundOver).toBe(true);
    await closeSocket(ws);
  });

  // 7. NEW_ROUND in wrong phase (betting) → WRONG_PHASE.
  it("NEW_ROUND in betting phase returns WRONG_PHASE", async () => {
    const { ws } = await hello(handle, "Alice");
    const tableId = await createTable(ws, 1);
    await join(ws, tableId);
    await claim(ws, 0, "Alice");
    send(ws, { v: 1, type: "NEW_ROUND" });
    const err = await recv(ws);
    expect(err.type).toBe("ERROR");
    expect(err.code).toBe("WRONG_PHASE");
    await closeSocket(ws);
  });

  // 8. GESTURE during any phase → GESTURE_MADE broadcast to all clients.
  it("GESTURE in betting phase broadcasts GESTURE_MADE to both clients", async () => {
    const { ws: wsA } = await hello(handle, "Alice");
    const { ws: wsB } = await hello(handle, "Bob");
    const tableId = await createTable(wsA, 2);

    await join(wsA, tableId);
    await join(wsB, tableId);
    await claim(wsA, 0, "Alice");
    await recvUntil(wsB, (m) => m.type === "SEAT_ASSIGNED" && m.seatIndex === 0);

    send(wsA, {
      v: 1,
      type: "GESTURE",
      seatIndex: 0,
      gesture: "confident",
    });
    const gotA = await recvUntil(
      wsA,
      (m) => m.type === "GESTURE_MADE" && m.seatIndex === 0,
    );
    expect(gotA.gesture).toBe("confident");
    const gotB = await recvUntil(
      wsB,
      (m) => m.type === "GESTURE_MADE" && m.seatIndex === 0,
    );
    expect(gotB.gesture).toBe("confident");
    void collectUntil; // retained helper; used in future tests.

    await closeSocket(wsA);
    await closeSocket(wsB);
  });
});
