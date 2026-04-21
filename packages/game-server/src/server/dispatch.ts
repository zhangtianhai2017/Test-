/**
 * Frame parser + router.
 *
 * `handleMessage` is the single entry point the WS server calls for every
 * inbound text frame. It:
 *   1. JSON-parses — on failure, emits `ERROR{code:BAD_JSON}`.
 *   2. Runs `ClientFrame.safeParse` — on failure, emits `ERROR{code:BAD_FRAME}`
 *      carrying the first zod issue so the client can fix the offending field.
 *   3. Enforces `v === PROTOCOL_VERSION` — a foreign wire version is a
 *      `BAD_VERSION` error (D-018: v1 clients must not silently talk to a v2
 *      server).
 *   4. Routes on `frame.type`:
 *        - HELLO: create or resume a session, reply WELCOME.
 *        - PING: reply PONG (echo timestamp).
 *        - LIST_TABLES: reply with an empty TABLE_LIST (M3d wires the real
 *          lobby).
 *        - anything else: requires an established session
 *          (`HELLO_REQUIRED` if not), otherwise NOT_IMPLEMENTED pointing at
 *          M3d / M4.
 *
 * `sendFrame` wraps `ServerFrame.parse` around the outbound payload as a
 * belt-and-braces check: if we ever emit a frame that violates the schema,
 * throw loudly during development rather than ship garbage to the client.
 */
import type { WebSocket } from "ws";

import { log } from "../log.js";
import { ClientFrame } from "../protocol/client.js";
import { PROTOCOL_VERSION } from "../protocol/frames.js";
import { ServerFrame, type WelcomeFrame, type ErrorFrame } from "../protocol/server.js";
import type { SessionManager } from "../session/sessionManager.js";

/** Server build version string; surfaced in WELCOME. */
export const SERVER_VERSION = "0.1.0";

/**
 * Context object threaded through each connection. Holds the connection's
 * socket, the shared session registry, and a tiny pair of getter/setter
 * closures over the connection's "current session id" variable. The closures
 * exist because the id is owned by the wsServer per-connection scope, not by
 * this module.
 */
export interface DispatchContext {
  socket: WebSocket;
  sessions: SessionManager;
  graceSeconds: number;
  currentSessionId: () => string | null;
  setCurrentSessionId: (id: string | null) => void;
}

/**
 * Validate + send a single ServerFrame. Validation is schema-level; if the
 * payload passes `ServerFrame.parse` it conforms to the contract the UE
 * client expects.
 */
export function sendFrame(socket: WebSocket, frame: unknown): void {
  const parsed = ServerFrame.safeParse(frame);
  if (!parsed.success) {
    // This is a server-side bug, not a client problem — crash loud in dev.
    const msg = parsed.error.issues[0]?.message ?? "unknown";
    log.error({ issue: parsed.error.issues[0], frame }, "outbound frame failed validation");
    throw new Error(`outbound frame failed ServerFrame validation: ${msg}`);
  }
  try {
    socket.send(JSON.stringify(parsed.data));
  } catch (err) {
    // Socket may have closed mid-dispatch; log and move on.
    log.warn({ err }, "socket.send failed");
  }
}

/** Convenience: build and send an ERROR frame. */
function sendError(socket: WebSocket, code: string, message: string, actionIdRef?: string): void {
  const frame: ErrorFrame = {
    v: PROTOCOL_VERSION,
    type: "ERROR",
    code,
    message,
    ...(actionIdRef ? { actionIdRef } : {}),
  };
  sendFrame(socket, frame);
}

/** Convenience: build and send a WELCOME frame. */
function sendWelcome(socket: WebSocket, sessionId: string, graceSeconds: number): void {
  const frame: WelcomeFrame = {
    v: PROTOCOL_VERSION,
    type: "WELCOME",
    sessionId,
    serverVersion: SERVER_VERSION,
    reconnectGraceSeconds: graceSeconds,
  };
  sendFrame(socket, frame);
}

/**
 * Main per-message entry point. Never throws: any unexpected error is turned
 * into an ERROR frame so one bad input doesn't kill the connection.
 */
