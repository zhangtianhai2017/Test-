/**
 * Tests for the top-level NPC agent (npcDecidePlay / npcDecideBet).
 *
 * These tests focus on the integration contract described in M2e:
 *   - basic-strategy baseline
 *   - static deviationRules override the baseline (when legal)
 *   - playNoise + tilt × tiltPlayImpact produce occasional random legal actions
 *   - bet policy is wired through with unit = minBet × betUnitMultiplier
 *   - tilt inflates/deflates bets (chaser/risk_averse)
 *   - amounts clamp to [minBet, min(maxBet, bankroll)]
 */
import { describe, it, expect } from "vitest";
import type { Card, Rank, Seat, PlayerHand } from "@blackjack/engine";
import { VEGAS } from "@blackjack/engine";
import { npcDecidePlay, npcDecideBet } from "../src/npcAgent.js";
import { newCounter, observe } from "../src/hiLoCounter.js";
import type { CounterState } from "../src/hiLoCounter.js";

function card(rank: Rank): Card {
  return { rank, suit: "♠" };
}
function card2(rank: Rank): Card {
  return { rank, suit: "♥" };
}

function hand(cards: readonly Card[], bet = 5): PlayerHand {
  return {
    cards: [...cards],
    bet,
    doubled: false,
    surrendered: false,
    settled: false,
    stood: false,
    splitFromAces: false,
  };
}

function npcSeat(
  playerCards: readonly Card[],
  overrides: Partial<{
    bankroll: number;
    tilt: number;
    index: number;
  }> = {},
): Seat {
  return {
    index: overrides.index ?? 0,
    player: {
      id: "npc-0",
      name: "NPC",
      kind: "npc",
      bankroll: overrides.bankroll ?? 1000,
    },
    hands: [hand(playerCards)],
    activeHandIndex: 0,
    pendingBet: 0,
    sideBets: { perfectPairs: 0, twentyOneP3: 0, luckyLadies: 0 },
    insuranceBet: 0,
    gestures: [],
    tilt: overrides.tilt ?? 0,
    ownerSessionId: null,
  };
}

function humanSeat(playerCards: readonly Card[]): Seat {
  const s = npcSeat(playerCards);
  s.player.kind = "human";
  return s;
}

/** Build a counter state with a forced runningCount / decksRemaining. */
function counterWithTrueCount(decks: number, target: number): CounterState {
  // Feed low cards (value +1) until we've pushed runningCount high enough that
  // running / decksRemaining ≈ target. We only need true-count ≥ 5 for the
  // kelly test, so be crude.
  let state = newCounter(decks);
  // Feed (target * decks + buffer) +1 cards.
  const need = Math.ceil(target * decks) + 2;
  for (let i = 0; i < need; i++) {
    state = observe(state, card("5")); // +1 Hi-Lo
  }
  return state;
}

describe("npcDecidePlay — optimal personality", () => {
  it("returns surrender on hard 16 vs 10 when canSurrender=true (no noise, no deviations)", () => {
    const seat = npcSeat([card("10"), card2("6")]);
    const action = npcDecidePlay(
      {
        seat,
        dealerUp: card("10"),
        rules: VEGAS,
        canDouble: false,
        canSplit: false,
        canSurrender: true,
      },
      "optimal",
      42,
    );
    expect(action).toBe("surrender");
  });

  it("is deterministic across identical seed+input", () => {
    const seat = npcSeat([card("9"), card2("7")]);
    const input = {
      seat,
      dealerUp: card("10"),
      rules: VEGAS,
      canDouble: false,
      canSplit: false,
      canSurrender: true,
    };
    const a = npcDecidePlay(input, "optimal", 123);
    const b = npcDecidePlay(input, "optimal", 123);
    expect(a).toBe(b);
  });
});

describe("npcDecidePlay — amateur with high tilt (noise is wired)", () => {
  it("over many seeds, sometimes picks a non-basic action", () => {
    // Hard 16 vs 10: basic strategy says "surrender" (or "hit" w/o surrender).
    // With playNoise (0.08) + tilt 0.9 × tiltPlayImpact (0.3) = 0.35 effective
    // noise, we should see at least one deviation over 20 seeds.
    const seat = npcSeat([card("10"), card2("6")], { tilt: 0.9 });
    const input = {
      seat,
      dealerUp: card("10"),
      rules: VEGAS,
      canDouble: false,
      canSplit: false,
      canSurrender: true,
    };
    const baseline = "surrender";
    let deviations = 0;
    for (let seed = 1; seed <= 20; seed++) {
      const action = npcDecidePlay(input, "amateur", seed);
      if (action !== baseline) deviations++;
    }
    expect(deviations).toBeGreaterThanOrEqual(1);
  });

  it("with zero tilt and amateur's small base noise, decisions are mostly BS", () => {
    // Same scenario but tilt=0 and a different hand — we just confirm noise
    // doesn't dominate when tilt is disabled.
    const seat = npcSeat([card("10"), card2("10")], { tilt: 0 }); // hard 20
    const input = {
      seat,
      dealerUp: card("6"),
      rules: VEGAS,
      canDouble: false,
      canSplit: false,
      canSurrender: false,
    };
    let bs = 0;
    for (let seed = 1; seed <= 20; seed++) {
      const action = npcDecidePlay(input, "amateur", seed);
      if (action === "stand") bs++;
    }
    // 20 — with 0.08 noise we expect majority = BS. Accept ≥ 15.
    expect(bs).toBeGreaterThanOrEqual(15);
  });
});

