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
  | { type: "SET_RULESET"; preset: RuleSetId }
  | { type: "CONFIGURE_TABLE"; config: TableConfig }
  | { type: "CLAIM_SEAT"; seatIndex: number; sessionId: string; name: string; bankroll?: number }
  | { type: "RELEASE_SEAT"; seatIndex: number; becomeNpc?: boolean; personality?: NpcPersonality }
  | { type: "PLACE_BET_FOR_SEAT"; seatIndex: number; amount: number; sideBets?: Partial<SideBets> }
  | { type: "GESTURE"; seatIndex: number; gesture: Gesture };

export type ActionType = Action["type"];

export interface SideBets {
  perfectPairs: number;
  twentyOneP3: number;
  luckyLadies: number;
}

export interface TableConfig {
  seats: Array<{
    kind: SeatKind;
    name?: string;
    personality?: NpcPersonality;
    bankroll?: number;
    ownerSessionId?: string | null;
  }>;
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
  seats: Seat[];
  activeSeatIndex: number;
  humanSeatIndex: number | null;
  maxSeats: number;
}

export interface CreateGameOptions {
  ruleSetId?: RuleSetId;
  seed?: number;
  bankroll?: number;
  maxSeats?: number;
}

export interface Game {
  getState(): GameSnapshot;
  dispatch(action: Action): void;
  on(listener: Listener): () => void;
  getLegalActions(): ActionType[];
  setRuleSet(id: RuleSetId): void;
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
  const maxSeats = opts.maxSeats ?? 6;
  const startingBankroll = opts.bankroll ?? rules.startingBankroll;

  const seats: Seat[] = [
    {
      index: 0,
      player: {
        id: "p0",
        name: "Player",
        kind: "human",
        bankroll: startingBankroll,
      },
      hands: [],
      activeHandIndex: 0,
      pendingBet: 0,
      sideBets: { perfectPairs: 0, twentyOneP3: 0, luckyLadies: 0 },
      insuranceBet: 0,
      gestures: [],
      tilt: 0,
      ownerSessionId: null,
    },
  ];
  const activeSeatIndex = 0;
  const humanSeatIndex: number | null = 0;

  let phase: Phase = "betting";
  let dealer: Card[] = [];
  let dealerHoleHidden = true;
  let roundResults: HandResult[] = [];
  let splitCount = 0;

  const seat = (): Seat => seats[0]!;

  const setPhase = (p: Phase): void => {
    if (phase !== p) {
      phase = p;
      bus.emit({ type: "PHASE_CHANGED", phase });
    }
  };

  const adjustBankroll = (delta: number): void => {
    seats[0]!.player.bankroll += delta;
    bus.emit({ type: "BANKROLL_CHANGED", bankroll: seats[0]!.player.bankroll, delta });
  };

  const legalActions = (): ActionType[] => {
    if (phase === "betting") return ["PLACE_BET", "SET_RULESET"];
    if (phase === "dealing") return [];
    if (phase === "insurance") return ["INSURE", "DECLINE_INSURANCE"];
    if (phase === "playerTurn") {
      const s = seat();
      const h = s.hands[s.activeHandIndex];
      if (!h) return [];
      const acts: ActionType[] = ["HIT", "STAND"];
      if (h.cards.length === 2 && !h.splitFromAces) {
        acts.push("DOUBLE");
        if (isPair(h.cards) && splitCount < rules.maxSplits) acts.push("SPLIT");
        if (rules.allowSurrender && s.hands.length === 1) acts.push("SURRENDER");
      }
      return acts;
    }
    if (phase === "roundOver") return ["NEW_ROUND", "SET_RULESET"];
    return [];
  };

