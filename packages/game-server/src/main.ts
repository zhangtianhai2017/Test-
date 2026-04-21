/**
 * @blackjack/game-server — authoritative Node.js game server.
 *
 * Module layout (filled in by M3b..e and M4):
 *   protocol/     — zod message schemas, shared with UE client
 *   server/       — WebSocket server + connection manager
 *   session/      — per-connection session state
 *   lobby/        — table registry + join/create flows
 *   table/        — per-table game loop (wraps @blackjack/engine)
 *   dealerClient.ts — HTTP client to @blackjack/dealer-ai
 *   log.ts
 *   main.ts       — this file; CLI + bootstrap
 *
 * D-016, D-017, D-018, D-020, D-022 for the decisions behind this module.
 */

import { log } from "./log.js";

async function main(): Promise<void> {
  log.info({ version: "0.1.0" }, "game-server scaffold loaded");
  // WebSocket server bootstrap is M3c. This scaffold just exits cleanly.
}

main().catch((err) => {
  log.error({ err }, "fatal");
  process.exit(1);
});
