import { describe, it, expect } from "vitest";
import type { Card, Rank } from "@blackjack/engine";
import {
  newCounter,
  observe,
  runningCount,
  decksRemaining,
  trueCount,
  reset,
  hiLoValue,
} from "../src/hiLoCounter.js";

function c(rank: Rank): Card {
  return { rank, suit: "♠" };
}

describe("hiLoCounter", () => {
  describe("newCounter", () => {
    it("starts at zero with the given deck count", () => {
      const s = newCounter(6);
      expect(s.runningCount).toBe(0);
      expect(s.cardsSeen).toBe(0);
      expect(s.decks).toBe(6);
      expect(runningCount(s)).toBe(0);
      expect(trueCount(s)).toBe(0);
    });
  });

  describe("hiLoValue", () => {
    it("maps 2-6 to +1", () => {
      expect(hiLoValue("2")).toBe(1);
      expect(hiLoValue("3")).toBe(1);
      expect(hiLoValue("4")).toBe(1);
      expect(hiLoValue("5")).toBe(1);
      expect(hiLoValue("6")).toBe(1);
    });
    it("maps 7-9 to 0", () => {
      expect(hiLoValue("7")).toBe(0);
      expect(hiLoValue("8")).toBe(0);
      expect(hiLoValue("9")).toBe(0);
    });
    it("maps 10, J, Q, K, A to -1", () => {
      expect(hiLoValue("10")).toBe(-1);
      expect(hiLoValue("J")).toBe(-1);
      expect(hiLoValue("Q")).toBe(-1);
      expect(hiLoValue("K")).toBe(-1);
      expect(hiLoValue("A")).toBe(-1);
    });
  });

  describe("observe", () => {
    it("is pure — does not mutate input", () => {
      const s = newCounter(6);
      const s2 = observe(s, c("5"));
      expect(s.runningCount).toBe(0);
      expect(s.cardsSeen).toBe(0);
      expect(s2.runningCount).toBe(1);
      expect(s2.cardsSeen).toBe(1);
    });

    it("accumulates +1 cards correctly", () => {
      let s = newCounter(6);
      for (const r of ["2", "3", "4", "5", "6"] as Rank[]) {
        s = observe(s, c(r));
      }
      expect(runningCount(s)).toBe(5);
      expect(s.cardsSeen).toBe(5);
    });

    it("mixed observations sum to the net running count", () => {
      let s = newCounter(6);
      // +1, +1, 0, -1 → net +1
      s = observe(s, c("2"));
      s = observe(s, c("6"));
      s = observe(s, c("8"));
      s = observe(s, c("K"));
      expect(runningCount(s)).toBe(1);
      expect(s.cardsSeen).toBe(4);
    });
  });

  describe("decksRemaining + trueCount", () => {
    it("decksRemaining = (decks*52 - cardsSeen) / 52", () => {
      const s = newCounter(6);
      expect(decksRemaining(s)).toBe(6);
      let s2 = s;
      for (let i = 0; i < 52; i++) s2 = observe(s2, c("8")); // 52 neutrals
      expect(decksRemaining(s2)).toBe(5);
    });

    it("trueCount = runningCount / decksRemaining", () => {
      let s = newCounter(6);
      // Observe 52 cards (1 deck) all +1 → running=52 but that's impossible;
      // use 10 +1 cards and check tc = 10 / 5.xx decks ≈ running/decksLeft.
      for (let i = 0; i < 10; i++) s = observe(s, c("5"));
      const dr = decksRemaining(s);
      expect(dr).toBeCloseTo((6 * 52 - 10) / 52, 6);
      expect(trueCount(s)).toBeCloseTo(10 / dr, 6);
    });

    it("returns runningCount when decksRemaining < 0.5 (shoe end)", () => {
      // 6 decks = 312 cards. Leave < 26 cards → see > 286 cards.
      let s = newCounter(6);
      // seed a running count of +3
      s = observe(s, c("5"));
      s = observe(s, c("5"));
      s = observe(s, c("5"));
      // burn neutrals to push cardsSeen past threshold
      for (let i = 0; i < 290; i++) s = observe(s, c("8"));
      expect(decksRemaining(s)).toBeLessThan(0.5);
      expect(trueCount(s)).toBe(3);
    });
  });

  describe("reset", () => {
    it("preserves decks and zeros counts", () => {
      let s = newCounter(8);
      s = observe(s, c("2"));
      s = observe(s, c("A"));
      s = observe(s, c("5"));
      const r = reset(s);
      expect(r.decks).toBe(8);
      expect(r.runningCount).toBe(0);
      expect(r.cardsSeen).toBe(0);
      // original unchanged (pure)
      expect(s.cardsSeen).toBe(3);
    });
  });
});
