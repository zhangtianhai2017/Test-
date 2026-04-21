/**
 * Per-connection session model.
 *
 * A `Session` is the server's handle on one logical user. It lives longer than
 * a single TCP connection: if the socket drops the session stays in memory
 * for a grace window (D-022, default 45 s) so the client can reconnect and
 * resume. `socket` is nulled during that grace window; a `graceDeadline`
 * records when the session manager will give up and evict.
 *
 * The `tableId` / `ownedSeats` fields are placeholders for M3d — the session
 * manager tracks them only so lobby/table code can do cleanup on eviction.
 */
import type { WebSocket } from "ws";

export interface Session {
  /** Server-assigned UUID, handed back in WELCOME and used for resume. */
  id: string;
  /** Guest nickname from HELLO.displayName. */
  displayName: string;
  /** HELLO.clientVersion, purely informational. */
  clientVersion: string;
  /** Active socket, or null while the session is in its reconnect grace window. */
  socket: WebSocket | null;
  /** Epoch ms when the session was first created. */
  createdAt: number;
  /** Epoch ms of the most recent frame received (or reconnect). */
  lastSeenAt: number;
  /** Epoch ms after which an unclaimed session is evicted; null while connected. */
  graceDeadline: number | null;
  /** Table the session has joined, if any (populated by M3d). */
  tableId: string | null;
  /** Seat indices the session owns on `tableId` (populated by M3d). */
  ownedSeats: number[];
}

/**
 * Build a fresh `Session` with sensible defaults. The manager is responsible
 * for generating the id and inserting into its registry; this helper just
 * centralises the shape so tests and the manager agree.
 */
export function newSession(
  displayName: string,
  clientVersion: string,
  socket: WebSocket,
): Session {
  const now = Date.now();
  return {
    id: globalThis.crypto.randomUUID(),
    displayName,
    clientVersion,
    socket,
    createdAt: now,
    lastSeenAt: now,
    graceDeadline: null,
    tableId: null,
    ownedSeats: [],
  };
}
