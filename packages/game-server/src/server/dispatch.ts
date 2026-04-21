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
 *        - LIST_TABLES / CREATE_TABLE / JOIN_TABLE / LEAVE_TABLE
 *          / CONFIGURE_TABLE / CLAIM_SEAT / RELEASE_SEAT: M3d lobby ops.
 *        - PLACE_BET / HIT / STAND / DOUBLE / SPLIT / SURRENDER
 *          / INSURE / DECLINE_INSURANCE / GESTURE / NEW_ROUND:
 *          stubbed NOT_IMPLEMENTED until M4 wires the game loop.
 *
 * `sendFrame` wraps `ServerFrame.parse` around the outbound payload as a
 * belt-and-braces check: if we ever emit a frame that violates the schema,
 * throw loudly during development rather than ship garbage to the client.
 */
import type { WebSocket } from "ws";

import type { Lobby } from "../lobby/lobby.js";
import type { Table } from "../lobby/table.js";
import { buildTableStateFrame } from "../lobby/toProtocol.js";
import { log } from "../log.js";
import { ClientFrame } from "../protocol/client.js";
import { PROTOCOL_VERSION } from "../protocol/frames.js";
import {
  ServerFrame,
  type ErrorFrame,
  type SeatAssignedFrame,
  type SeatReleasedFrame,
  type ServerFrame as ServerFrameType,
  type TableCreatedFrame,
  type TableListFrame,
  type TableSummary,
  type WelcomeFrame,
} from "../protocol/server.js";
import type { SessionManager } from "../session/sessionManager.js";
import type { Session } from "../session/session.js";
import type { EventBridge } from "../table/eventBridge.js";
import type { NpcDriver } from "../table/npcDriver.js";

/** Server build version string; surfaced in WELCOME. */
export const SERVER_VERSION = "0.1.0";

/**
 * Context object threaded through each connection. Holds the connection's
 * socket, the shared session + lobby registries, and a tiny pair of
 * getter/setter closures over the connection's "current session id" variable.
 * The closures exist because the id is owned by the wsServer per-connection
 * scope, not by this module.
 */
