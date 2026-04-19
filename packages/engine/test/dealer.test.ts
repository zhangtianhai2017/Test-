import { describe, it, expect } from "vitest";
import { dealerShouldHit } from "../src/dealer.js";
import { VEGAS } from "../src/rules.js";
import type { Card } from "../src/cards.js";

const C = (rank: Card["rank"]): Card => ({ rank, suit: "♠" });

describe("dealer policy", () => {
  it("hits on 16 hard", () => {
    expect(dealerShouldHit([C("10"), C("6")], VEGAS)).toBe(true);
  });
  it("stands on 17 hard", () => {
    expect(dealerShouldHit([C("10"), C("7")], VEGAS)).toBe(false);
  });
  it("hits on soft 17 when H17 ruleset", () => {
    expect(dealerShouldHit([C("A"), C("6")], { ...VEGAS, dealerHitsSoft17: true })).toBe(true);
  });
  it("stands on soft 17 when S17 ruleset", () => {
    expect(dealerShouldHit([C("A"), C("6")], { ...VEGAS, dealerHitsSoft17: false })).toBe(false);
  });
  it("does not hit after bust", () => {
    expect(dealerShouldHit([C("10"), C("10"), C("5")], VEGAS)).toBe(false);
  });
});
