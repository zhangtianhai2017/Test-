/**
 * Registry of `Session` objects with reconnect support.
 *
 * Responsibilities (D-022):
 *  - Own the session map keyed by UUID.
 *  - Create new sessions on HELLO.
 *  - On socket close, move a session to a "grace" state with a deadline; a
 *    reconnecting client can resume before the deadline.
 *  - Periodically sweep and evict expired sessions.
 *
 * The manager is deliberately ignorant of table/lobby state: it just logs a
 * reminder when a session with a `tableId` is evicted so M3d can plug in
 * cleanup without a circular dependency.
 */
import type { WebSocket } from "ws";

import { log } from "../log.js";
import { newSession, type Session } from "./session.js";

export interface SessionManager {
  /** Create a brand-new session for a HELLO without a resume id. */
  create(displayName: string, clientVersion: string, socket: WebSocket): Session;
  /**
   * Resume an existing session by id. Returns null if the id is unknown or
   * its grace window has elapsed, and null if the session is currently
   * connected (duplicate-login; caller decides how to handle).
   */
  resume(oldSessionId: string, socket: WebSocket): Session | null;
  /** Move the session to grace state; keep it in the map for the grace window. */
  disconnect(sessionId: string): void;
  /** Fully remove a session (e.g. on SESSION_LOST or shutdown). */
  close(sessionId: string, reason: string): void;
  get(sessionId: string): Session | null;
  all(): Session[];
  /** Drop sessions whose grace window has passed. Returns the number evicted. */
  sweepExpired(nowMs?: number): number;
  /** Stop internal timers. Idempotent. */
  shutdown(): void;
}

export interface SessionManagerOptions {
  /** Seconds a disconnected session is kept alive for resume (D-022 default 45). */
  graceSeconds?: number;
  /** How often the sweeper runs (default 5000 ms). */
  sweepIntervalMs?: number;
}

const DEFAULT_GRACE_SECONDS = 45;
const DEFAULT_SWEEP_INTERVAL_MS = 5000;

export function createSessionManager(
  opts: SessionManagerOptions = {},
): SessionManager {
  const graceSeconds = opts.graceSeconds ?? DEFAULT_GRACE_SECONDS;
  const sweepIntervalMs = opts.sweepIntervalMs ?? DEFAULT_SWEEP_INTERVAL_MS;
  const sessions = new Map<string, Session>();

  const mgr: SessionManager = {
    create(displayName, clientVersion, socket) {
      const session = newSession(displayName, clientVersion, socket);
      sessions.set(session.id, session);
      log.debug({ sessionId: session.id, displayName }, "session created");
      return session;
    },

    resume(oldSessionId, socket) {
      const existing = sessions.get(oldSessionId);
      if (!existing) return null;
      // Already connected → duplicate login; refuse.
      if (existing.socket !== null) return null;
      existing.socket = socket;
      existing.graceDeadline = null;
      existing.lastSeenAt = Date.now();
      log.debug({ sessionId: existing.id }, "session resumed");
      return existing;
    },

    disconnect(sessionId) {
      const s = sessions.get(sessionId);
      if (!s) return;
      s.socket = null;
      s.graceDeadline = Date.now() + graceSeconds * 1000;
      log.debug(
        { sessionId, graceDeadline: s.graceDeadline },
        "session disconnected, entering grace",
      );
    },

    close(sessionId, reason) {
      const s = sessions.get(sessionId);
      if (!s) return;
      sessions.delete(sessionId);
      log.debug({ sessionId, reason }, "session closed");
    },

    get(sessionId) {
      return sessions.get(sessionId) ?? null;
    },

    all() {
      return Array.from(sessions.values());
    },

    sweepExpired(nowMs = Date.now()) {
      let dropped = 0;
      for (const [id, s] of sessions) {
        if (s.graceDeadline !== null && s.graceDeadline < nowMs) {
          if (s.tableId !== null) {
            // M3d: lobby/table cleanup will hook in here (remove from table,
            // reassign or release seats, broadcast SEAT_RELEASED).
            log.info(
              { sessionId: id, tableId: s.tableId, ownedSeats: s.ownedSeats },
              "session grace expired; table cleanup pending (M3d)",
            );
          } else {
            log.debug({ sessionId: id }, "session grace expired");
          }
          sessions.delete(id);
          dropped += 1;
        }
      }
      return dropped;
    },

    shutdown() {
      if (timer !== null) {
        clearInterval(timer);
        timer = null;
      }
    },
  };

  // Periodic sweeper. `unref()` so it never holds the process open on its own.
  let timer: ReturnType<typeof setInterval> | null = setInterval(() => {
    mgr.sweepExpired();
  }, sweepIntervalMs);
  if (typeof timer.unref === "function") timer.unref();

  return mgr;
}