export interface DispatchContext {
  socket: WebSocket;
  sessions: SessionManager;
  lobby: Lobby;
  graceSeconds: number;
  currentSessionId: () => string | null;
  setCurrentSessionId: (id: string | null) => void;
  /** Send a frame to every still-connected session joined on `tableId`. */
  broadcastToTable: (tableId: string, frame: ServerFrameType) => void;
  /** Engine → wire event bridge; `attach` is called on table creation (M4a). */
  bridge: EventBridge;
  /** NPC auto-driver; `attach` is called on table creation (M4c). */
  npcDriver: NpcDriver;
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

/** Build the on-wire `TableSummary` for a lobby `Table`. */
function summaryOf(table: Table): TableSummary {
  const seatsTaken = table.seatOwners.reduce<number>(
    (acc, owner) => acc + (owner !== null ? 1 : 0),
    0,
  );
  const snap = table.game.getState();
  return {
    tableId: table.meta.tableId,
    ruleSet: table.meta.ruleSet,
    maxSeats: table.meta.maxSeats,
    seatsTaken,
    phase: snap.phase,
    language: table.meta.language,
    dealerPersona: table.meta.dealerPersona,
  };
}

/** Send the requesting client a fresh TABLE_STATE snapshot. */
function sendTableState(ctx: DispatchContext, table: Table): void {
  sendFrame(ctx.socket, buildTableStateFrame(table));
}

/** Broadcast an up-to-date TABLE_STATE to every session joined on the table. */
function broadcastTableState(ctx: DispatchContext, table: Table): void {
  ctx.broadcastToTable(table.meta.tableId, buildTableStateFrame(table));
}

/**
 * Shape returned by the game-action validation helpers. Either the resolved
 * artefact (table or ok-flag) or an `{ error }` with a wire-ready code and
 * message — the caller converts it to an `ERROR` frame.
 */
type ValidationErr = { error: { code: string; message: string } };

/**
 * Resolve the `Table` the session currently sits on, or produce the matching
 * ERROR payload (NOT_IN_TABLE / NO_TABLE). Used by every game-action handler
 * as the very first step before seat-level checks.
 */
function requireSessionInTable(
  session: Session,
  lobby: Lobby,
): { table: Table } | ValidationErr {
  if (session.tableId === null) {
    return { error: { code: "NOT_IN_TABLE", message: "Session has no table" } };
  }
  const table = lobby.get(session.tableId);
  if (!table) {
    return { error: { code: "NO_TABLE", message: `table ${session.tableId} not found` } };
  }
  return { table };
}

/**
 * Validate seatIndex is in range and owned by this session. Matches the
 * pattern already used in CLAIM_SEAT / RELEASE_SEAT above.
 */
function requireOwnership(
  table: Table,
  seatIndex: number,
  sessionId: string,
): { ok: true } | ValidationErr {
  if (seatIndex < 0 || seatIndex >= table.meta.maxSeats) {
    return {
      error: {
        code: "BAD_SEAT_INDEX",
        message: `seatIndex ${seatIndex} out of range for table ${table.meta.tableId}`,
      },
    };
  }
  if (table.seatOwners[seatIndex] !== sessionId) {
    return {
      error: {
        code: "NOT_SEAT_OWNER",
        message: `session does not own seat ${seatIndex}`,
      },
    };
  }
  return { ok: true };
}

/**
 * Resolve the session tied to the current connection, or emit an error and
 * return null if there isn't one. Centralises the HELLO_REQUIRED guard used
 * by every non-HELLO frame.
 */
function requireSession(ctx: DispatchContext): Session | null {
  const sid = ctx.currentSessionId();
  if (!sid) {
    sendError(ctx.socket, "HELLO_REQUIRED", "send HELLO before any other frame");
    return null;
  }
  const s = ctx.sessions.get(sid);
  if (!s) {
    sendError(ctx.socket, "HELLO_REQUIRED", "session no longer exists; re-HELLO");
    return null;
  }
  return s;
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

    // -----------------------------------------------------------------
    // Lobby / table management (M3d)
    // -----------------------------------------------------------------

    case "LIST_TABLES": {
      if (!requireSession(ctx)) return;
      // The lobby summary already has every field we need; remap only to
      // reshape `occupiedSeats` → `seatsTaken` for the wire protocol.
      const tables: TableSummary[] = ctx.lobby.listSummaries().map((s) => ({
        tableId: s.tableId,
        ruleSet: s.ruleSet,
        maxSeats: s.maxSeats,
        seatsTaken: s.occupiedSeats,
        phase: s.phase as TableSummary["phase"],
        language: s.language,
        dealerPersona: s.dealerPersona,
      }));
      const out: TableListFrame = {
        v: PROTOCOL_VERSION,
        type: "TABLE_LIST",
        tables,
      };
      sendFrame(ctx.socket, out);
      return;
    }

    case "CREATE_TABLE": {
      if (!requireSession(ctx)) return;
      const table = ctx.lobby.createTable({
        ruleSet: frame.ruleSet,
        maxSeats: frame.maxSeats,
        dealerPersona: frame.dealerPersona,
        language: frame.language,
      });
      // Attach the engine → wire event bridge so events from this table's
      // game are broadcast to seated sessions (M4a). The unsubscribe handle
      // is stashed on the table for future use (tables aren't explicitly
      // deleted in v1, so a teardown call site doesn't exist yet).
      const unsub = ctx.bridge.attach(table);
      (table as unknown as { _bridgeUnsub?: () => void })._bridgeUnsub = unsub;
      // Also attach the NPC auto-driver (M4c). Stash its unsubscribe on the
      // same table handle; tables aren't explicitly deleted in v1, so a
      // teardown call site doesn't exist yet.
      const npcUnsub = ctx.npcDriver.attach(table);
      (table as unknown as { _npcDriverUnsub?: () => void })._npcDriverUnsub = npcUnsub;
      const out: TableCreatedFrame = {
        v: PROTOCOL_VERSION,
        type: "TABLE_CREATED",
        table: summaryOf(table),
      };
      sendFrame(ctx.socket, out);
      return;
    }

    case "JOIN_TABLE": {
      const session = requireSession(ctx);
      if (!session) return;
      const table = ctx.lobby.get(frame.tableId);
      if (!table) {
        sendError(ctx.socket, "NO_TABLE", `table ${frame.tableId} does not exist`);
        return;
      }
      if (session.tableId !== null && session.tableId !== frame.tableId) {
        sendError(
          ctx.socket,
          "ALREADY_IN_TABLE",
          `already joined on table ${session.tableId}; LEAVE_TABLE first`,
        );
        return;
      }
      // Idempotent re-join on the same table: just resend TABLE_STATE.
      if (session.tableId === frame.tableId) {
        sendTableState(ctx, table);
        return;
      }

      session.tableId = frame.tableId;
      const claimed: number[] = [];
      if (frame.seatRequest && frame.seatRequest.length > 0) {
        for (const seatIndex of frame.seatRequest) {
          if (seatIndex < 0 || seatIndex >= table.meta.maxSeats) {
            sendError(
              ctx.socket,
              "BAD_SEAT_INDEX",
              `seatIndex ${seatIndex} out of range for table ${table.meta.tableId}`,
            );
            continue;
          }
          if (table.seatOwners[seatIndex] !== null) {
            sendError(
              ctx.socket,
              "SEAT_TAKEN",
              `seat ${seatIndex} already owned`,
            );
            continue;
          }
          table.game.dispatch({
            type: "CLAIM_SEAT",
            seatIndex,
            sessionId: session.id,
            name: session.displayName,
          });
          table.seatOwners[seatIndex] = session.id;
          if (!session.ownedSeats.includes(seatIndex)) {
            session.ownedSeats.push(seatIndex);
          }
          claimed.push(seatIndex);
        }
      }

      sendTableState(ctx, table);

      // Announce each newly-claimed seat to the rest of the table.
      for (const seatIndex of claimed) {
        const seatSnap = table.game.getState().seats[seatIndex];
        const assigned: SeatAssignedFrame = {
          v: PROTOCOL_VERSION,
          type: "SEAT_ASSIGNED",
          seatIndex,
          ownerSessionId: session.id,
          playerName: seatSnap?.player.name ?? session.displayName,
          bankroll: seatSnap?.player.bankroll ?? 0,
        };
        ctx.broadcastToTable(table.meta.tableId, assigned);
      }
      return;
    }

    case "LEAVE_TABLE": {
      const session = requireSession(ctx);
      if (!session) return;
      if (session.tableId === null) {
        sendError(ctx.socket, "NOT_IN_TABLE", "not currently joined on any table");
        return;
      }
      const tableId = session.tableId;
      const released = ctx.lobby.releaseSeatsFor(session.id, tableId);
      // Clear the leaver's own state before broadcasting so the broadcast
      // helper's "sessions joined on this table" filter excludes them.
      session.tableId = null;
      session.ownedSeats = [];
      for (const { seatIndex } of released) {
        const out: SeatReleasedFrame = {
          v: PROTOCOL_VERSION,
          type: "SEAT_RELEASED",
          seatIndex,
        };
        ctx.broadcastToTable(tableId, out);
      }
      return;
    }

    case "CLAIM_SEAT": {
      const session = requireSession(ctx);
      if (!session) return;
      if (session.tableId === null) {
        sendError(
          ctx.socket,
          "NOT_IN_TABLE",
          "JOIN_TABLE before CLAIM_SEAT",
          frame.actionId,
        );
        return;
      }
      const table = ctx.lobby.get(session.tableId);
      if (!table) {
        sendError(ctx.socket, "NO_TABLE", "table vanished", frame.actionId);
        return;
      }
      if (frame.seatIndex < 0 || frame.seatIndex >= table.meta.maxSeats) {
        sendError(
          ctx.socket,
          "BAD_SEAT_INDEX",
          `seatIndex ${frame.seatIndex} out of range`,
          frame.actionId,
        );
        return;
      }
      if (table.seatOwners[frame.seatIndex] !== null) {
        sendError(
          ctx.socket,
          "SEAT_TAKEN",
          `seat ${frame.seatIndex} already owned`,
          frame.actionId,
        );
        return;
      }
      const dispatchArgs: {
        type: "CLAIM_SEAT";
        seatIndex: number;
        sessionId: string;
        name: string;
        bankroll?: number;
      } = {
        type: "CLAIM_SEAT",
        seatIndex: frame.seatIndex,
        sessionId: session.id,
        name: frame.name,
      };
      if (frame.bankroll !== undefined) {
        dispatchArgs.bankroll = frame.bankroll;
      }
      table.game.dispatch(dispatchArgs);
      table.seatOwners[frame.seatIndex] = session.id;
      if (!session.ownedSeats.includes(frame.seatIndex)) {
        session.ownedSeats.push(frame.seatIndex);
      }
      const seatSnap = table.game.getState().seats[frame.seatIndex];
      const assigned: SeatAssignedFrame = {
        v: PROTOCOL_VERSION,
        type: "SEAT_ASSIGNED",
        seatIndex: frame.seatIndex,
        ownerSessionId: session.id,
        playerName: seatSnap?.player.name ?? frame.name,
        bankroll: seatSnap?.player.bankroll ?? frame.bankroll ?? 0,
      };
      ctx.broadcastToTable(table.meta.tableId, assigned);
      return;
    }

    case "RELEASE_SEAT": {
      const session = requireSession(ctx);
      if (!session) return;
      if (session.tableId === null) {
        sendError(
          ctx.socket,
          "NOT_IN_TABLE",
          "JOIN_TABLE before RELEASE_SEAT",
          frame.actionId,
        );
        return;
      }
      const table = ctx.lobby.get(session.tableId);
      if (!table) {
        sendError(ctx.socket, "NO_TABLE", "table vanished", frame.actionId);
        return;
      }
      if (frame.seatIndex < 0 || frame.seatIndex >= table.meta.maxSeats) {
        sendError(
          ctx.socket,
          "BAD_SEAT_INDEX",
          `seatIndex ${frame.seatIndex} out of range`,
          frame.actionId,
        );
        return;
      }
      if (table.seatOwners[frame.seatIndex] !== session.id) {
        sendError(
          ctx.socket,
          "NOT_SEAT_OWNER",
          `session does not own seat ${frame.seatIndex}`,
          frame.actionId,
        );
        return;
      }
      const releaseArgs: {
        type: "RELEASE_SEAT";
        seatIndex: number;
        becomeNpc?: boolean;
        personality?: import("@blackjack/engine").NpcPersonality;
      } = {
        type: "RELEASE_SEAT",
        seatIndex: frame.seatIndex,
      };
      if (frame.becomeNpc !== undefined) releaseArgs.becomeNpc = frame.becomeNpc;
      if (frame.personality !== undefined) releaseArgs.personality = frame.personality;
      table.game.dispatch(releaseArgs);
      table.seatOwners[frame.seatIndex] = null;
      session.ownedSeats = session.ownedSeats.filter((s) => s !== frame.seatIndex);
      const out: SeatReleasedFrame = {
        v: PROTOCOL_VERSION,
        type: "SEAT_RELEASED",
        seatIndex: frame.seatIndex,
        ...(frame.becomeNpc !== undefined ? { becameNpc: frame.becomeNpc } : {}),
        ...(frame.personality !== undefined ? { personality: frame.personality } : {}),
      };
      ctx.broadcastToTable(table.meta.tableId, out);
      return;
    }

    case "CONFIGURE_TABLE": {
      const session = requireSession(ctx);
      if (!session) return;
      if (session.tableId === null) {
        sendError(ctx.socket, "NOT_IN_TABLE", "JOIN_TABLE before CONFIGURE_TABLE");
        return;
      }
      const table = ctx.lobby.get(session.tableId);
      if (!table) {
        sendError(ctx.socket, "NO_TABLE", "table vanished");
        return;
      }
      if (frame.seats.length > table.meta.maxSeats) {
        sendError(
          ctx.socket,
          "TOO_MANY_SEATS",
          `seats must be ≤ ${table.meta.maxSeats}`,
        );
        return;
      }
      table.game.dispatch({
        type: "CONFIGURE_TABLE",
        config: {
          seats: frame.seats.map((s) => {
            const out: {
              kind: typeof s.kind;
              name?: string;
              personality?: typeof s.personality;
              bankroll?: number;
            } = { kind: s.kind };
            if (s.name !== undefined) out.name = s.name;
            if (s.personality !== undefined) out.personality = s.personality;
            if (s.bankroll !== undefined) out.bankroll = s.bankroll;
            return out;
          }),
        },
      });
      // CONFIGURE_TABLE is a bulk reset of seat layout; any previously-
      // claimed ownership is invalidated because the engine rewrote the
      // seat array. Clear server-side ownership too, and wipe every
      // session's `ownedSeats` that references this table so the next
      // CLAIM_SEAT starts from a clean slate.
      table.seatOwners = new Array(table.meta.maxSeats).fill(null);
      for (const s of ctx.sessions.all()) {
        if (s.tableId === table.meta.tableId) {
          s.ownedSeats = [];
        }
      }
      // CONFIGURE_TABLE doesn't emit an engine event, so nudge the NPC
      // driver so it re-scans the now-replaced seat layout (M4c).
      ctx.npcDriver.notifyTableConfigured(table);
      broadcastTableState(ctx, table);
      return;
    }

    // -----------------------------------------------------------------
    // Round-phase actions (M4b).
    //
    // Each handler validates:
    //   1. Session is joined on a table (tableId set + lobby knows it).
    //   2. seatIndex is in range and owned by this session (gesture/bet/
    //      turn actions all require seat ownership).
    //   3. Phase constraint for the action.
    //   4. For turn-gated actions: activeSeatIndex === seatIndex.
    //
    // TODO(M4): actionId idempotency per D-022 is deferred. The grace-
    // reconnect in M3c handles the main drop-reconnect window; full
    // per-session replay-dedupe (last 50 ids) is post-v1.
    //
    // TODO(M4a): the engine may emit an ERROR event after a valid-looking
    // dispatch (e.g. INSUFFICIENT_FUNDS on PLACE_BET). The event bridge
    // currently broadcasts those to all table members as an ERROR wire
    // frame. The caller therefore receives feedback, but without an
    // actionIdRef tag. Good enough for v1.
    // -----------------------------------------------------------------

    case "PLACE_BET": {
      const session = requireSession(ctx);
      if (!session) return;
      const actionIdRef = frame.actionId;
      const tableOrErr = requireSessionInTable(session, ctx.lobby);
      if ("error" in tableOrErr) {
        sendError(ctx.socket, tableOrErr.error.code, tableOrErr.error.message, actionIdRef);
        return;
      }
      const { table } = tableOrErr;
      const own = requireOwnership(table, frame.seatIndex, session.id);
      if ("error" in own) {
        sendError(ctx.socket, own.error.code, own.error.message, actionIdRef);
        return;
      }
      const snap = table.game.getState();
      if (snap.phase !== "betting") {
        sendError(
          ctx.socket,
          "WRONG_PHASE",
          `PLACE_BET only allowed in phase "betting" (got "${snap.phase}")`,
          actionIdRef,
        );
        return;
      }
      const betArgs: {
        type: "PLACE_BET_FOR_SEAT";
        seatIndex: number;
        amount: number;
        sideBets?: Partial<import("@blackjack/engine").SideBets>;
      } = {
        type: "PLACE_BET_FOR_SEAT",
        seatIndex: frame.seatIndex,
        amount: frame.amount,
      };
      if (frame.sideBets !== undefined) betArgs.sideBets = frame.sideBets;
      table.game.dispatch(betArgs);
      return;
    }

    case "HIT":
    case "STAND":
    case "DOUBLE":
    case "SPLIT":
    case "SURRENDER": {
      const session = requireSession(ctx);
      if (!session) return;
      const actionIdRef = frame.actionId;
      const tableOrErr = requireSessionInTable(session, ctx.lobby);
      if ("error" in tableOrErr) {
        sendError(ctx.socket, tableOrErr.error.code, tableOrErr.error.message, actionIdRef);
        return;
      }
      const { table } = tableOrErr;
      const own = requireOwnership(table, frame.seatIndex, session.id);
      if ("error" in own) {
        sendError(ctx.socket, own.error.code, own.error.message, actionIdRef);
        return;
      }
      const snap = table.game.getState();
      if (snap.phase !== "playerTurn") {
        sendError(
          ctx.socket,
          "WRONG_PHASE",
          `${frame.type} only allowed in phase "playerTurn" (got "${snap.phase}")`,
          actionIdRef,
        );
        return;
      }
      if (snap.activeSeatIndex !== frame.seatIndex) {
        sendError(
          ctx.socket,
          "NOT_YOUR_TURN",
          `seat ${frame.seatIndex} is not the active seat (active=${snap.activeSeatIndex})`,
          actionIdRef,
        );
        return;
      }
      table.game.dispatch({ type: frame.type });
      return;
    }

    case "INSURE": {
      const session = requireSession(ctx);
      if (!session) return;
      const actionIdRef = frame.actionId;
      const tableOrErr = requireSessionInTable(session, ctx.lobby);
      if ("error" in tableOrErr) {
        sendError(ctx.socket, tableOrErr.error.code, tableOrErr.error.message, actionIdRef);
        return;
      }
      const { table } = tableOrErr;
      const own = requireOwnership(table, frame.seatIndex, session.id);
      if ("error" in own) {
        sendError(ctx.socket, own.error.code, own.error.message, actionIdRef);
        return;
      }
      const snap = table.game.getState();
      if (snap.phase !== "insurance") {
        sendError(
          ctx.socket,
          "WRONG_PHASE",
          `INSURE only allowed in phase "insurance" (got "${snap.phase}")`,
          actionIdRef,
        );
        return;
      }
      // Engine currently targets humanSeatIndex for insurance regardless of
      // the seat the frame nominates (D-023 v1 note). Per-seat routing is
      // post-v1; ownership+phase gating suffices here.
      table.game.dispatch({ type: "INSURE", amount: frame.amount });
      return;
    }

    case "DECLINE_INSURANCE": {
      const session = requireSession(ctx);
      if (!session) return;
      const actionIdRef = frame.actionId;
      const tableOrErr = requireSessionInTable(session, ctx.lobby);
      if ("error" in tableOrErr) {
        sendError(ctx.socket, tableOrErr.error.code, tableOrErr.error.message, actionIdRef);
        return;
      }
      const { table } = tableOrErr;
      const own = requireOwnership(table, frame.seatIndex, session.id);
      if ("error" in own) {
        sendError(ctx.socket, own.error.code, own.error.message, actionIdRef);
        return;
      }
      const snap = table.game.getState();
      if (snap.phase !== "insurance") {
        sendError(
          ctx.socket,
          "WRONG_PHASE",
          `DECLINE_INSURANCE only allowed in phase "insurance" (got "${snap.phase}")`,
          actionIdRef,
        );
        return;
      }
      table.game.dispatch({ type: "DECLINE_INSURANCE" });
      return;
    }

    case "NEW_ROUND": {
      const session = requireSession(ctx);
      if (!session) return;
      const actionIdRef = frame.actionId;
      const tableOrErr = requireSessionInTable(session, ctx.lobby);
      if ("error" in tableOrErr) {
        sendError(ctx.socket, tableOrErr.error.code, tableOrErr.error.message, actionIdRef);
        return;
      }
      const { table } = tableOrErr;
      // Any seated session may trigger NEW_ROUND; no seat ownership check.
      const snap = table.game.getState();
      if (snap.phase !== "roundOver") {
        sendError(
          ctx.socket,
          "WRONG_PHASE",
          `NEW_ROUND only allowed in phase "roundOver" (got "${snap.phase}")`,
          actionIdRef,
        );
        return;
      }
      table.game.dispatch({ type: "NEW_ROUND" });
      return;
    }

    case "GESTURE": {
      const session = requireSession(ctx);
      if (!session) return;
      const actionIdRef = frame.actionId;
      const tableOrErr = requireSessionInTable(session, ctx.lobby);
      if ("error" in tableOrErr) {
        sendError(ctx.socket, tableOrErr.error.code, tableOrErr.error.message, actionIdRef);
        return;
      }
      const { table } = tableOrErr;
      const own = requireOwnership(table, frame.seatIndex, session.id);
      if ("error" in own) {
        sendError(ctx.socket, own.error.code, own.error.message, actionIdRef);
        return;
      }
      // GESTURE is not phase-gated: a seated player can emote at any time.
      table.game.dispatch({
        type: "GESTURE",
        seatIndex: frame.seatIndex,
        gesture: frame.gesture,
      });
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
