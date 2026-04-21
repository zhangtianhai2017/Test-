# AGENT — game-server module

You are the maintainer of the `packages/game-server` module. Read this
whole file before touching code.

## Purpose

Authoritative game server. A Node.js process that:

1. Owns the shoe, dealer, and all game state for every table. Clients never
   see what they shouldn't (face-down cards stay server-side).
2. Accepts WebSocket connections from UE clients (and, for local single-
   player, from the UE launcher connecting to 127.0.0.1).
3. Multiplexes 1..N tables simultaneously.
4. Runs NPC seats via `@blackjack/ai-npc` (server-side; clients just watch).
5. Forwards event context to `dealer-ai` (Python, separate HTTP service)
   to generate dealer quips, broadcasts quips/audio back to relevant
   clients.
6. Handles session lifecycle: join table, claim seat(s), disconnect,
   reconnect, timeout → seat-to-NPC fallback.

## Scope — what you own

```
packages/game-server/
├── package.json
├── tsconfig.json
├── src/
│   ├── main.ts              ← entry point (CLI, config, listen)
│   ├── protocol/            ← message schemas (shared with UE client)
│   ├── server/              ← WebSocket server, connection manager
│   ├── lobby/               ← table list, join/create
│   ├── table/               ← per-table game loop, calls @blackjack/engine
│   ├── session/             ← per-connection session state
│   ├── dealerClient.ts      ← HTTP client to dealer-ai
│   └── log.ts
└── test/
```

## Scope — what you do NOT own

- Rules logic: use `@blackjack/engine` directly. If rules need changes, that's
  an engine module escalation.
- NPC decisions: use `@blackjack/ai-npc`. Don't inline strategy.
- Text/voice generation: HTTP-call `dealer-ai`. Don't embed an LLM.
- Client rendering: that's UE.

## Key invariants

1. **Server is authoritative.** Clients send *intent* (e.g. `{type:"hit"}`);
   server validates and mutates state. Clients never compute outcomes.
2. **No face-down card in public state.** Dealer hole card is omitted from
   any broadcast until the reveal phase.
3. **Idempotent + idempotency-keyed actions.** A dropped-reconnect client
   resends the last action; server must recognize repeats via a client-
   supplied `action_id` and not double-apply.
4. **Deterministic with seed** (same as engine). Table state should be
   replayable from seed + action log for debugging.
5. **Node runtime, TypeScript strict.** No CommonJS, use ESM.
6. **Cross-platform.** Runs on Linux (dev) and Windows (prod). No
   Unix-only signals in code paths needed for production.

## Protocol (sketch — finalize in M3)

WebSocket at `/game`. JSON frames. Every frame has `{v:1, type, ...}`.

Client → Server:
```
{type:"HELLO", clientId, displayName}
{type:"LIST_TABLES"}
{type:"CREATE_TABLE", config:{ruleSet, seats:[...]}, persona:"veteran", language:"zh"}
{type:"JOIN_TABLE", tableId, seatRequest:[1,2]}    // claim seats 1 and 2
{type:"LEAVE_TABLE"}
{type:"PLACE_BET", seatIndex, amount, sideBets?}
{type:"HIT"|"STAND"|"DOUBLE"|"SPLIT"|"SURRENDER", seatIndex, actionId}
{type:"INSURE"|"DECLINE_INSURANCE", seatIndex, amount?}
{type:"GESTURE", gesture, targetSeatIndex?}
{type:"NEW_ROUND"}
{type:"PING"}
```

Server → Client:
```
{type:"WELCOME", sessionId, serverVersion}
{type:"TABLE_STATE", fullSnapshot}                   // authoritative state
{type:"TABLE_DELTA", patch}                          // incremental updates
{type:"SEAT_ASSIGNED", seatIndex, ownerClientId}
{type:"PHASE_CHANGED", phase}
{type:"CARD_DEALT", to, handIndex, card, faceDown}   // faceDown=true hides rank/suit
{type:"DEALER_QUIP", text, tone, language, audioUrl?}
{type:"ERROR", code, message, actionIdRef?}
{type:"PONG"}
```

## Single-player / local mode

When UE launches in single-player mode:
1. UE spawns `game-server.exe` as a subprocess bound to `127.0.0.1:7878`.
2. UE spawns `dealer-ai.exe` as a subprocess bound to `127.0.0.1:8787`.
3. UE connects to `ws://127.0.0.1:7878/game` like any client.
4. UE creates a table and claims 1 or more seats, fills remaining with NPCs.
5. On UE exit, both subprocesses shut down.

Implementation: UE launcher passes `--single-player` flag; server uses a
different bind + shuts down on parent death.

## Dependencies

- `ws` — WebSocket server
- `@blackjack/engine` — rules
- `@blackjack/ai-npc` — NPC decisions
- `zod` — protocol validation
- `pino` — structured logs
- `tsx` — dev runtime
- `esbuild` or `tsup` — production bundling

## Tests

- Unit tests per module (session, lobby, table)
- Integration tests that spin up a real server and drive it via a fake WS
  client, playing through scenarios (single seat, multi-seat, two clients,
  disconnect + reconnect, NPC-fills-disconnected-seat)

## Escalation triggers

- Protocol field name change required after a client has shipped — must
  go through PM, may need versioning
- Rules behavior divergence between server and `@blackjack/engine` — this
  should be impossible if you only use the engine as a black box
- Auth / account feature requests — out of scope in v1 per D-019

## Packaging for Windows

Use `pkg` or (recommended) `@yao-pkg/pkg` or `bun build --compile` to
produce a single `game-server.exe`. Ships alongside `dealer-ai.exe`.

## Known complexities to watch

- **Reconnect window**: when a client drops, their seats must not be
  auto-cleaned immediately. Grace period (e.g. 45 s), then:
  - configured NPC mode: seat becomes NPC
  - configured empty mode: seat becomes empty and the round can finish
- **Betting window timer**: server enforces; clients see countdown
- **Action-out-of-turn**: reject with clear error code
- **Client-side anti-cheat**: none needed per se — server is authoritative.
  Just rate-limit to prevent spam.