  const snapshot = (): GameSnapshot => {
    const s = seat();
    return {
      phase,
      ruleSet: rules,
      bankroll: s.player.bankroll,
      dealer: dealer.slice(),
      dealerHoleHidden,
      hands: s.hands.map((h) => ({ ...h, cards: h.cards.slice() })),
      activeHandIndex: s.activeHandIndex,
      pendingBet: s.pendingBet,
      sideBets: { ...s.sideBets },
      insuranceBet: s.insuranceBet,
      roundResults: roundResults.slice(),
      legalActions: legalActions(),
      handValues: s.hands.map((h) => evaluate(h.cards)),
      dealerValue: evaluate(
        dealerHoleHidden && dealer.length > 1 ? [dealer[0]!] : dealer,
      ),
      seats: seats.map((st) => ({
        ...st,
        player: { ...st.player },
        hands: st.hands.map((h) => ({ ...h, cards: h.cards.slice() })),
        sideBets: { ...st.sideBets },
        gestures: st.gestures.slice(),
      })),
      activeSeatIndex,
      humanSeatIndex,
      maxSeats,
    };
  };

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
    if (target === "player") seat().hands[handIndex]!.cards.push(c);
    else dealer.push(c);
    bus.emit({ type: "CARD_DEALT", to: target, handIndex, card: c, faceDown });
    return c;
  };

  const placeBet = (amount: number, sb?: Partial<SideBets>): void => {
    if (phase !== "betting") return err("ILLEGAL_ACTION", "Not in betting phase");
    if (amount < rules.minBet || amount > rules.maxBet)
      return err("BET_OUT_OF_RANGE", `bet must be ${rules.minBet}-${rules.maxBet}`);
    const sbAmt = (sb?.perfectPairs ?? 0) + (sb?.twentyOneP3 ?? 0) + (sb?.luckyLadies ?? 0);
    const s = seat();
    if (amount + sbAmt > s.player.bankroll) return err("INSUFFICIENT_FUNDS", "Not enough bankroll");
    s.pendingBet = amount;
    s.sideBets = {
      perfectPairs: sb?.perfectPairs ?? 0,
      twentyOneP3: sb?.twentyOneP3 ?? 0,
      luckyLadies: sb?.luckyLadies ?? 0,
    };
    adjustBankroll(-(amount + sbAmt));
    bus.emit({ type: "BET_PLACED", amount, sideBets: s.sideBets });
    deal();
  };

  const deal = (): void => {
    setPhase("dealing");
    const s = seat();
    s.hands = [
      {
        cards: [],
        bet: s.pendingBet,
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
    s.activeHandIndex = 0;

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
    const s = seat();
    const p = s.hands[0]!.cards;
    if (s.sideBets.perfectPairs > 0) {
      const r = evalPerfectPairs(p);
      if (r.payout > 0) {
        const payout = s.sideBets.perfectPairs * (r.payout + 1);
        adjustBankroll(payout);
        bus.emit({ type: "SIDEBET_WIN", kind: "perfectPairs", payout, label: r.label });
      }
    }
    if (s.sideBets.twentyOneP3 > 0) {
      const r = evalTwentyOnePlusThree(p, dealer[0]);
      if (r.payout > 0) {
        const payout = s.sideBets.twentyOneP3 * (r.payout + 1);
        adjustBankroll(payout);
        bus.emit({ type: "SIDEBET_WIN", kind: "21+3", payout, label: r.label });
      }
    }
    if (s.sideBets.luckyLadies > 0) {
      const r = evalLuckyLadies(p, dealer);
      if (r.payout > 0) {
        const payout = s.sideBets.luckyLadies * (r.payout + 1);
        adjustBankroll(payout);
        bus.emit({ type: "SIDEBET_WIN", kind: "luckyLadies", payout, label: r.label });
      }
    }
  };

  const afterInsurance = (): void => {
    const s = seat();
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
    if (isBlackjack(s.hands[0]!.cards)) {
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
    const s = seat();
    const h = s.hands[s.activeHandIndex];
    if (!h) return;
    bus.emit({ type: "PLAYER_ACTION", action: "HIT", handIndex: s.activeHandIndex });
    dealCardTo("player", s.activeHandIndex, false);
    const v = evaluate(h.cards);
    if (rules.id === "PONTOON" && h.cards.length >= 5 && !v.isBust) {
      h.stood = true;
      advanceHand();
      return;
    }
    if (v.isBust) {
      bus.emit({ type: "HAND_BUST", handIndex: s.activeHandIndex });
      advanceHand();
    } else if (v.total === 21) {
      h.stood = true;
      advanceHand();
    }
  };

  const stand = (): void => {
    const s = seat();
    const h = s.hands[s.activeHandIndex];
    if (!h) return;
    bus.emit({ type: "PLAYER_ACTION", action: "STAND", handIndex: s.activeHandIndex });
    h.stood = true;
    advanceHand();
  };

  const doubleDown = (): void => {
    const s = seat();
    const h = s.hands[s.activeHandIndex];
    if (!h) return;
    if (h.cards.length !== 2) return err("ILLEGAL_ACTION", "Double requires 2 cards");
    if (s.player.bankroll < h.bet) return err("INSUFFICIENT_FUNDS", "Cannot cover double");
    adjustBankroll(-h.bet);
    h.bet *= 2;
    h.doubled = true;
    bus.emit({ type: "PLAYER_ACTION", action: "DOUBLE", handIndex: s.activeHandIndex });
    dealCardTo("player", s.activeHandIndex, false);
    h.stood = true;
    const v = evaluate(h.cards);
    if (v.isBust) bus.emit({ type: "HAND_BUST", handIndex: s.activeHandIndex });
    advanceHand();
  };

  const split = (): void => {
    const s = seat();
    const h = s.hands[s.activeHandIndex];
    if (!h) return;
    if (!isPair(h.cards)) return err("ILLEGAL_ACTION", "Not a pair");
    if (splitCount >= rules.maxSplits) return err("ILLEGAL_ACTION", "Max splits reached");
    if (s.player.bankroll < h.bet) return err("INSUFFICIENT_FUNDS", "Cannot cover split");
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
    s.hands.splice(s.activeHandIndex + 1, 0, newHand);
    bus.emit({ type: "PLAYER_ACTION", action: "SPLIT", handIndex: s.activeHandIndex });

    dealCardTo("player", s.activeHandIndex, false);
    dealCardTo("player", s.activeHandIndex + 1, false);

    if (isAces && rules.splitAcesOneCardOnly) {
      s.hands[s.activeHandIndex]!.stood = true;
      s.hands[s.activeHandIndex + 1]!.stood = true;
      advanceHand();
    }
  };

  const surrender = (): void => {
    const s = seat();
    const h = s.hands[s.activeHandIndex];
    if (!h) return;
    if (!rules.allowSurrender || s.hands.length !== 1 || h.cards.length !== 2)
      return err("ILLEGAL_ACTION", "Surrender not allowed");
    h.surrendered = true;
    h.stood = true;
    bus.emit({ type: "PLAYER_ACTION", action: "SURRENDER", handIndex: s.activeHandIndex });
    advanceHand();
  };

  const insure = (amount: number): void => {
    if (phase !== "insurance") return err("ILLEGAL_ACTION", "Not in insurance phase");
    const s = seat();
    const max = Math.floor(s.hands[0]!.bet / 2);
    if (amount < 0 || amount > max) return err("BET_OUT_OF_RANGE", `0-${max}`);
    if (amount > s.player.bankroll) return err("INSUFFICIENT_FUNDS", "Not enough bankroll");
    s.insuranceBet = amount;
    adjustBankroll(-amount);
    afterInsurance();
  };

  const declineInsurance = (): void => {
    if (phase !== "insurance") return err("ILLEGAL_ACTION", "Not in insurance phase");
    seat().insuranceBet = 0;
    afterInsurance();
  };

  const advanceHand = (): void => {
    const s = seat();
    while (s.activeHandIndex < s.hands.length) {
      const h = s.hands[s.activeHandIndex]!;
      const v = evaluate(h.cards);
      if (h.stood || h.surrendered || v.isBust) {
        s.activeHandIndex++;
        continue;
      }
      return;
    }
    dealerTurn();
  };

  const dealerTurn = (): void => {
    setPhase("dealerTurn");
    revealHole();
    const s = seat();
    const anyLiveHand = s.hands.some((h) => !h.surrendered && !evaluate(h.cards).isBust);
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
    const s = seat();
    const dv = evaluate(dealer);
    const dealerBJ = isBlackjack(dealer);
    const insurancePayout = dealerBJ && s.insuranceBet > 0 ? s.insuranceBet * (rules.insurancePays + 1) : 0;
    if (insurancePayout > 0) adjustBankroll(insurancePayout);

    for (let i = 0; i < s.hands.length; i++) {
      const h = s.hands[i]!;
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
    const s = seat();
    s.pendingBet = 0;
    s.sideBets = { perfectPairs: 0, twentyOneP3: 0, luckyLadies: 0 };
    s.insuranceBet = 0;
    s.hands = [];
    s.activeHandIndex = 0;
    dealer = [];
    dealerHoleHidden = true;
    roundResults = [];
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
        case "CONFIGURE_TABLE":
        case "CLAIM_SEAT":
        case "RELEASE_SEAT":
        case "PLACE_BET_FOR_SEAT":
        case "GESTURE":
          return err("UNIMPLEMENTED", `${action.type} pending M1c.2-4`);
        case "SET_RULESET":
          return setRuleSet(action.preset);
        case "DEAL":
          return err("INTERNAL", "DEAL is dispatched automatically after PLACE_BET");
      }
    },
  };
}
