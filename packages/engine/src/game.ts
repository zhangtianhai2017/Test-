import type { Card } from "./cards.js";
import { createShoe, type Shoe } from "./cards.js";
import { evaluate, isBlackjack, isPair, rankValue } from "./hand.js";
import type { RuleSet } from "./rules.js";
import { PRESETS, type RuleSetId } from "./rules.js";
import { mulberry32, type Rng } from "./rng.js";
import { dealerShouldHit } from "./dealer.js";
import { EventBus, type Listener } from "./events.js";
import {
  evalLuckyLadies,
  evalPerfectPairs,
  evalTwentyOnePlusThree,
} from "./sidebets.js";

export type Phase =
  | "betting"
  | "dealing"
  | "insurance"
  | "playerTurn"
  | "dealerTurn"
  | "settlement"
  | "roundOver";

export type Action =
  | { type: "PLACE_BET"; amount: number; sideBets?: Partial<SideBets> }
  | { type: "DEAL" }
  | { type: "HIT" }
  | { type: "STAND" }
  | { type: "DOUBLE" }
  | { type: "SPLIT" }
  | { type: "SURRENDER" }
  | { type: "INSURE"; amount: number }
  | { type: "DECLINE_INSURANCE" }
  | { type: "NEW_ROUND" }
  | { type: "SET_RULESET"; preset: RuleSetId };

export type ActionType = Action["type"];

export interface SideBets {
  perfectPairs: number;
  twentyOneP3: number;
  luckyLadies: number;
}

export interface PlayerHand {
  cards: Card[];
  bet: number;
  doubled: boolean;
  surrendered: boolean;
  settled: boolean;
  stood: boolean;
  splitFromAces: boolean;
}

export type Outcome =
  | "win"
  | "loss"
  | "push"
  | "blackjack"
  | "surrender"
  | "bust";

export interface HandResult {
  handIndex: number;
  outcome: Outcome;
  payout: number;
  total: number;
  cards: readonly Card[];
  label?: string;
}

export interface GameSnapshot {
  phase: Phase;
  ruleSet: RuleSet;
  bankroll: number;
  dealer: Card[];
  dealerHoleHidden: boolean;
  hands: PlayerHand[];
  activeHandIndex: number;
  pendingBet: number;
  sideBets: SideBets;
  insuranceBet: number;
  roundResults: HandResult[];
  legalActions: ActionType[];
  handValues: { total: number; soft: boolean; isBust: boolean; is21: boolean }[];
  dealerValue: { total: number; soft: boolean; isBust: boolean; is21: boolean };
}

export interface CreateGameOptions {
  ruleSetId?: RuleSetId;
  seed?: number;
  bankroll?: number;
}

export interface Game {
  getState(): GameSnapshot;
  dispatch(action: Action): void;
  on(listener: Listener): () => void;
  getLegalActions(): ActionType[];
  setRuleSet(id: RuleSetId): void;
}

export type SeatKind = "empty" | "human" | "npc";

export type NpcPersonality =
  | "optimal" | "counter" | "amateur" | "chaser"
  | "superstitious" | "ritualistic" | "risk_averse";

export type Gesture =
  | "confident" | "nervous" | "poker-face" | "taunt" | "sigh" | "celebrate";

export interface Player {
  id: string;
  name: string;
  kind: SeatKind;
  bankroll: number;
  personality?: NpcPersonality;
}

export interface Seat {
  index: number;
  player: Player;
  hands: PlayerHand[];
  activeHandIndex: number;
  pendingBet: number;
  sideBets: SideBets;
  insuranceBet: number;
  gestures: Gesture[];
  tilt: number;
  ownerSessionId: string | null;
}