export function handleMessage(ctx: DispatchContext, raw: string): void {
  // --- 1. JSON parse ------------------------------------------------------
  let obj: unknown;
  try {
    obj = JSON.parse(raw);
  } catch (err) {
    const msg = err instanceof Error ? err.message : "invalid JSON";
    sendError(ctx.socket, "BAD_JSON", msg);
    return;
  }

  // --- 2. Schema parse ----------------------------------------------------
  const parsed = ClientFrame.safeParse(obj);
  if (!parsed.success) {
    const first = parsed.error.issues[0];
    const path = first?.path?.join(".") ?? "";
    const msg = first ? `${path ? path + ": " : ""}${first.message}` : "invalid frame";
    sendError(ctx.socket, "BAD_FRAME", msg);
    return;
  }
  const frame = parsed.data;

  // --- 3. Protocol-version check -----------------------------------------
  // Note: discriminated-union parsing already requires `v === PROTOCOL_VERSION`
  // via the `z.literal(PROTOCOL_VERSION)` in each frame schema, so reaching
  // this point implies v matches. We still check defensively so a future
  // schema relaxation doesn't silently drop the guard.
  if (frame.v !== PROTOCOL_VERSION) {
    sendError(ctx.socket, "BAD_VERSION", `expected v=${PROTOCOL_VERSION}, got v=${frame.v}`);
    return;
  }

  // Touch lastSeenAt on every frame from an established session.
  const currentId = ctx.currentSessionId();
  if (currentId) {
    const sess = ctx.sessions.get(currentId);
    if (sess) sess.lastSeenAt = Date.now();
  }

  // --- 4. Route by type --------------------------------------------------
  switch (frame.type) {
    case "HELLO": {
      if (frame.resumeSessionId) {
        const resumed = ctx.sessions.resume(frame.resumeSessionId, ctx.socket);
        if (!resumed) {
          sendError(
            ctx.socket,
            "RESUME_FAILED",
            `unable to resume session ${frame.resumeSessionId} (unknown, duplicate, or grace expired)`,
          );
          return;
        }
        // Update display name / client version in case they rotated.
        resumed.displayName = frame.displayName;
        resumed.clientVersion = frame.clientVersion;
        ctx.setCurrentSessionId(resumed.id);
        sendWelcome(ctx.socket, resumed.id, ctx.graceSeconds);
        return;
      }
      const created = ctx.sessions.create(frame.displayName, frame.clientVersion, ctx.socket);
      ctx.setCurrentSessionId(created.id);
      sendWelcome(ctx.socket, created.id, ctx.graceSeconds);
      return;
    }

    case "PING": {
      const pong: { v: 1; type: "PONG"; timestamp?: number; serverTime: number } = {
        v: PROTOCOL_VERSION,
        type: "PONG",
        serverTime: Date.now(),
      };
      if (typeof frame.timestamp === "number") pong.timestamp = frame.timestamp;
      sendFrame(ctx.socket, pong);
      return;
    }

    case "LIST_TABLES": {
      if (!currentId) {
        sendError(ctx.socket, "HELLO_REQUIRED", "send HELLO before any other frame");
        return;
      }
      // M3d will replace this with the real lobby listing.
      sendFrame(ctx.socket, {
        v: PROTOCOL_VERSION,
        type: "TABLE_LIST",
        tables: [],
      });
      return;
    }

    // Everything below is stubbed — M3d for lobby/table, M4 for in-round.
    case "CREATE_TABLE":
    case "JOIN_TABLE":
    case "LEAVE_TABLE":
    case "CONFIGURE_TABLE":
    case "CLAIM_SEAT":
    case "RELEASE_SEAT":
    case "PLACE_BET":
    case "HIT":
    case "STAND":
    case "DOUBLE":
    case "SPLIT":
    case "SURRENDER":
    case "INSURE":
    case "DECLINE_INSURANCE":
    case "GESTURE":
    case "NEW_ROUND": {
      if (!currentId) {
        sendError(ctx.socket, "HELLO_REQUIRED", "send HELLO before any other frame");
        return;
      }
      const actionIdRef = "actionId" in frame ? (frame as { actionId?: string }).actionId : undefined;
      sendError(
        ctx.socket,
        "NOT_IMPLEMENTED",
        `${frame.type} will land in M3d (lobby/table) or M4 (game loop)`,
        actionIdRef,
      );
      return;
    }

    default: {
      // TypeScript exhaustiveness guard.
      const _exhaustive: never = frame;
      void _exhaustive;
      sendError(ctx.socket, "BAD_FRAME", "unhandled frame type");
      return;
    }
  }
}
