/**
 * Integration tests for M3d (lobby + table registry + seat claiming).
 *
 * Each test spins a fresh `startGameServer` on an ephemeral port and drives
 * real `ws.WebSocket` clients through a CREATE/JOIN/CLAIM/RELEASE/LEAVE
 * lifecycle, verifying both the acting-client response and broadcast
 * delivery to any other sessions joined on the same table.
 *
 * No betting/play/settlement is exercised here — that's M4b, covered by
 * `humanActions.test.ts`.
 */
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { WebSocket } from "ws";

import { startGameServer, type GameServerHandle } from "../src/server/wsServer.js";

// ---------------------------------------------------------------------------
// Helpers (re-declared from server.test.ts to keep each test file standalone)
// ---------------------------------------------------------------------------

async function connectAndWait(url: string): Promise<WebSocket> {
  const ws = new WebSocket(url);
  await new Promise<void>((resolve, reject) => {
    ws.once("open", () => resolve());
    ws.once("error", reject);
  });
  return ws;
}

function recv(ws: WebSocket, timeoutMs = 2000): Promise<any> {
  return new Promise((resolve, reject) => {
    const onMsg = (d: Buffer): void => {
      clearTimeout(timer);
      ws.off("message", onMsg);
      resolve(JSON.parse(d.toString()));
    };
    const timer = setTimeout(() => {
      ws.off("message", onMsg);
      reject(new Error("recv timeout"));
    }, timeoutMs);
    ws.on("message", onMsg);
  });
}

/**
 * Receive messages until one matches the predicate. Useful when broadcasts
 * and direct replies arrive interleaved — e.g. a CLAIM_SEAT generates a
 * SEAT_ASSIGNED to the claimer plus, on the other client, a SEAT_ASSIGNED
 * broadcast that may be preceded by an unrelated TABLE_STATE.
 */
async function recvUntil(
  ws: WebSocket,
  pred: (m: any) => boolean,
  timeoutMs = 2000,
): Promise<any> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const remaining = Math.max(50, deadline - Date.now());
    const m = await recv(ws, remaining);
    if (pred(m)) return m;
  }
  throw new Error("recvUntil: predicate never matched");
}

function send(ws: WebSocket, frame: any): void {
  ws.send(JSON.stringify(frame));
}

