import { describe, it, expect } from "vitest";
import type { Card, Rank, RuleSet } from "@blackjack/engine";
import { VEGAS } from "@blackjack/engine";
import { decideBasicStrategy } from "../src/basicStrategy.js";

// VEGAS is H17 by default. S17 = Vegas with dealerHitsSoft17 flipped off.
const H17: RuleSet = VEGAS;
const S17: RuleSet = { ...VEGAS, dealerHitsSoft17: false };

function c(rank: Rank): Card {
  return { rank, suit: "♠" };
}
function c2(rank: Rank): Card {
  return { rank, suit: "♥" };
}

function baseInput(
  playerCards: readonly Card[],
  dealerUp: Card,
  rules: RuleSet,
  overrides: Partial<{
    canDouble: boolean;
    canSplit: boolean;
    canSurrender: boolean;
    canDoubleAfterSplit: boolean;
  }> = {},
) {
  return {
    playerCards,
    dealerUp,
    rules,
    canDouble: overrides.canDouble ?? true,
    canSplit: overrides.canSplit ?? true,
    canSurrender: overrides.canSurrender ?? true,
    canDoubleAfterSplit: overrides.canDoubleAfterSplit,
  };
}

describe("decideBasicStrategy — hard totals", () => {
  it("hard 16 vs 10 → surrender when allowed, hit otherwise (H17 & S17)", () => {
    const hand = [c("10"), c2("6")]; // hard 16
    const up = c("10");
    for (const rules of [H17, S17]) {
      expect(decideBasicStrategy(baseInput(hand, up, rules))).toBe("surrender");
      expect(
        decideBasicStrategy(
          baseInput(hand, up, rules, { canSurrender: false }),
        ),
      ).toBe("hit");
    }
  });

  it("hard 16 vs 6 → stand", () => {
    const hand = [c("10"), c2("6")];
    const up = c("6");
    expect(decideBasicStrategy(baseInput(hand, up, H17))).toBe("stand");
    expect(decideBasicStrategy(baseInput(hand, up, S17))).toBe("stand");
  });

  it("hard 11 vs 10 → double when allowed, hit otherwise", () => {
    const hand = [c("6"), c2("5")]; // hard 11
    const up = c("10");
    expect(decideBasicStrategy(baseInput(hand, up, H17))).toBe("double");
    expect(
      decideBasicStrategy(baseInput(hand, up, H17, { canDouble: false })),
    ).toBe("hit");
  });

  it("hard 11 vs A → S17 hit; H17 double (else hit)", () => {
    const hand = [c("6"), c2("5")];
    const up = c("A");
    expect(decideBasicStrategy(baseInput(hand, up, S17))).toBe("hit");
    expect(decideBasicStrategy(baseInput(hand, up, H17))).toBe("double");
    expect(
      decideBasicStrategy(baseInput(hand, up, H17, { canDouble: false })),
    ).toBe("hit");
  });

  it("hard 8 vs 5 → hit", () => {
    const hand = [c("5"), c2("3")]; // hard 8
    const up = c("5");
    expect(decideBasicStrategy(baseInput(hand, up, H17))).toBe("hit");
    expect(decideBasicStrategy(baseInput(hand, up, S17))).toBe("hit");
  });
});

describe("decideBasicStrategy — soft totals", () => {
  it("soft 18 (A,7) vs 9 → hit", () => {
    const hand = [c("A"), c2("7")];
    const up = c("9");
    expect(decideBasicStrategy(baseInput(hand, up, H17))).toBe("hit");
    expect(decideBasicStrategy(baseInput(hand, up, S17))).toBe("hit");
  });

  it("soft 18 (A,7) vs 6 → double when allowed, stand otherwise", () => {
    const hand = [c("A"), c2("7")];
    const up = c("6");
    expect(decideBasicStrategy(baseInput(hand, up, H17))).toBe("double");
    expect(decideBasicStrategy(baseInput(hand, up, S17))).toBe("double");
    expect(
      decideBasicStrategy(baseInput(hand, up, H17, { canDouble: false })),
    ).toBe("stand");
    expect(
      decideBasicStrategy(baseInput(hand, up, S17, { canDouble: false })),
    ).toBe("stand");
  });

  it("soft 18 (A,7) vs 2 → S17 stand; H17 double (else stand)", () => {
    const hand = [c("A"), c2("7")];
    const up = c("2");
    expect(decideBasicStrategy(baseInput(hand, up, S17))).toBe("stand");
    expect(decideBasicStrategy(baseInput(hand, up, H17))).toBe("double");
    expect(
      decideBasicStrategy(baseInput(hand, up, H17, { canDouble: false })),
    ).toBe("stand");
  });
});

describe("decideBasicStrategy — pairs", () => {
  it("A,A vs any → split when canSplit", () => {
    const hand = [c("A"), c2("A")];
    for (const up of ["2", "6", "9", "10", "A"] as const) {
      expect(decideBasicStrategy(baseInput(hand, c(up), H17))).toBe("split");
      expect(decideBasicStrategy(baseInput(hand, c(up), S17))).toBe("split");
    }
  });

  it("8,8 vs 10 → split when canSplit", () => {
    const hand = [c("8"), c2("8")];
    const up = c("10");
    expect(decideBasicStrategy(baseInput(hand, up, H17))).toBe("split");
    expect(decideBasicStrategy(baseInput(hand, up, S17))).toBe("split");
  });

  it("10,10 vs 6 → stand (never split; hard 20 stands)", () => {
    const hand = [c("10"), c2("10")];
    const up = c("6");
    expect(decideBasicStrategy(baseInput(hand, up, H17))).toBe("stand");
    // Also verify even when canSplit=false the answer is the same.
    expect(
      decideBasicStrategy(baseInput(hand, up, H17, { canSplit: false })),
    ).toBe("stand");
  });

  it("5,5 vs 9 → double when allowed, hit otherwise (falls through to hard 10)", () => {
    const hand = [c("5"), c2("5")];
    const up = c("9");
    expect(decideBasicStrategy(baseInput(hand, up, H17))).toBe("double");
    expect(
      decideBasicStrategy(baseInput(hand, up, H17, { canDouble: false })),
    ).toBe("hit");
  });
});
