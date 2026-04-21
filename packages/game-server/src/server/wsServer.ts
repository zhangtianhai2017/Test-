/**
 * WebSocket server + connection lifecycle (M3c + M3d).
 *
 * Responsibilities:
 *  - Bind a `ws.WebSocketServer` on the configured host:port.
 *  - Own one `SessionManager` and one `Lobby` for the lifetime of the server.
 *  - For each connection, hold a tiny piece of per-socket state: the
 *    `currentSessionId` (null until HELLO). The actual parsing + routing is
 *    delegated to `dispatch.handleMessage`.
 *  - On `close`, move the session to grace so a reconnect can resume.
 *  - On grace expiry (via the session manager's `onExpire` hook), release any
 *    seats the dropped session owned and broadcast SEAT_RELEASED to the
 *    remaining members of that table (M3d).
 *
 * The dispatcher is handed a `broadcastToTable` helper so lobby/table
 * dispatch logic can notify every session currently sitting at a table
 * without reaching back into this module's per-connection state.
 */
import { createServer, type Server as HttpServer } from "node:http";
import { AddressInfo } from "node:net";

import { WebSocket, WebSocketServer } from "ws";

import { createLobby, type Lobby } from "../lobby/lobby.js";
import { log } from "../log.js";
import { PROTOCOL_VERSION } from "../protocol/frames.js";
import type { SeatReleasedFrame, ServerFrame } from "../protocol/server.js";
import { createSessionManager, type SessionManager } from "../session/sessionManager.js";
import { createEventBridge, type EventBridge } from "../table/eventBridge.js";
import { createNpcDriver, type NpcDriver } from "../table/npcDriver.js";
import { handleMessage, sendFrame, type DispatchContext } from "./dispatch.js";

/** Handle returned from `startGameServer`. Used by the entry point + tests. */
export interface GameServerHandle {
  /** Actual bound address. Useful when the caller passed port 0 for ephemeral. */
  address(): { host: string; port: number };
  /** Close the server, terminate sockets, and stop the session sweeper. */
  close(): Promise<void>;
  /** Exposed so tests can poke at session state; not part of the stable API. */
  _sessions(): SessionManager;
}

export interface StartOptions {
  /** Defaults to 127.0.0.1 (D-017: local binding unless explicitly externalised). */
  host?: string;
  /** Defaults to 7878 (D-017). Use 0 for an ephemeral port. */
  port?: number;
  /** Grace window for reconnect in seconds (D-022 default 45). */
  graceSeconds?: number;
  /** Session sweeper interval; tests override to tighten the loop. */
  sweepIntervalMs?: number;
  /**
   * Seed base for deterministic shoe generation in the lobby's tables.
   * Undefined in production (tables use Date.now-style seeding); tests pass
   * a fixed integer so the engine's RNG is reproducible.
   */
  seedBase?: number;
}

const DEFAULT_HOST = "127.0.0.1";
const DEFAULT_PORT = 7878;
const DEFAULT_GRACE_SECONDS = 45;