export function createGame(opts: CreateGameOptions = {}): Game {
  const bus = new EventBus();
  let rules: RuleSet = PRESETS[opts.ruleSetId ?? "VEGAS"];
  const rng: Rng = mulberry32(opts.seed ?? Date.now() & 0xffffffff);
  let shoe: Shoe = createShoe(rng, {
    decks: rules.decks,
    penetration: rules.penetration,
    removeTens: rules.removeTens,
  });
  let bankroll = opts.bankroll ?? rules.startingBankroll;
  let phase: Phase = "betting";
  let dealer: Card[] = [];
  let dealerHoleHidden = true;
  let hands: PlayerHand[] = [];
  let activeHandIndex = 0;
  let pendingBet = 0;
  let sideBets: SideBets = { perfectPairs: 0, twentyOneP3: 0, luckyLadies: 0 };
  let insuranceBet = 0;
  let roundResults: HandResult[] = [];
  let splitCount = 0;

  const setPhase = (p: Phase): void => {
    if (phase !== p) {
      phase = p;
      bus.emit({ type: "PHASE_CHANGED", phase });
    }
  };

  const adjustBankroll = (delta: number): void => {
    bankroll += delta;
    bus.emit({ type: "BANKROLL_CHANGED", bankroll, delta });
  };

  const legalActions = (): ActionType[] => {
    if (phase === "betting") return ["PLACE_BET", "SET_RULESET"];
    if (phase === "dealing") return [];
    if (phase === "insurance") return ["INSURE", "DECLINE_INSURANCE"];
    if (phase === "playerTurn") {
      const h = hands[activeHandIndex];
      if (!h) return [];
      const acts: ActionType[] = ["HIT", "STAND"];
      if (h.cards.length === 2 && !h.splitFromAces) {
        acts.push("DOUBLE");
        if (isPair(h.cards) && splitCount < rules.maxSplits) acts.push("SPLIT");
        if (rules.allowSurrender && hands.length === 1) acts.push("SURRENDER");
      }
      return acts;
    }
    if (phase === "roundOver") return ["NEW_ROUND", "SET_RULESET"];
    return [];
  };

  const snapshot = (): GameSnapshot => ({
    phase,
    ruleSet: rules,
    bankroll,
    dealer: dealer.slice(),
    dealerHoleHidden,
    hands: hands.map((h) => ({ ...h, cards: h.cards.slice() })),
    activeHandIndex,
    pendingBet,
    sideBets: { ...sideBets },
    insuranceBet,
    roundResults: roundResults.slice(),
    legalActions: legalActions(),
    handValues: hands.map((h) => evaluate(h.cards)),
    dealerValue: evaluate(
      dealerHoleHidden && dealer.length > 1 ? [dealer[0]!] : dealer,
    ),
  });

  const err = (code: string, message: string): void => {
    bus.emit({ type: "ERROR", code, message });
  };

  const draw = (): Card => {
    const c = shoe.draw();
    if (shoe.needsShuffle()) {
      // defer reshuffle until next round; mark shoe for shuffle
    }
    return c;
  };

  const dealCardTo = (target: "player" | "dealer", handIndex: number, faceDown: boolean): Card => {
    const c = draw();
    if (target === "player") hands[handIndex]!.cards.push(c);
    else dealer.push(c);
    bus.emit({ type: "CARD_DEALT", to: target, handIndex, card: c, faceDown });
    return c;
  };

  const placeBet = (amount: number, sb?: Partial<SideBets>): void => {
    if (phase !== "betting") return err("ILLEGAL_ACTION", "Not in betting phase");
    if (amount < rules.minBet || amount > rules.maxBet)
      return err("BET_OUT_OF_RANGE", `bet must be ${rules.minBet}-${rules.maxBet}`);
    const sbAmt = (sb?.perfectPairs ?? 0) + (sb?.twentyOneP3 ?? 0) + (sb?.luckyLadies ?? 0);
    if (amount + sbAmt > bankroll) return err("INSUFFICIENT_FUNDS", "Not enough bankroll");
    pendingBet = amount;
    sideBets = {
      perfectPairs: sb?.perfectPairs ?? 0,
      twentyOneP3: sb?.twentyOneP3 ?? 0,
      luckyLadies: sb?.luckyLadies ?? 0,
    };
    adjustBankroll(-(amount + sbAmt));
    bus.emit({ type: "BET_PLACED", amount, sideBets });
    deal();
  };

  const deal = (): void => {
    setPhase("dealing");
    hands = [
      {
        cards: [],
        bet: pendingBet,
        doubled: false,
        surrendered: false,
        settled: false,
        stood: false,
        splitFromAces: false,
      },
    ];
    dealer = [];
    dealerHoleHidden = true;
    splitCount = 0;
    activeHandIndex = 0;

    dealCardTo("player", 0, false);
    dealCardTo("dealer", 0, false);
    dealCardTo("player", 0, false);
    dealCardTo("dealer", 0, true);

    settleSideBets();

    if (rules.dealerPeeksOnAce && dealer[0]!.rank === "A") {
      setPhase("insurance");
      return;
    }
    afterInsurance();
  };

  const settleSideBets = (): void => {
    const p = hands[0]!.cards;
    if (sideBets.perfectPairs > 0) {
      const r = evalPerfectPairs(p);
      if (r.payout > 0) {
        const payout = sideBets.perfectPairs * (r.payout + 1);
        adjustBankroll(payout);
        bus.emit({ type: "SIDEBET_WIN", kind: "perfectPairs", payout, label: r.label });
      }
    }
    if (sideBets.twentyOneP3 > 0) {
      const r = evalTwentyOnePlusThree(p, dealer[0]);
      if (r.payout > 0) {
        const payout = sideBets.twentyOneP3 * (r.payout + 1);
        adjustBankroll(payout);
        bus.emit({ type: "SIDEBET_WIN", kind: "21+3", payout, label: r.label });
      }
    }
    if (sideBets.luckyLadies > 0) {
      const r = evalLuckyLadies(p, dealer);
      if (r.payout > 0) {
        const payout = sideBets.luckyLadies * (r.payout + 1);
        adjustBankroll(payout);
        bus.emit({ type: "SIDEBET_WIN", kind: "luckyLadies", payout, label: r.label });
      }
    }
  };

  const afterInsurance = (): void => {
    const dealerHasBJ = isBlackjack(dealer);
    if (dealerHasBJ && (rules.dealerPeeksOnAce || rules.dealerPeeksOnTen)) {
      const upIsTen = rankValue(dealer[0]!.rank) === 10;
      const upIsAce = dealer[0]!.rank === "A";
      if ((upIsAce && rules.dealerPeeksOnAce) || (upIsTen && rules.dealerPeeksOnTen)) {
        revealHole();
        settleAgainstDealer();
        return;
      }
    }
    if (isBlackjack(hands[0]!.cards)) {
      bus.emit({ type: "NATURAL_BLACKJACK", handIndex: 0 });
      revealHole();
      settleAgainstDealer();
      return;
    }
    setPhase("playerTurn");
  };

  const revealHole = (): void => {
    dealerHoleHidden = false;
    if (dealer.length >= 2) bus.emit({ type: "HOLE_CARD_REVEALED", card: dealer[1]! });
  };

  const hit = (): void => {
    const h = hands[activeHandIndex];
    if (!h) return;
    bus.emit({ type: "PLAYER_ACTION", action: "HIT", handIndex: activeHandIndex });
    dealCardTo("player", activeHandIndex, false);
    const v = evaluate(h.cards);
    if (rules.id === "PONTOON" && h.cards.length >= 5 && !v.isBust) {
      h.stood = true;
      advanceHand();
      return;
    }
    if (v.isBust) {
      bus.emit({ type: "HAND_BUST", handIndex: activeHandIndex });
      advanceHand();
    } else if (v.total === 21) {
      h.stood = true;
      advanceHand();
    }
  };

  const stand = (): void => {
    const h = hands[activeHandIndex];
    if (!h) return;
    bus.emit({ type: "PLAYER_ACTION", action: "STAND", handIndex: activeHandIndex });
    h.stood = true;
    advanceHand();
  };

  const doubleDown = (): void => {
    const h = hands[activeHandIndex];
    if (!h) return;
    if (h.cards.length !== 2) return err("ILLEGAL_ACTION", "Double requires 2 cards");
    if (bankroll < h.bet) return err("INSUFFICIENT_FUNDS", "Cannot cover double");
    adjustBankroll(-h.bet);
    h.bet *= 2;
    h.doubled = true;
    bus.emit({ type: "PLAYER_ACTION", action: "DOUBLE", handIndex: activeHandIndex });
    dealCardTo("player", activeHandIndex, false);
    h.stood = true;
    const v = evaluate(h.cards);
    if (v.isBust) bus.emit({ type: "HAND_BUST", handIndex: activeHandIndex });
    advanceHand();
  };

  const split = (): void => {
    const h = hands[activeHandIndex];
    if (!h) return;
    if (!isPair(h.cards)) return err("ILLEGAL_ACTION", "Not a pair");
    if (splitCount >= rules.maxSplits) return err("ILLEGAL_ACTION", "Max splits reached");
    if (bankroll < h.bet) return err("INSUFFICIENT_FUNDS", "Cannot cover split");
    const isAces = h.cards[0]!.rank === "A";
    adjustBankroll(-h.bet);
    splitCount++;
    const second = h.cards.pop()!;
    const newHand: PlayerHand = {
      cards: [second],
      bet: h.bet,
      doubled: false,
      surrendered: false,
      settled: false,
      stood: false,
      splitFromAces: isAces,
    };
    h.splitFromAces = isAces;
    hands.splice(activeHandIndex + 1, 0, newHand);
    bus.emit({ type: "PLAYER_ACTION", action: "SPLIT", handIndex: activeHandIndex });

    dealCardTo("player", activeHandIndex, false);
    dealCardTo("player", activeHandIndex + 1, false);

    if (isAces && rules.splitAcesOneCardOnly) {
      hands[activeHandIndex]!.stood = true;
      hands[activeHandIndex + 1]!.stood = true;
      advanceHand();
    }
  };

  const surrender = (): void => {
    const h = hands[activeHandIndex];
    if (!h) return;
    if (!rules.allowSurrender || hands.length !== 1 || h.cards.length !== 2)
      return err("ILLEGAL_ACTION", "Surrender not allowed");
    h.surrendered = true;
    h.stood = true;
    bus.emit({ type: "PLAYER_ACTION", action: "SURRENDER", handIndex: activeHandIndex });
    advanceHand();
  };

  const insure = (amount: number): void => {
    if (phase !== "insurance") return err("ILLEGAL_ACTION", "Not in insurance phase");
    const max = Math.floor(hands[0]!.bet / 2);
    if (amount < 0 || amount > max) return err("BET_OUT_OF_RANGE", `0-${max}`);
    if (amount > bankroll) return err("INSUFFICIENT_FUNDS", "Not enough bankroll");
    insuranceBet = amount;
    adjustBankroll(-amount);
    afterInsurance();
  };

  const declineInsurance = (): void => {
    if (phase !== "insurance") return err("ILLEGAL_ACTION", "Not in insurance phase");
    insuranceBet = 0;
    afterInsurance();
  };

  const advanceHand = (): void => {
    while (activeHandIndex < hands.length) {
      const h = hands[activeHandIndex]!;
      const v = evaluate(h.cards);
      if (h.stood || h.surrendered || v.isBust) {
        activeHandIndex++;
        continue;
      }
      return;
    }
    dealerTurn();
  };

  const dealerTurn = (): void => {
    setPhase("dealerTurn");
    revealHole();
    const anyLiveHand = hands.some((h) => !h.surrendered && !evaluate(h.cards).isBust);
    if (anyLiveHand) {
      while (dealerShouldHit(dealer, rules)) {
        const c = draw();
        dealer.push(c);
        const v = evaluate(dealer);
        bus.emit({ type: "DEALER_ACTION", action: "HIT", total: v.total, soft: v.soft });
        bus.emit({ type: "CARD_DEALT", to: "dealer", handIndex: 0, card: c, faceDown: false });
      }
      const v = evaluate(dealer);
      bus.emit({ type: "DEALER_ACTION", action: "STAND", total: v.total, soft: v.soft });
    }
    settleAgainstDealer();
  };

  const bonus21Multiplier = (h: PlayerHand): number => {
    if (!rules.bonus21s) return 0;
    const v = evaluate(h.cards);
    if (v.total !== 21 || h.cards.length < 5) return 0;
    const len = h.cards.length;
    const suited = h.cards.every((c) => c.suit === h.cards[0]!.suit);
    if (len === 5) return suited ? 1.5 : 0.5;
    if (len === 6) return suited ? 2 : 1;
    return suited ? 3 : 2;
  };

  const settleAgainstDealer = (): void => {
    setPhase("settlement");
    const dv = evaluate(dealer);
    const dealerBJ = isBlackjack(dealer);
    const insurancePayout = dealerBJ && insuranceBet > 0 ? insuranceBet * (rules.insurancePays + 1) : 0;
    if (insurancePayout > 0) adjustBankroll(insurancePayout);

    for (let i = 0; i < hands.length; i++) {
      const h = hands[i]!;
      const v = evaluate(h.cards);
      let outcome: Outcome = "loss";
      let payout = 0;
      let label: string | undefined;

      if (h.surrendered) {
        outcome = "surrender";
        payout = Math.floor(h.bet / 2);
      } else if (v.isBust) {
        outcome = "bust";
        payout = 0;
      } else if (isBlackjack(h.cards) && !h.splitFromAces) {
        if (dealerBJ) {
          outcome = "push";
          payout = h.bet;
        } else {
          outcome = "blackjack";
          payout = Math.floor(h.bet * (1 + rules.blackjackPays));
        }
      } else {
        const bonusMult = bonus21Multiplier(h);
        if (dealerBJ) {
          outcome = "loss";
        } else if (dv.isBust) {
          outcome = "win";
          payout = h.bet * 2;
        } else if (v.total > dv.total) {
          outcome = "win";
          payout = h.bet * 2;
        } else if (v.total < dv.total) {
          outcome = "loss";
        } else {
          outcome = "push";
          payout = h.bet;
        }
        if (bonusMult > 0 && outcome === "win") {
          const bonus = Math.floor(h.bet * bonusMult);
          payout += bonus;
          label = `Bonus 21 +${bonus}`;
        }
        if (rules.playerTotalsWinOver17 && outcome === "loss" && v.total >= 17 && v.total <= 21 && !dealerBJ && !v.isBust && v.total > dv.total) {
          outcome = "win";
          payout = h.bet * 2;
        }
      }

      if (payout > 0) adjustBankroll(payout);
      const res: HandResult = { handIndex: i, outcome, payout, total: v.total, cards: h.cards.slice(), label };
      roundResults.push(res);
      bus.emit({ type: "BET_SETTLED", handIndex: i, outcome, payout });
    }

    bus.emit({ type: "ROUND_OVER", results: roundResults.slice() });
    setPhase("roundOver");
    if (shoe.needsShuffle()) {
      shoe.reshuffle();
      bus.emit({ type: "SHOE_SHUFFLED" });
    }
  };

  const newRound = (): void => {
    pendingBet = 0;
    sideBets = { perfectPairs: 0, twentyOneP3: 0, luckyLadies: 0 };
    insuranceBet = 0;
    hands = [];
    dealer = [];
    dealerHoleHidden = true;
    roundResults = [];
    activeHandIndex = 0;
    setPhase("betting");
  };

  const setRuleSet = (id: RuleSetId): void => {
    rules = PRESETS[id];
    shoe = createShoe(rng, {
      decks: rules.decks,
      penetration: rules.penetration,
      removeTens: rules.removeTens,
    });
    bus.emit({ type: "RULESET_CHANGED", ruleSet: id });
    newRound();
  };

  return {
    getState: snapshot,
    on: (l) => bus.on(l),
    getLegalActions: legalActions,
    setRuleSet,
    dispatch(action: Action): void {
      switch (action.type) {
        case "PLACE_BET":
          return placeBet(action.amount, action.sideBets);
        case "HIT":
          return phase === "playerTurn" ? hit() : err("ILLEGAL_ACTION", action.type);
        case "STAND":
          return phase === "playerTurn" ? stand() : err("ILLEGAL_ACTION", action.type);
        case "DOUBLE":
          return phase === "playerTurn" ? doubleDown() : err("ILLEGAL_ACTION", action.type);
        case "SPLIT":
          return phase === "playerTurn" ? split() : err("ILLEGAL_ACTION", action.type);
        case "SURRENDER":
          return phase === "playerTurn" ? surrender() : err("ILLEGAL_ACTION", action.type);
        case "INSURE":
          return insure(action.amount);
        case "DECLINE_INSURANCE":
          return declineInsurance();
        case "NEW_ROUND":
          return phase === "roundOver" ? newRound() : err("ILLEGAL_ACTION", action.type);
        case "SET_RULESET":
          return setRuleSet(action.preset);
        case "DEAL":
          return err("INTERNAL", "DEAL is dispatched automatically after PLACE_BET");
      }
    },
  };
}
