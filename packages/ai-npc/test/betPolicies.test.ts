import { describe, it, expect } from "vitest";
import type { RuleSet } from "@blackjack/engine";
import { VEGAS } from "@blackjack/engine";
import { decideBet, type BetContext } from "../src/betPolicies.js";

const rules: RuleSet = VEGAS; // minBet 5, maxBet 500

function ctx(overrides: Partial<BetContext> = {}): BetContext {
  return {
    bankroll: 1000,
    rules,
    ...overrides,
  };
}

describe("decideBet — flat", () => {
  it("returns the unit clamped to minBet", () => {
    const r = decideBet("flat", ctx({ unit: 10 }));
    expect(r.amount).toBe(10);
    expect(r.rationale).toBe("flat");
  });
  it("falls back to rules.minBet when unit is not provided", () => {
    const r = decideBet("flat", ctx());
    expect(r.amount).toBe(rules.minBet);
  });
  it("clamps a too-small unit up to minBet", () => {
    const r = decideBet("flat", ctx({ unit: 1 }));
    expect(r.amount).toBe(rules.minBet);
  });
});

describe("decideBet — reverse-martingale", () => {
  it("doubles on win", () => {
    const r = decideBet(
      "reverse-martingale",
      ctx({ unit: 10, currentBet: 10, lastResult: "win" }),
    );
    expect(r.amount).toBe(20);
  });
  it("doubles on blackjack", () => {
    const r = decideBet(
      "reverse-martingale",
      ctx({ unit: 10, currentBet: 20, lastResult: "blackjack" }),
    );
    expect(r.amount).toBe(40);
  });
  it("caps at 4x unit", () => {
    const r = decideBet(
      "reverse-martingale",
      ctx({ unit: 10, currentBet: 40, lastResult: "win" }),
    );
    // 40 * 2 = 80 > 4*10=40 cap → 40
    expect(r.amount).toBe(40);
  });
  it("resets to unit on loss", () => {
    const r = decideBet(
      "reverse-martingale",
      ctx({ unit: 10, currentBet: 40, lastResult: "loss" }),
    );
    expect(r.amount).toBe(10);
  });
  it("resets on bust and surrender", () => {
    expect(
      decideBet(
        "reverse-martingale",
        ctx({ unit: 10, currentBet: 40, lastResult: "bust" }),
      ).amount,
    ).toBe(10);
    expect(
      decideBet(
        "reverse-martingale",
        ctx({ unit: 10, currentBet: 40, lastResult: "surrender" }),
      ).amount,
    ).toBe(10);
  });
  it("holds on push", () => {
    const r = decideBet(
      "reverse-martingale",
      ctx({ unit: 10, currentBet: 20, lastResult: "push" }),
    );
    expect(r.amount).toBe(20);
  });
});

describe("decideBet — kelly", () => {
  it("trueCount 0 yields minBet (multiplier clamped to 1)", () => {
    const r = decideBet("kelly", ctx({ unit: 10, trueCount: 0 }));
    expect(r.amount).toBe(10);
    expect(r.rationale).toContain("Kelly");
  });
  it("trueCount 1 yields 1 unit", () => {
    const r = decideBet("kelly", ctx({ unit: 10, trueCount: 1 }));
    // floor(1 - 0.5) = 0 → clamp to 1 → 10
    expect(r.amount).toBe(10);
  });
  it("trueCount 2 yields 1 unit (floor(1.5)=1)", () => {
    const r = decideBet("kelly", ctx({ unit: 10, trueCount: 2 }));
    expect(r.amount).toBe(10);
  });
  it("trueCount 3 yields 2 units (floor(2.5)=2)", () => {
    const r = decideBet("kelly", ctx({ unit: 10, trueCount: 3 }));
    expect(r.amount).toBe(20);
  });
  it("trueCount 8.5 yields 8 units (multiplier clamped to 8)", () => {
    const r = decideBet("kelly", ctx({ unit: 10, trueCount: 8.5 }));
    // floor(8.5-0.5)=8 → 10*8 = 80
    expect(r.amount).toBe(80);
  });
  it("large trueCount clamps to maxBet", () => {
    const r = decideBet(
      "kelly",
      ctx({ unit: 100, trueCount: 20 }),
    );
    // multiplier clamped to 8 → 100*8 = 800 → clamped to maxBet 500
    expect(r.amount).toBe(rules.maxBet);
  });
});

describe("decideBet — unit-spread", () => {
  it("streak +3 → 4 units", () => {
    const r = decideBet("unit-spread", ctx({ unit: 10, streak: 3 }));
    expect(r.amount).toBe(40);
  });
  it("streak +1 → 2 units", () => {
    const r = decideBet("unit-spread", ctx({ unit: 10, streak: 1 }));
    expect(r.amount).toBe(20);
  });
  it("streak -2 → 1 unit (don't chase)", () => {
    const r = decideBet("unit-spread", ctx({ unit: 10, streak: -2 }));
    expect(r.amount).toBe(10);
  });
  it("no streak → 1 unit", () => {
    const r = decideBet("unit-spread", ctx({ unit: 10 }));
    expect(r.amount).toBe(10);
  });
});

describe("decideBet — bankroll clamp", () => {
  it("flat clamps to bankroll", () => {
    const r = decideBet(
      "flat",
      ctx({ unit: 100, bankroll: 30 }),
    );
    expect(r.amount).toBe(30);
  });
  it("kelly clamps to bankroll", () => {
    const r = decideBet(
      "kelly",
      ctx({ unit: 100, trueCount: 8, bankroll: 150 }),
    );
    expect(r.amount).toBe(150);
  });
  it("unit-spread clamps to bankroll on hot streak", () => {
    const r = decideBet(
      "unit-spread",
      ctx({ unit: 50, streak: 5, bankroll: 100 }),
    );
    // 50*4 = 200 → clamped to bankroll 100
    expect(r.amount).toBe(100);
  });
  it("reverse-martingale clamps to bankroll", () => {
    const r = decideBet(
      "reverse-martingale",
      ctx({ unit: 25, currentBet: 50, lastResult: "win", bankroll: 60 }),
    );
    // 50*2 = 100 → cap 4*25=100 → clamped to bankroll 60
    expect(r.amount).toBe(60);
  });
});
