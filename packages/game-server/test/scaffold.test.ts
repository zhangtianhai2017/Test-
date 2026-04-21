import { describe, it, expect } from "vitest";

describe("@blackjack/game-server scaffold", () => {
  it("package loads and types work", async () => {
    // Just prove the workspace resolves and imports work.
    const engine = await import("@blackjack/engine");
    const ainpc = await import("@blackjack/ai-npc");
    expect(typeof engine.createGame).toBe("function");
    expect(typeof ainpc.npcDecidePlay).toBe("function");
  });
});
