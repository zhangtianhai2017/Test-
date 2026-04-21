import { describe, it, expect } from "vitest";
import { __moduleScaffolded } from "../src/index.js";

describe("@blackjack/ai-npc scaffold", () => {
  it("package loads", () => {
    expect(__moduleScaffolded).toBe(true);
  });
});