async function closeSocket(ws: WebSocket): Promise<void> {
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

/** Open a connection and complete HELLO. Returns the socket + session id. */
async function hello(
  handle: GameServerHandle,
  displayName: string,
): Promise<{ ws: WebSocket; sessionId: string }> {
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

// ---------------------------------------------------------------------------
// Fixture
// ---------------------------------------------------------------------------

describe("game-server / lobby + seat claiming (M3d)", () => {
  let handle: GameServerHandle;

  beforeEach(async () => {
    handle = await startGameServer({
      host: "127.0.0.1",
      port: 0,
      graceSeconds: 1, // short grace for the disconnect-expire test
      sweepIntervalMs: 100,
      seedBase: 42,
    });
  });

  afterEach(async () => {
    await handle.close();
  });

  // -------------------------------------------------------------------------
  // 1. CREATE_TABLE → TABLE_CREATED
  // -------------------------------------------------------------------------

  it("CREATE_TABLE returns a TABLE_CREATED frame with a unique tableId", async () => {
    const { ws } = await hello(handle, "Alice");
    send(ws, {
      v: 1,
      type: "CREATE_TABLE",
      ruleSet: "VEGAS",
      maxSeats: 3,
      dealerPersona: "veteran",
      language: "en",
    });
    const msg = await recv(ws);
    expect(msg.type).toBe("TABLE_CREATED");
    expect(typeof msg.table.tableId).toBe("string");
    expect(msg.table.tableId.length).toBeGreaterThan(0);
    expect(msg.table.ruleSet).toBe("VEGAS");
    expect(msg.table.maxSeats).toBe(3);
    expect(msg.table.seatsTaken).toBe(0);
    expect(msg.table.language).toBe("en");
    await closeSocket(ws);
  });

  // -------------------------------------------------------------------------
  // 2. Two CREATE_TABLE calls → distinct ids
  // -------------------------------------------------------------------------

  it("two CREATE_TABLE calls from different sessions yield distinct tableIds", async () => {
    const { ws: wsA } = await hello(handle, "A");
    const { ws: wsB } = await hello(handle, "B");

    send(wsA, {
      v: 1,
      type: "CREATE_TABLE",
      ruleSet: "VEGAS",
      maxSeats: 3,
      dealerPersona: "veteran",
      language: "zh",
    });
    const createdA = await recv(wsA);

    send(wsB, {
      v: 1,
      type: "CREATE_TABLE",
      ruleSet: "VEGAS",
      maxSeats: 4,
      dealerPersona: "veteran",
      language: "zh",
    });
    const createdB = await recv(wsB);

    expect(createdA.table.tableId).not.toBe(createdB.table.tableId);
    await closeSocket(wsA);
    await closeSocket(wsB);
  });

  // -------------------------------------------------------------------------
  // 3. LIST_TABLES returns created tables
  // -------------------------------------------------------------------------

  it("LIST_TABLES returns every created table", async () => {
    const { ws } = await hello(handle, "A");

    send(ws, {
      v: 1,
      type: "CREATE_TABLE",
      ruleSet: "VEGAS",
      maxSeats: 3,
      dealerPersona: "veteran",
      language: "zh",
    });
    const c1 = await recv(ws);

    send(ws, {
      v: 1,
      type: "CREATE_TABLE",
      ruleSet: "SPANISH21",
      maxSeats: 4,
      dealerPersona: "veteran",
      language: "zh",
    });
    const c2 = await recv(ws);

    send(ws, { v: 1, type: "LIST_TABLES" });
    const list = await recv(ws);
    expect(list.type).toBe("TABLE_LIST");
    expect(list.tables).toHaveLength(2);
    const ids = list.tables.map((t: any) => t.tableId).sort();
    expect(ids).toEqual([c1.table.tableId, c2.table.tableId].sort());
    await closeSocket(ws);
  });

  // -------------------------------------------------------------------------
  // 4. JOIN_TABLE on nonexistent id → NO_TABLE
  // -------------------------------------------------------------------------

  it("JOIN_TABLE on a nonexistent table returns NO_TABLE", async () => {
    const { ws } = await hello(handle, "A");
    send(ws, { v: 1, type: "JOIN_TABLE", tableId: "doesnotexist" });
    const err = await recv(ws);
    expect(err.type).toBe("ERROR");
    expect(err.code).toBe("NO_TABLE");
    await closeSocket(ws);
  });

  // -------------------------------------------------------------------------
  // 5. JOIN_TABLE with valid id → TABLE_STATE
  // -------------------------------------------------------------------------

  it("JOIN_TABLE with a valid id replies with TABLE_STATE", async () => {
    const { ws } = await hello(handle, "A");
    send(ws, {
      v: 1,
      type: "CREATE_TABLE",
      ruleSet: "VEGAS",
      maxSeats: 3,
      dealerPersona: "veteran",
      language: "en",
    });
    const created = await recv(ws);
    send(ws, { v: 1, type: "JOIN_TABLE", tableId: created.table.tableId });
    const state = await recv(ws);
    expect(state.type).toBe("TABLE_STATE");
    expect(state.tableId).toBe(created.table.tableId);
    expect(state.maxSeats).toBe(3);
    expect(state.ruleSet).toBe("VEGAS");
    expect(state.language).toBe("en");
    expect(state.dealer.holeHidden).toBe(true);
    await closeSocket(ws);
  });

  // -------------------------------------------------------------------------
  // 6. CLAIM_SEAT broadcasts to other table members
  // -------------------------------------------------------------------------

  it("CLAIM_SEAT by client A is observed by already-joined client B", async () => {
    const { ws: wsA } = await hello(handle, "Alice");
    const { ws: wsB, sessionId: sidB } = await hello(handle, "Bob");
    void sidB;

    send(wsA, {
      v: 1,
      type: "CREATE_TABLE",
      ruleSet: "VEGAS",
      maxSeats: 3,
      dealerPersona: "veteran",
      language: "zh",
    });
    const created = await recv(wsA);
    const tableId = created.table.tableId as string;

    // A joins.
    send(wsA, { v: 1, type: "JOIN_TABLE", tableId });
    await recv(wsA); // TABLE_STATE for A

    // B joins.
    send(wsB, { v: 1, type: "JOIN_TABLE", tableId });
    await recv(wsB); // TABLE_STATE for B

    // A claims seat 0.
    send(wsA, {
      v: 1,
      type: "CLAIM_SEAT",
      seatIndex: 0,
      name: "Alice",
    });
    const assignedToA = await recvUntil(
      wsA,
      (m) => m.type === "SEAT_ASSIGNED" && m.seatIndex === 0,
    );
    expect(assignedToA.playerName).toBe("Alice");

    // B receives the broadcast.
    const assignedToB = await recvUntil(
      wsB,
      (m) => m.type === "SEAT_ASSIGNED" && m.seatIndex === 0,
    );
    expect(assignedToB.playerName).toBe("Alice");

    await closeSocket(wsA);
    await closeSocket(wsB);
  });

  it("late-joining client sees A's seat ownership in its TABLE_STATE", async () => {
    const { ws: wsA, sessionId: sidA } = await hello(handle, "Alice");

    send(wsA, {
      v: 1,
      type: "CREATE_TABLE",
      ruleSet: "VEGAS",
      maxSeats: 3,
      dealerPersona: "veteran",
      language: "zh",
    });
    const created = await recv(wsA);
    const tableId = created.table.tableId as string;

    send(wsA, { v: 1, type: "JOIN_TABLE", tableId });
    await recv(wsA);
    send(wsA, { v: 1, type: "CLAIM_SEAT", seatIndex: 0, name: "Alice" });
    await recvUntil(wsA, (m) => m.type === "SEAT_ASSIGNED" && m.seatIndex === 0);

    // Now B joins — its TABLE_STATE should show seat 0 owned by A.
    const { ws: wsB } = await hello(handle, "Bob");
    send(wsB, { v: 1, type: "JOIN_TABLE", tableId });
    const stateB = await recv(wsB);
    expect(stateB.type).toBe("TABLE_STATE");
    const seat0 = stateB.seats[0];
    expect(seat0.ownerSessionId).toBe(sidA);
    expect(seat0.playerName).toBe("Alice");

    await closeSocket(wsA);
    await closeSocket(wsB);
  });

  // -------------------------------------------------------------------------
  // 7. CLAIM_SEAT on occupied seat → SEAT_TAKEN
  // -------------------------------------------------------------------------

  it("CLAIM_SEAT on an already-owned seat returns SEAT_TAKEN with no mutation", async () => {
    const { ws: wsA } = await hello(handle, "Alice");
    const { ws: wsB } = await hello(handle, "Bob");

    send(wsA, {
      v: 1,
      type: "CREATE_TABLE",
      ruleSet: "VEGAS",
      maxSeats: 3,
      dealerPersona: "veteran",
      language: "zh",
    });
    const created = await recv(wsA);
    const tableId = created.table.tableId;

    send(wsA, { v: 1, type: "JOIN_TABLE", tableId });
    await recv(wsA);
    send(wsA, { v: 1, type: "CLAIM_SEAT", seatIndex: 1, name: "Alice" });
    await recvUntil(wsA, (m) => m.type === "SEAT_ASSIGNED");

    send(wsB, { v: 1, type: "JOIN_TABLE", tableId });
    await recv(wsB);
    // drain any broadcasts about pre-existing seats
    send(wsB, { v: 1, type: "CLAIM_SEAT", seatIndex: 1, name: "Bob" });
    const err = await recv(wsB);
    expect(err.type).toBe("ERROR");
    expect(err.code).toBe("SEAT_TAKEN");

    // Confirm no mutation: re-list via a fresh JOIN_TABLE state on B.
    send(wsB, { v: 1, type: "JOIN_TABLE", tableId }); // idempotent re-join
    const stateB = await recv(wsB);
    expect(stateB.seats[1].playerName).toBe("Alice");

    await closeSocket(wsA);
    await closeSocket(wsB);
  });

  // -------------------------------------------------------------------------
  // 8. RELEASE_SEAT by non-owner → NOT_SEAT_OWNER
  // -------------------------------------------------------------------------

  it("RELEASE_SEAT by a non-owner returns NOT_SEAT_OWNER", async () => {
    const { ws: wsA } = await hello(handle, "Alice");
    const { ws: wsB } = await hello(handle, "Bob");

    send(wsA, {
      v: 1,
      type: "CREATE_TABLE",
      ruleSet: "VEGAS",
      maxSeats: 3,
      dealerPersona: "veteran",
      language: "zh",
    });
    const created = await recv(wsA);
    const tableId = created.table.tableId;

    send(wsA, { v: 1, type: "JOIN_TABLE", tableId });
    await recv(wsA);
    send(wsA, { v: 1, type: "CLAIM_SEAT", seatIndex: 2, name: "Alice" });
    await recvUntil(wsA, (m) => m.type === "SEAT_ASSIGNED");

    send(wsB, { v: 1, type: "JOIN_TABLE", tableId });
    await recv(wsB);
    send(wsB, { v: 1, type: "RELEASE_SEAT", seatIndex: 2 });
    const err = await recv(wsB);
    expect(err.type).toBe("ERROR");
    expect(err.code).toBe("NOT_SEAT_OWNER");

    await closeSocket(wsA);
    await closeSocket(wsB);
  });

  // -------------------------------------------------------------------------
  // 9. LEAVE_TABLE clears ownedSeats + broadcasts SEAT_RELEASED
  // -------------------------------------------------------------------------

  it("LEAVE_TABLE releases owned seats and broadcasts SEAT_RELEASED", async () => {
    const { ws: wsA } = await hello(handle, "Alice");
    const { ws: wsB } = await hello(handle, "Bob");

    send(wsA, {
      v: 1,
      type: "CREATE_TABLE",
      ruleSet: "VEGAS",
      maxSeats: 3,
      dealerPersona: "veteran",
      language: "zh",
    });
    const created = await recv(wsA);
    const tableId = created.table.tableId;

    send(wsA, { v: 1, type: "JOIN_TABLE", tableId });
    await recv(wsA);
    send(wsA, { v: 1, type: "CLAIM_SEAT", seatIndex: 0, name: "Alice" });
    await recvUntil(wsA, (m) => m.type === "SEAT_ASSIGNED");

    send(wsB, { v: 1, type: "JOIN_TABLE", tableId });
    await recv(wsB);
    // drain any pending broadcasts on B's queue before triggering the release
    // (unlikely here, but keeps the assertion tight).

    send(wsA, { v: 1, type: "LEAVE_TABLE" });
    const releasedOnB = await recvUntil(
      wsB,
      (m) => m.type === "SEAT_RELEASED" && m.seatIndex === 0,
    );
    expect(releasedOnB.type).toBe("SEAT_RELEASED");

    await closeSocket(wsA);
    await closeSocket(wsB);
  });

  // -------------------------------------------------------------------------
  // 10. Session disconnect + grace expire → seats auto-released
  // -------------------------------------------------------------------------

  it("session grace expiry auto-releases owned seats with a broadcast", async () => {
    const { ws: wsA } = await hello(handle, "Alice");
    const { ws: wsB } = await hello(handle, "Bob");

    send(wsA, {
      v: 1,
      type: "CREATE_TABLE",
      ruleSet: "VEGAS",
      maxSeats: 3,
      dealerPersona: "veteran",
      language: "zh",
    });
    const created = await recv(wsA);
    const tableId = created.table.tableId;

    send(wsA, { v: 1, type: "JOIN_TABLE", tableId });
    await recv(wsA);
    send(wsA, { v: 1, type: "CLAIM_SEAT", seatIndex: 0, name: "Alice" });
    await recvUntil(wsA, (m) => m.type === "SEAT_ASSIGNED");

    send(wsB, { v: 1, type: "JOIN_TABLE", tableId });
    await recv(wsB);

    // Drop A's connection; its session enters grace and then the sweeper
    // evicts it. Since `graceSeconds: 1` + `sweepIntervalMs: 100` we wait
    // ~1.5 s for the release broadcast.
    await closeSocket(wsA);

    const released = await recvUntil(
      wsB,
      (m) => m.type === "SEAT_RELEASED" && m.seatIndex === 0,
      3000,
    );
    expect(released.type).toBe("SEAT_RELEASED");

    await closeSocket(wsB);
  }, 10_000);

  // (Round-action integration coverage lives in humanActions.test.ts.)
});