describe("npcDecidePlay — risk_averse static deviations", () => {
  it("hits hard 11 vs 10 instead of doubling (deviation fires)", () => {
    const seat = npcSeat([card("6"), card2("5")]);
    const action = npcDecidePlay(
      {
        seat,
        dealerUp: card("10"),
        rules: VEGAS,
        canDouble: true,
        canSplit: false,
        canSurrender: false,
      },
      "risk_averse",
      42,
    );
    expect(action).toBe("hit");
  });

  it("stands on 8,8 vs 10 instead of splitting", () => {
    const seat = npcSeat([card("8"), card2("8")]);
    const action = npcDecidePlay(
      {
        seat,
        dealerUp: card("10"),
        rules: VEGAS,
        canDouble: true,
        canSplit: true,
        canSurrender: false,
      },
      "risk_averse",
      42,
    );
    expect(action).toBe("stand");
  });
});

describe("npcDecidePlay — non-NPC seat throws", () => {
  it("throws when called with kind=human", () => {
    const seat = humanSeat([card("10"), card2("6")]);
    expect(() =>
      npcDecidePlay(
        {
          seat,
          dealerUp: card("10"),
          rules: VEGAS,
          canDouble: false,
          canSplit: false,
          canSurrender: true,
        },
        "optimal",
        1,
      ),
    ).toThrow(/non-NPC/i);
  });
});

describe("npcDecideBet — flat (optimal)", () => {
  it("bets minBet when bankroll is fresh and betUnitMultiplier=1", () => {
    const seat = npcSeat([card("10"), card2("6")], { bankroll: 1000 });
    const amount = npcDecideBet(
      { seat, rules: VEGAS },
      "optimal",
      7,
    );
    expect(amount).toBe(VEGAS.minBet); // 5
  });
});

describe("npcDecideBet — kelly (counter) true-count spread", () => {
  it("scales bet up when true count is high", () => {
    const seat = npcSeat([card("10"), card2("6")], { bankroll: 1000 });
    const counter = counterWithTrueCount(VEGAS.decks, 5);
    const amount = npcDecideBet(
      { seat, rules: VEGAS, counter },
      "counter",
      7,
    );
    // Kelly ramp at tc≈5 yields multiplier ≥ 4 → bet ≥ 2×minBet.
    expect(amount).toBeGreaterThanOrEqual(VEGAS.minBet * 2);
  });

  it("bets at least minBet with no counter state", () => {
    const seat = npcSeat([card("10"), card2("6")], { bankroll: 1000 });
    const amount = npcDecideBet(
      { seat, rules: VEGAS },
      "counter",
      7,
    );
    expect(amount).toBeGreaterThanOrEqual(VEGAS.minBet);
  });
});

describe("npcDecideBet — chaser (reverse-martingale) on win streak", () => {
  it("presses (doubles) on a win while under the 4× cap, inflated by tilt", () => {
    // reverse-martingale caps at 4 × unit. Chaser's unit = minBet × 1 = 5, so
    // cap = 20. Start currentBet below the cap so we see the press.
    const seat = npcSeat([card("10"), card2("6")], { bankroll: 1000, tilt: 0.1 });
    const amount = npcDecideBet(
      {
        seat,
        rules: VEGAS,
        lastResult: "win",
        currentBet: 8,
        streak: 1,
      },
      "chaser",
      7,
    );
    // doubled = 16 (still < cap 20). chaser tiltBetImpact = 0.8 × 0.1 = 8%
    // floor(16 × 1.08) = 17. Allow a small band.
    expect(amount).toBeGreaterThanOrEqual(16);
    expect(amount).toBeLessThanOrEqual(20);
  });

  it("caps at 4× unit even if currentBet is huge", () => {
    const seat = npcSeat([card("10"), card2("6")], { bankroll: 1000, tilt: 0 });
    const amount = npcDecideBet(
      {
        seat,
        rules: VEGAS,
        lastResult: "win",
        currentBet: 100,
        streak: 3,
      },
      "chaser",
      7,
    );
    // unit = 5 → cap = 20. No tilt inflation.
    expect(amount).toBe(20);
  });
});

describe("npcDecideBet — risk_averse deflates under tilt", () => {
  it("high-tilt risk-averse bets ≤ default unit", () => {
    const seat = npcSeat([card("10"), card2("6")], { bankroll: 1000, tilt: 0.9 });
    const amount = npcDecideBet(
      { seat, rules: VEGAS },
      "risk_averse",
      7,
    );
    // flat policy returns unit=minBet=5. tiltBetImpact=-0.4 × 0.9 = -0.36 →
    // floor(5 × 0.64) = 3 → clamp up to minBet=5. So at most unit, and never
    // more than a fresh flat bet.
    const unit = VEGAS.minBet;
    expect(amount).toBeLessThanOrEqual(unit);
    expect(amount).toBeGreaterThanOrEqual(0);
  });
});

describe("npcDecideBet — clamps to bankroll ceiling", () => {
  it("kelly high count + tiny bankroll clamps to bankroll", () => {
    const seat = npcSeat([card("10"), card2("6")], { bankroll: 10 });
    const counter = counterWithTrueCount(VEGAS.decks, 6);
    const amount = npcDecideBet(
      { seat, rules: VEGAS, counter },
      "counter",
      7,
    );
    expect(amount).toBeLessThanOrEqual(10);
  });

  it("throws on non-NPC seat", () => {
    const seat = humanSeat([card("10"), card2("6")]);
    expect(() =>
      npcDecideBet({ seat, rules: VEGAS }, "optimal", 1),
    ).toThrow(/non-NPC/i);
  });
});
