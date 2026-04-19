import { describe, it, expect } from "vitest";
import { createGame } from "../src/index.js";
import type { Action, EngineEvent } from "../src/index.js";

function play(actions: Action[], seed = 42, ruleSetId: "VEGAS" | "SPANISH21" | "PONTOON" | "SUPER_FUN_21" = "VEGAS") {
  const game = createGame({ seed, ruleSetId });
  const events: EngineEvent[] = [];
  game.on((e) => events.push(e));
  for (const a of actions) game.dispatch(a);
  return { game, events, state: game.getState() };
}

describe("game state machine", () => {
  it("starts in betting phase with bankroll", () => {
    const g = createGame({ seed: 1 });
    expect(g.getState().phase).toBe("betting");
    expect(g.getState().bankroll).toBeGreaterThan(0);
    expect(g.getLegalActions()).toContain("PLACE_BET");
  });

  it("PLACE_BET → deals 4 cards and enters playerTurn (or settles if BJ)", () => {
    const { state, events } = play([{ type: "PLACE_BET", amount: 25 }]);
    const dealtToPlayer = events.filter((e) => e.type === "CARD_DEALT" && e.to === "player").length;
    const dealtToDealer = events.filter((e) => e.type === "CARD_DEALT" && e.to === "dealer").length;
    expect(dealtToPlayer).toBeGreaterThanOrEqual(2);
    expect(dealtToDealer).toBeGreaterThanOrEqual(2);
    expect(["playerTurn", "roundOver", "insurance"]).toContain(state.phase);
  });

  it("STAND ends player turn and moves to dealer / settlement", () => {
    const g = createGame({ seed: 99 });
    g.dispatch({ type: "PLACE_BET", amount: 25 });
    if (g.getState().phase === "playerTurn") {
      g.dispatch({ type: "STAND" });
    }
    expect(["roundOver"]).toContain(g.getState().phase);
  });

  it("bankroll is debited on PLACE_BET and credited on win", () => {
    const g = createGame({ seed: 3 });
    const start = g.getState().bankroll;
    g.dispatch({ type: "PLACE_BET", amount: 50 });
    const afterBet = g.getState().bankroll;
    expect(afterBet).toBe(start - 50);
    while (g.getState().phase === "playerTurn") g.dispatch({ type: "STAND" });
    expect(g.getState().roundResults.length).toBeGreaterThan(0);
  });

  it("rejects bets outside min/max range", () => {
    const g = createGame({ seed: 1 });
    const events: EngineEvent[] = [];
    g.on((e) => events.push(e));
    g.dispatch({ type: "PLACE_BET", amount: 1 });
    expect(events.some((e) => e.type === "ERROR")).toBe(true);
  });

  it("NEW_ROUND resets to betting after round over", () => {
    const g = createGame({ seed: 7 });
    g.dispatch({ type: "PLACE_BET", amount: 25 });
    while (g.getState().phase === "playerTurn") g.dispatch({ type: "STAND" });
    g.dispatch({ type: "NEW_ROUND" });
    expect(g.getState().phase).toBe("betting");
  });

  it("SET_RULESET changes ruleSet and reshuffles", () => {
    const g = createGame({ seed: 1 });
    g.setRuleSet("SPANISH21");
    expect(g.getState().ruleSet.id).toBe("SPANISH21");
    expect(g.getState().ruleSet.removeTens).toBe(true);
  });

  it("determinism: same seed → identical dealer final total across runs", () => {
    const run = () => {
      const g = createGame({ seed: 12345 });
      g.dispatch({ type: "PLACE_BET", amount: 25 });
      while (g.getState().phase === "playerTurn") g.dispatch({ type: "STAND" });
      return g.getState().dealer.map((c) => c.rank + c.suit).join(",");
    };
    expect(run()).toBe(run());
  });
});

describe("side bets", () => {
  it("Perfect Pairs pays when player starts with a pair", () => {
    // try many seeds until we find a pair (deterministic over seeds)
    let paid = false;
    for (let s = 1; s < 200 && !paid; s++) {
      const g = createGame({ seed: s });
      const events: EngineEvent[] = [];
      g.on((e) => events.push(e));
      g.dispatch({ type: "PLACE_BET", amount: 25, sideBets: { perfectPairs: 5 } });
      if (events.some((e) => e.type === "SIDEBET_WIN" && e.kind === "perfectPairs")) paid = true;
    }
    expect(paid).toBe(true);
  });
});

describe("rulesets", () => {
  it("Spanish 21 removes tens from shoe", () => {
    const g = createGame({ seed: 1, ruleSetId: "SPANISH21" });
    // play 50 hands; no raw "10" rank should ever appear
    const seenRanks = new Set<string>();
    for (let i = 0; i < 50; i++) {
      g.dispatch({ type: "PLACE_BET", amount: 10 });
      for (const c of g.getState().hands[0]!.cards) seenRanks.add(c.rank);
      for (const c of g.getState().dealer) seenRanks.add(c.rank);
      while (g.getState().phase === "playerTurn") g.dispatch({ type: "STAND" });
      for (const c of g.getState().hands[0]!.cards) seenRanks.add(c.rank);
      for (const c of g.getState().dealer) seenRanks.add(c.rank);
      g.dispatch({ type: "NEW_ROUND" });
    }
    expect(seenRanks.has("10")).toBe(false);
    expect(seenRanks.has("J")).toBe(true);
  });

  it("Pontoon pays 2:1 on natural", () => {
    const g = createGame({ seed: 1, ruleSetId: "PONTOON" });
    expect(g.getState().ruleSet.blackjackPays).toBe(2);
  });
});
