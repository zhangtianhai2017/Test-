# game-server — STATE

Updated: 2026-04-21 after M3 complete (PM)

## Files
- `src/protocol/` — 4 files, zod schemas + types (frames.ts, client.ts, server.ts, index.ts)
- `src/session/` — session.ts + sessionManager.ts (uuid, 45s grace, onExpire hook)
- `src/lobby/` — table.ts + lobby.ts + toProtocol.ts (state→wire mapping)
- `src/server/` — wsServer.ts + dispatch.ts (WebSocket lifecycle + frame router)
- `src/main.ts` — CLI entry with SIGINT/SIGTERM handlers
- `src/log.ts` — pino + pino-pretty dev transport
- `test/` — 4 files, **39 tests**, 0 skipped, 0 failed
  - scaffold.test.ts (1) — import sanity
  - protocol.test.ts (15) — zod validation + round-trip
  - server.test.ts (11) — WS lifecycle + session reconnect
  - lobby.test.ts (12) — table creation + seat ownership + broadcasts + grace-expire

## Recent work — M3 complete

**M3a scaffold** 3122c1d  
**M3b protocol schemas** 89032d4 — 19 client frames + 25 server frames,
both discriminated unions (server uses z.union because CardDealtFrame
has superRefine).  
**M3c WS server** 4c76ae2 — startGameServer() + SessionManager with
45s reconnect grace per D-022, HELLO/WELCOME/PING/PONG, RESUME_FAILED.  
**M3d lobby + seats** 6b033d7 — Lobby registry, TABLE_CREATED,
LIST_TABLES, JOIN_TABLE (optional seatRequest), LEAVE_TABLE,
CLAIM_SEAT, RELEASE_SEAT, CONFIGURE_TABLE; SEAT_ASSIGNED and
SEAT_RELEASED broadcasts; grace-expire auto-cleanup.

M3e (integration test) deferred into M4, since a true full-round
integration test needs the game loop.

## Commit chain
3122c1d (M3a) → 89032d4 (M3b) → 4c76ae2 (M3c) → 6b033d7 (M3d).

## Known unfinished / upcoming
- **M4** — wire game actions (PLACE_BET, HIT, STAND, DOUBLE, SPLIT,
  SURRENDER, INSURE/DECLINE_INSURANCE, NEW_ROUND, GESTURE) through to
  the engine. Broadcast the resulting events (CARD_DEALT,
  HAND_BUST, NATURAL_BLACKJACK, PLAYER_ACTION, DEALER_ACTION,
  HOLE_CARD_REVEALED, BET_SETTLED, ROUND_OVER, SIDEBET_WIN,
  BANKROLL_CHANGED, SHOE_SHUFFLED, PHASE_CHANGED, GESTURE_MADE) to
  all table members.
- **M4** — NPC auto-drive. When activeSeatIndex points to an NPC
  seat, server calls `npcDecidePlay(...)` (or `npcDecideBet` during
  betting) and dispatches the resulting engine action on its behalf.
  Include a per-NPC decision delay so it doesn't fire instantly.
- **M9/M11** — dealer-ai HTTP client (for quips/TTS).

## Open issues
None.

## Design quirks worth remembering
- ServerFrame union is `z.union`, not `z.discriminatedUnion`, because
  CardDealtFrame uses `.superRefine` (a ZodEffects, which
  discriminatedUnion rejects). Runtime branch narrowing on `.type`
  still works fine.
- TABLE_STATE dealer uses `MaybeHiddenCard = CardPayload | {faceDown:true}`
  so the hole card is a zero-information placeholder.
- TABLE_DELTA patch is an open-shape `z.record(z.unknown())` with
  monotonic seq — deliberately underspecified to allow iterative diff
  formats without protocol version bumps.
- Lobby's `releaseSeatsFor` best-effort-dispatches engine RELEASE_SEAT
  and swallows phase errors so disconnects mid-round don't lock seats.