export function startGameServer(opts: StartOptions = {}): Promise<GameServerHandle> {
  const host = opts.host ?? DEFAULT_HOST;
  const port = opts.port ?? DEFAULT_PORT;
  const graceSeconds = opts.graceSeconds ?? DEFAULT_GRACE_SECONDS;
  const sweepIntervalMs = opts.sweepIntervalMs; // undefined → manager default

  // Shared per-server state.
  const lobby: Lobby = createLobby(opts.seedBase);

  /**
   * Send a frame to every session that (a) is joined on `tableId` and (b)
   * still has an open socket. Skips grace-state sessions (socket === null)
   * so we don't buffer broadcasts for users who may never come back.
   */
  const broadcastToTable = (tableId: string, frame: ServerFrame): void => {
    for (const s of sessions.all()) {
      if (s.tableId !== tableId) continue;
      if (s.socket === null) continue;
      try {
        sendFrame(s.socket, frame);
      } catch (err) {
        log.warn({ err, sessionId: s.id }, "broadcastToTable: sendFrame failed");
      }
    }
  };

  // Engine → wire event bridge. Attached per-table on CREATE_TABLE (M4a).
  const bridge: EventBridge = createEventBridge(broadcastToTable);

  // NPC auto-driver. Also attached per-table on CREATE_TABLE (M4c).
  const npcDriver: NpcDriver = createNpcDriver();

  // When a session's grace window expires, release any seats it still owns
  // and notify the rest of the table. This lives here (rather than in the
  // session manager) so the manager stays lobby-ignorant.
  const sessions = createSessionManager({
    graceSeconds,
    sweepIntervalMs,
    onExpire: (session) => {
      if (session.tableId === null) return;
      const released = lobby.releaseSeatsFor(session.id);
      for (const { tableId, seatIndex } of released) {
        const frame: SeatReleasedFrame = {
          v: PROTOCOL_VERSION,
          type: "SEAT_RELEASED",
          seatIndex,
        };
        broadcastToTable(tableId, frame);
      }
      // Clear the session's own bookkeeping — safe even after it's deleted.
      session.tableId = null;
      session.ownedSeats = [];
    },
  });

  // We attach the WS server to a plain http server so callers can later add
  // `/health` or other routes without restructuring. Today, all requests are
  // upgrade requests, and non-upgrade HTTP gets a dumb 426.
  const http: HttpServer = createServer((_req, res) => {
    res.statusCode = 426;
    res.setHeader("Content-Type", "text/plain; charset=utf-8");
    res.end("This endpoint speaks WebSocket only.\n");
  });

  const wss = new WebSocketServer({ server: http });

  wss.on("connection", (socket: WebSocket) => {
    // Per-connection mutable state: the session id, if any. Captured by the
    // getter/setter closures we pass into dispatch.
    let currentSessionId: string | null = null;

    const ctx: DispatchContext = {
      socket,
      sessions,
      lobby,
      graceSeconds,
      currentSessionId: () => currentSessionId,
      setCurrentSessionId: (id) => {
        currentSessionId = id;
      },
      broadcastToTable,
      bridge,
      npcDriver,
    };

    socket.on("message", (data, isBinary) => {
      if (isBinary) {
        // We only speak JSON text. Reply BAD_FRAME rather than silently drop.
        try {
          socket.send(
            JSON.stringify({
              v: 1,
              type: "ERROR",
              code: "BAD_FRAME",
              message: "binary frames are not supported",
            }),
          );
        } catch {
          /* socket already gone */
        }
        return;
      }
      // `data` is a Buffer | ArrayBuffer | Buffer[] per ws types. toString()
      // is safe on all of them.
      const raw = Array.isArray(data)
        ? Buffer.concat(data).toString("utf8")
        : data.toString();
      try {
        handleMessage(ctx, raw);
      } catch (err) {
        log.error({ err }, "unhandled error in handleMessage");
      }
    });

    socket.on("close", () => {
      if (currentSessionId) {
        sessions.disconnect(currentSessionId);
      }
    });

    socket.on("error", (err) => {
      log.warn({ err }, "ws socket error");
    });
  });

  return new Promise<GameServerHandle>((resolve, reject) => {
    const onError = (err: Error) => {
      http.off("listening", onListening);
      reject(err);
    };
    const onListening = () => {
      http.off("error", onError);
      const addr = http.address() as AddressInfo | null;
      const boundHost = addr?.address ?? host;
      const boundPort = addr?.port ?? port;
      log.info({ host: boundHost, port: boundPort }, "ws server listening");

      const handle: GameServerHandle = {
        address() {
          return { host: boundHost, port: boundPort };
        },
        async close() {
          // Stop accepting new connections + close existing ones.
          await new Promise<void>((res) => {
            wss.close(() => res());
          });
          // Terminate any client sockets that didn't close on their own so
          // Node can let the event loop drain (important for tests).
          for (const client of wss.clients) {
            try {
              client.terminate();
            } catch {
              /* ignore */
            }
          }
          await new Promise<void>((res) => {
            http.close(() => res());
          });
          sessions.shutdown();
        },
        _sessions() {
          return sessions;
        },
      };
      resolve(handle);
    };
    http.once("error", onError);
    http.once("listening", onListening);
    http.listen(port, host);
  });
}
