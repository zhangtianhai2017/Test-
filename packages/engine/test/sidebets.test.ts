import { describe, it, expect } from "vitest";
import type { Card } from "../src/cards.js";
import { evalLuckyLadies, evalPerfectPairs, evalTwentyOnePlusThree } from "../src/sidebets.js";

const C = (rank: Card["rank"], suit: Card["suit"]): Card => ({ rank, suit });

describe("Perfect Pairs", () => {
  it("perfect pair (same rank + same suit) = 30:1", () => {
    expect(evalPerfectPairs([C("7", "♠"), C("7", "♠")]).payout).toBe(30);
  });
  it("colored pair (same color, different suit) = 10:1", () => {
    expect(evalPerfectPairs([C("7", "♥"), C("7", "♦")]).payout).toBe(10);
  });
  it("mixed pair (different colors) = 5:1", () => {
    expect(evalPerfectPairs([C("7", "♠"), C("7", "♥")]).payout).toBe(5);
  });
  it("non-pair pays 0", () => {
    expect(evalPerfectPairs([C("7", "♠"), C("8", "♠")]).payout).toBe(0);
  });
});

describe("21+3", () => {
  it("suited trips", () => {
    expect(
      evalTwentyOnePlusThree([C("7", "♠"), C("7", "♠")], C("7", "♠")).payout,
    ).toBe(100);
  });
  it("straight flush", () => {
    expect(
      evalTwentyOnePlusThree([C("5", "♠"), C("6", "♠")], C("7", "♠")).payout,
    ).toBe(40);
  });
  it("three of a kind (mixed suits)", () => {
    expect(
      evalTwentyOnePlusThree([C("7", "♠"), C("7", "♥")], C("7", "♦")).payout,
    ).toBe(30);
  });
  it("straight (mixed suits)", () => {
    expect(
      evalTwentyOnePlusThree([C("5", "♠"), C("6", "♥")], C("7", "♦")).payout,
    ).toBe(10);
  });
  it("flush", () => {
    expect(
      evalTwentyOnePlusThree([C("2", "♠"), C("5", "♠")], C("9", "♠")).payout,
    ).toBe(5);
  });
  it("nothing", () => {
    expect(
      evalTwentyOnePlusThree([C("2", "♠"), C("5", "♥")], C("9", "♦")).payout,
    ).toBe(0);
  });
});

describe("Lucky Ladies", () => {
  it("QQ of hearts + dealer BJ = 1000:1", () => {
    const r = evalLuckyLadies(
      [C("Q", "♥"), C("Q", "♥")],
      [C("A", "♠"), C("K", "♠")],
    );
    expect(r.payout).toBe(1000);
  });
  it("matched 20 (same rank & suit) = 125:1", () => {
    const r = evalLuckyLadies(
      [C("K", "♠"), C("K", "♠")],
      [C("5", "♠"), C("7", "♠")],
    );
    expect(r.payout).toBe(125);
  });
  it("any 20 (different suits, different colors) = 4:1", () => {
    expect(
      evalLuckyLadies([C("K", "♠"), C("10", "♥")], [C("5", "♠"), C("7", "♠")]).payout,
    ).toBe(4);
  });
  it("not a 20 = 0", () => {
    expect(
      evalLuckyLadies([C("K", "♠"), C("8", "♠")], [C("5", "♠"), C("7", "♠")]).payout,
    ).toBe(0);
  });
});
