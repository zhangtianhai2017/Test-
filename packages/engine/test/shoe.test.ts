import { describe, it, expect } from "vitest";
import { createShoe, buildDeck } from "../src/cards.js";
import { mulberry32 } from "../src/rng.js";

describe("shoe", () => {
  it("builds 52 cards per deck", () => {
    expect(buildDeck({ decks: 1 })).toHaveLength(52);
    expect(buildDeck({ decks: 6 })).toHaveLength(312);
  });
  it("removes tens for Spanish 21 (48 per deck)", () => {
    expect(buildDeck({ decks: 1, removeTens: true })).toHaveLength(48);
  });
  it("same seed → same draw order (deterministic)", () => {
    const a = createShoe(mulberry32(42), { decks: 6 });
    const b = createShoe(mulberry32(42), { decks: 6 });
    for (let i = 0; i < 50; i++) {
      const x = a.draw();
      const y = b.draw();
      expect(x.rank).toBe(y.rank);
      expect(x.suit).toBe(y.suit);
    }
  });
  it("needsShuffle triggers around cut card", () => {
    const s = createShoe(mulberry32(1), { decks: 1, penetration: 0.5 });
    for (let i = 0; i < 25; i++) s.draw();
    expect(s.needsShuffle()).toBe(false);
    for (let i = 0; i < 5; i++) s.draw();
    expect(s.needsShuffle()).toBe(true);
  });
});
