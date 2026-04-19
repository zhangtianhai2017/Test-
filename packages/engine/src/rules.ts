export type RuleSetId = "VEGAS" | "SPANISH21" | "PONTOON" | "SUPER_FUN_21";

export interface RuleSet {
  id: RuleSetId;
  name: string;
  decks: number;
  removeTens: boolean;
  penetration: number;
  dealerHitsSoft17: boolean;
  blackjackPays: number;
  insurancePays: number;
  allowSurrender: boolean;
  allowDoubleAfterSplit: boolean;
  maxSplits: number;
  resplitAces: boolean;
  splitAcesOneCardOnly: boolean;
  doubleAllowed: "ANY_TWO" | "9_10_11" | "10_11";
  dealerPeeksOnTen: boolean;
  dealerPeeksOnAce: boolean;
  bonus21s: boolean;
  playerTotalsWinOver17: boolean;
  minBet: number;
  maxBet: number;
  startingBankroll: number;
}

export const VEGAS: RuleSet = {
  id: "VEGAS",
  name: "Classic Vegas",
  decks: 6,
  removeTens: false,
  penetration: 0.75,
  dealerHitsSoft17: true,
  blackjackPays: 1.5,
  insurancePays: 2,
  allowSurrender: true,
  allowDoubleAfterSplit: true,
  maxSplits: 3,
  resplitAces: false,
  splitAcesOneCardOnly: true,
  doubleAllowed: "ANY_TWO",
  dealerPeeksOnTen: true,
  dealerPeeksOnAce: true,
  bonus21s: false,
  playerTotalsWinOver17: false,
  minBet: 5,
  maxBet: 500,
  startingBankroll: 1000,
};

export const SPANISH21: RuleSet = {
  ...VEGAS,
  id: "SPANISH21",
  name: "Spanish 21",
  decks: 6,
  removeTens: true,
  blackjackPays: 1.5,
  allowSurrender: true,
  bonus21s: true,
  playerTotalsWinOver17: true,
};

export const PONTOON: RuleSet = {
  ...VEGAS,
  id: "PONTOON",
  name: "Pontoon",
  decks: 8,
  blackjackPays: 2,
  allowSurrender: false,
  bonus21s: true,
  dealerPeeksOnAce: false,
  dealerPeeksOnTen: false,
  playerTotalsWinOver17: true,
};

export const SUPER_FUN_21: RuleSet = {
  ...VEGAS,
  id: "SUPER_FUN_21",
  name: "Super Fun 21",
  decks: 1,
  blackjackPays: 1,
  bonus21s: true,
  allowSurrender: true,
  playerTotalsWinOver17: true,
};

export const PRESETS: Record<RuleSetId, RuleSet> = {
  VEGAS,
  SPANISH21,
  PONTOON,
  SUPER_FUN_21,
};
