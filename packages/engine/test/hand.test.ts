import { describe, it, expect } from "vitest";
import { evaluate, isBlackjack, isPair, rankValue } from "../src/hand.js";
import type { Card } from "../src/cards.js";

const C = (rank: Card["rank"], suit: Card["suit"] = "♠"): Card => ({ rank, suit });

describe("rank values", () => {
  it("face cards are 10", () => {
    expect(rankValue("J")).toBe(10);
    expect(rankValue("Q")).toBe(10);
    expect(rankValue("K")).toBe(10);
    expect(rankValue("10")).toBe(10);
  });
  it("ace is 1 (promoted in evaluate)", () => {
    expect(rankValue("A")).toBe(1);
  });
});

describe("evaluate", () => {
  it("hard hand", () => {
    const v = evaluate([C("9"), C("7")]);
    expect(v.total).toBe(16);
    expect(v.soft).toBe(false);
  });
  it("soft hand with ace promoted", () => {
    const v = evaluate([C("A"), C("7")]);
    expect(v.total).toBe(18);
    expect(v.soft).toBe(true);
  });
  it("soft to hard when third card busts soft", () => {
    const v = evaluate([C("A"), C("7"), C("5")]);
    expect(v.total).toBe(13);
    expect(v.soft).toBe(false);
  });
  it("detects bust", () => {
    expect(evaluate([C("10"), C("8"), C("7")]).isBust).toBe(true);
  });
  it("detects 21", () => {
    expect(evaluate([C("A"), C("K")]).is21).toBe(true);
  });
});

describe("isBlackjack / isPair", () => {
  it("natural blackjack only on 2 cards", () => {
    expect(isBlackjack([C("A"), C("K")])).toBe(true);
    expect(isBlackjack([C("7"), C("7"), C("7")])).toBe(false);
  });
  it("pair detection handles 10 and face as pair (same rank value)", () => {
    expect(isPair([C("10"), C("J")])).toBe(true);
    expect(isPair([C("7"), C("7")])).toBe(true);
    expect(isPair([C("7"), C("8")])).toBe(false);
  });
});
