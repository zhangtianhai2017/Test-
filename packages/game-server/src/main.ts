/**
 * @blackjack/game-server — authoritative Node.js game server.
 *
 * Module layout (filled in by M3b..e and M4):
 *   protocol/     — zod message schemas, shared with UE client
 *   server/       — WebSocket server + connection manager (M3c)
 *   session/      — per-connection session state (M3c)
 *   lobby/        — table registry + join/create flows (M3d)
 *   table/        — per-table game loop (wraps @blackjack/engine) (M4)
 *   dealerClient.ts — HTTP client to @blackjack/dealer-ai (M9)
 *   log.ts
 *   main.ts       — this file; CLI + bootstrap
 *
 * D-016, D-017, D-018, D-020, D-022 for the decisions behind this module.
 */

import { startGameServer } from "./server/wsServer.js";
import { log } from "./log.js";

async function main(): Promise<void> {
  const host = process.env.GAME_SERVER_HOST ?? "127.0.0.1";
  const port = Number(process.env.GAME_SERVER_PORT ?? 7878);

  const handle = await startGameServer({ host, port });
  const { host: h, port: p } = handle.address();
  log.info({ host: h, port: p }, "game-server listening");

  const shutdown = async (): Promise<void> => {
    log.info("shutting down");
    await handle.close();
    process.exit(0);
  };
  process.on("SIGINT", shutdown);
  process.on("SIGTERM", shutdown);
}

main().catch((err) => {
  log.error({ err }, "fatal");
  process.exit(1);
});
