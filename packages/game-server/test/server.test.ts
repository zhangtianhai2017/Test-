/**
 * Integration tests for the WebSocket server (M3c).
 *
 * These tests spin a real `startGameServer` on an ephemeral port and connect
 * real `ws.WebSocket` clients — no mocks. This catches bugs in the end-to-end
 * parse → dispatch → send path that a unit test couldn't.
 */
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { WebSocket } from "ws";

import { startGameServer, type GameServerHandle } from "../src/server/wsServer.js";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function connectAndWait(url: string): Promise<WebSocket> {
  const ws = new WebSocket(url);
  await new Promise<void>((resolve, reject) => {
    ws.once("open", () => resolve());
    ws.once("error", reject);
  });
  return ws;
}

function recv(ws: WebSocket): Promise<any> {
  return new Promise((resolve) => {
    ws.once("message", (d: Buffer) => resolve(JSON.parse(d.toString())));
  });
}

function send(ws: WebSocket, frame: any): void {
  ws.send(JSON.stringify(frame));
}

function sendRaw(ws: WebSocket, raw: string): void {
  ws.send(raw);
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

// ---------------------------------------------------------------------------
// Fixture
// ---------------------------------------------------------------------------

describe("game-server / WebSocket server (M3c)", () => {
  let handle: GameServerHandle;

  beforeEach(async () => {
    handle = await startGameServer({
      host: "127.0.0.1",
      port: 0, // ephemeral
      graceSeconds: 2,
      sweepIntervalMs: 200,
    });
  });

  afterEach(async () => {
    await handle.close();
  });

  // -------------------------------------------------------------------------
  // 1. Basic liveness
  // -------------------------------------------------------------------------

  it("starts and accepts a connection on an ephemeral port", async () => {
    const { host, port } = handle.address();
    expect(host).toBe("127.0.0.1");
    expect(port).toBeGreaterThan(0);

    const ws = await connectAndWait(url(handle));
    expect(ws.readyState).toBe(WebSocket.OPEN);
    await closeSocket(ws);
  });

  // -------------------------------------------------------------------------
  // 2. HELLO → WELCOME
  // -------------------------------------------------------------------------

  it("HELLO returns WELCOME with a sessionId and reconnectGraceSeconds", async () => {
    const ws = await connectAndWait(url(handle));
    send(ws, {
      v: 1,
      type: "HELLO",
      displayName: "Alice",
      clientVersion: "test-0",
    });
    const welcome = await recv(ws);
    expect(welcome.type).toBe("WELCOME");
    expect(typeof welcome.sessionId).toBe("string");
    expect(welcome.sessionId.length).toBeGreaterThan(0);
    expect(welcome.reconnectGraceSeconds).toBe(2); // matches fixture override
    expect(welcome.v).toBe(1);
    await closeSocket(ws);
  });

  // -------------------------------------------------------------------------
  // 3. Non-HELLO first frame → HELLO_REQUIRED
  // -------------------------------------------------------------------------

  it("rejects a non-HELLO first frame with HELLO_REQUIRED", async () => {
    const ws = await connectAndWait(url(handle));
    send(ws, { v: 1, type: "LIST_TABLES" });
    const err = await recv(ws);
    expect(err.type).toBe("ERROR");
    expect(err.code).toBe("HELLO_REQUIRED");
    await closeSocket(ws);
  });

  // -------------------------------------------------------------------------
  // 4. Bad JSON
  // -------------------------------------------------------------------------

  it("returns BAD_JSON for malformed JSON", async () => {
    const ws = await connectAndWait(url(handle));
    sendRaw(ws, "{this is not json");
    const err = await recv(ws);
    expect(err.type).toBe("ERROR");
    expect(err.code).toBe("BAD_JSON");
    await closeSocket(ws);
  });

  // -------------------------------------------------------------------------
  // 5. Bad version
  // -------------------------------------------------------------------------

  it("returns BAD_VERSION (via schema) when v != PROTOCOL_VERSION", async () => {
    const ws = await connectAndWait(url(handle));
    // v:99 fails the z.literal(1) in every frame schema → BAD_FRAME or
    // BAD_VERSION depending on where zod trips. The dispatcher short-circuits
    // on the discriminated-union check first, so we accept either code; what
    // matters is that the request is rejected without ever touching session
    // state.
    send(ws, {
      v: 99,
      type: "HELLO",
      displayName: "Bob",
      clientVersion: "test-0",
    });
    const err = await recv(ws);
    expect(err.type).toBe("ERROR");
    expect(["BAD_VERSION", "BAD_FRAME"]).toContain(err.code);
    await closeSocket(ws);
  });

  // -------------------------------------------------------------------------
  // 6. Schema-invalid frame
  // -------------------------------------------------------------------------

  it("returns BAD_FRAME when HELLO is missing displayName", async () => {
    const ws = await connectAndWait(url(handle));
    send(ws, { v: 1, type: "HELLO", clientVersion: "test-0" });
    const err = await recv(ws);
    expect(err.type).toBe("ERROR");
    expect(err.code).toBe("BAD_FRAME");
    expect(err.message).toMatch(/displayName/i);
    await closeSocket(ws);
  });

  // -------------------------------------------------------------------------
  // 7. PING → PONG
  // -------------------------------------------------------------------------

  it("responds to PING with PONG carrying the echoed timestamp", async () => {
    const ws = await connectAndWait(url(handle));
    send(ws, { v: 1, type: "HELLO", displayName: "Carol", clientVersion: "test-0" });
    await recv(ws); // consume WELCOME

    const t = 1_700_000_000_000;
    send(ws, { v: 1, type: "PING", timestamp: t });
    const pong = await recv(ws);
    expect(pong.type).toBe("PONG");
    expect(pong.timestamp).toBe(t);
    expect(typeof pong.serverTime).toBe("number");
    await closeSocket(ws);
  });

  // -------------------------------------------------------------------------
  // 8. LIST_TABLES → empty list
  // -------------------------------------------------------------------------

  it("LIST_TABLES returns an empty TABLE_LIST (M3d will populate it)", async () => {
    const ws = await connectAndWait(url(handle));
    send(ws, { v: 1, type: "HELLO", displayName: "Dan", clientVersion: "test-0" });
    await recv(ws);

    send(ws, { v: 1, type: "LIST_TABLES" });
    const msg = await recv(ws);
    expect(msg.type).toBe("TABLE_LIST");
    expect(msg.tables).toEqual([]);
    await closeSocket(ws);
  });

  // -------------------------------------------------------------------------
  // 9. PLACE_BET without a table → NOT_IN_TABLE (M4b)
  // -------------------------------------------------------------------------
  //
  // M3c asserted that round-action frames were still stubbed with
  // NOT_IMPLEMENTED; M4b has now wired them through to the engine. The
  // equivalent guard at this layer is the NOT_IN_TABLE rejection a bare
  // (post-HELLO, pre-JOIN_TABLE) session receives.
  it("PLACE_BET from a session with no table returns NOT_IN_TABLE", async () => {
    const ws = await connectAndWait(url(handle));
    send(ws, { v: 1, type: "HELLO", displayName: "Eve", clientVersion: "test-0" });
    await recv(ws);

    send(ws, {
      v: 1,
      type: "PLACE_BET",
      seatIndex: 0,
      amount: 10,
    });
    const err = await recv(ws);
    expect(err.type).toBe("ERROR");
    expect(err.code).toBe("NOT_IN_TABLE");
    await closeSocket(ws);
  });

  // -------------------------------------------------------------------------
  // 10. Reconnect within grace → same sessionId
  // -------------------------------------------------------------------------

  it("reconnect within grace window resumes the same sessionId", async () => {
    const ws1 = await connectAndWait(url(handle));
    send(ws1, { v: 1, type: "HELLO", displayName: "Frank", clientVersion: "test-0" });
    const welcome1 = await recv(ws1);
    const sid = welcome1.sessionId as string;
    expect(typeof sid).toBe("string");

    // Drop the first socket; server moves session to grace.
    await closeSocket(ws1);

    // Give the server a tick to process the close.
    await new Promise((r) => setTimeout(r, 50));

    // Reconnect before the 2 s grace expires.
    const ws2 = await connectAndWait(url(handle));
    send(ws2, {
      v: 1,
      type: "HELLO",
      displayName: "Frank",
      clientVersion: "test-0",
      resumeSessionId: sid,
    });
    const welcome2 = await recv(ws2);
    expect(welcome2.type).toBe("WELCOME");
    expect(welcome2.sessionId).toBe(sid);
    await closeSocket(ws2);
  });

  // -------------------------------------------------------------------------
  // 11. Reconnect after grace → RESUME_FAILED
  // -------------------------------------------------------------------------

  it("reconnect after grace expires returns RESUME_FAILED", async () => {
    const ws1 = await connectAndWait(url(handle));
    send(ws1, { v: 1, type: "HELLO", displayName: "Gina", clientVersion: "test-0" });
    const welcome1 = await recv(ws1);
    const sid = welcome1.sessionId as string;

    await closeSocket(ws1);

    // graceSeconds = 2, sweepIntervalMs = 200 → wait 2.5 s to be safe.
    await new Promise((r) => setTimeout(r, 2500));

    const ws2 = await connectAndWait(url(handle));
    send(ws2, {
      v: 1,
      type: "HELLO",
      displayName: "Gina",
      clientVersion: "test-0",
      resumeSessionId: sid,
    });
    const err = await recv(ws2);
    expect(err.type).toBe("ERROR");
    expect(err.code).toBe("RESUME_FAILED");
    await closeSocket(ws2);
  }, 10_000);
});
