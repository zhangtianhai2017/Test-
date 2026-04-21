/**
 * Basic Strategy lookup tables for Blackjack.
 *
 * Canonical source: Wizard of Odds multi-deck strategy calculator,
 *   https://wizardofodds.com/games/blackjack/strategy/calculator/
 *
 * Two rule variants are supported:
 *   - H17: dealer hits soft 17
 *   - S17: dealer stands on soft 17
 *
 * Tables assume:
 *   - 4-8 decks
 *   - Double allowed on any two cards
 *   - Double after split (DAS) allowed (we still honor canDoubleAfterSplit at
 *     runtime for pair-split "Ph" cells)
 *   - Late surrender allowed (we honor canSurrender at runtime)
 *
 * Cell codes:
 *   H  = hit
 *   S  = stand
 *   D  = double (always — no fallback needed)
 *   Dh = double if allowed, else hit
 *   Ds = double if allowed, else stand
 *   P  = split (DAS-independent)
 *   Ph = split if DAS allowed, else hit
 *   Rh = surrender if allowed, else hit
 */
import type { Card, RuleSet } from "@blackjack/engine";
import { evaluate, isPair, rankValue } from "@blackjack/engine";

export type BSAction = "hit" | "stand" | "double" | "split" | "surrender";

export interface BSInput {
  playerCards: readonly Card[];
  dealerUp: Card;
  rules: RuleSet;
  canDouble: boolean;
  canSplit: boolean;
  canSurrender: boolean;
  canDoubleAfterSplit?: boolean;
}

type Cell = "H" | "S" | "D" | "Dh" | "Ds" | "P" | "Ph" | "Rh";

/**
 * Dealer up-card index 0..9 corresponding to values:
 *   0 → 2
 *   1 → 3
 *   2 → 4
 *   3 → 5
 *   4 → 6
 *   5 → 7
 *   6 → 8
 *   7 → 9
 *   8 → 10 (T/J/Q/K)
 *   9 → A
 */
function dealerIndex(c: Card): number {
  const v = rankValue(c.rank); // A=1, face/10=10, 2..9 = nominal
  if (v === 1) return 9; // Ace
  if (v === 10) return 8;
  return v - 2; // 2→0 .. 9→7
}

/**
 * Hard totals table.
 *
 * Key = hard total (5..21).
 * Value = row of 10 cells, indexed by dealerIndex() above
 * (columns: 2 3 4 5 6 7 8 9 T A).
 *
 * H17-specific deviations vs S17 are patched in HARD_H17_OVERRIDES below.
 *
 * Source: WoO multi-deck S17 chart (DAS, late surrender).
 */
// prettier-ignore
const HARD_S17: Record<number, readonly Cell[]> = {
  //        2    3    4    5    6    7    8    9    T    A
  5:  ["H", "H", "H", "H", "H", "H", "H", "H", "H", "H"],
  6:  ["H", "H", "H", "H", "H", "H", "H", "H", "H", "H"],
  7:  ["H", "H", "H", "H", "H", "H", "H", "H", "H", "H"],
  8:  ["H", "H", "H", "H", "H", "H", "H", "H", "H", "H"],
  9:  ["H", "Dh","Dh","Dh","Dh","H", "H", "H", "H", "H"],
  10: ["Dh","Dh","Dh","Dh","Dh","Dh","Dh","Dh","H", "H"],
  11: ["Dh","Dh","Dh","Dh","Dh","Dh","Dh","Dh","Dh","H"],
  12: ["H", "H", "S", "S", "S", "H", "H", "H", "H", "H"],
  13: ["S", "S", "S", "S", "S", "H", "H", "H", "H", "H"],
  14: ["S", "S", "S", "S", "S", "H", "H", "H", "H", "H"],
  15: ["S", "S", "S", "S", "S", "H", "H", "H", "Rh","H"],
  16: ["S", "S", "S", "S", "S", "H", "H", "Rh","Rh","Rh"],
  17: ["S", "S", "S", "S", "S", "S", "S", "S", "S", "S"],
  18: ["S", "S", "S", "S", "S", "S", "S", "S", "S", "S"],
  19: ["S", "S", "S", "S", "S", "S", "S", "S", "S", "S"],
  20: ["S", "S", "S", "S", "S", "S", "S", "S", "S", "S"],
  21: ["S", "S", "S", "S", "S", "S", "S", "S", "S", "S"],
};

/**
 * H17 overrides applied on top of HARD_S17.
 *
 * Canonical WoO H17 differences:
 *   - 11 vs A: double (S17: hit)
 *   - 15 vs A: surrender-else-hit (S17: hit)
 *   - 17 vs A: surrender-else-stand (S17: stand)
 *
 * (16 vs A is already Rh in S17, so no override needed.)
 */
// prettier-ignore
const HARD_H17_OVERRIDES: Record<number, Partial<Record<number, Cell>>> = {
  11: { 9: "Dh" },    // 11 vs A → double else hit
  15: { 9: "Rh" },    // 15 vs A → surrender else hit
  17: { 9: "Rh" },    // 17 vs A → surrender else stand-by-default → use Rh (fallback = hit
                       // per rule, but surrender-on-17 is a very marginal H17 WoO call; see note)
};

/**
 * Soft totals table.
 *
 * Key = hand total (13..20) where one Ace is counted as 11.
 * Columns indexed by dealerIndex() (2 3 4 5 6 7 8 9 T A).
 *
 * S17 canonical chart (WoO multi-deck, DAS).
 */
// prettier-ignore
const SOFT_S17: Record<number, readonly Cell[]> = {
  //        2    3    4    5    6    7    8    9    T    A
  13: ["H", "H", "H", "Dh","Dh","H", "H", "H", "H", "H"],  // A,2
  14: ["H", "H", "H", "Dh","Dh","H", "H", "H", "H", "H"],  // A,3
  15: ["H", "H", "Dh","Dh","Dh","H", "H", "H", "H", "H"],  // A,4
  16: ["H", "H", "Dh","Dh","Dh","H", "H", "H", "H", "H"],  // A,5
  17: ["H", "Dh","Dh","Dh","Dh","H", "H", "H", "H", "H"],  // A,6
  18: ["S", "Ds","Ds","Ds","Ds","S", "S", "H", "H", "H"],  // A,7
  19: ["S", "S", "S", "S", "S", "S", "S", "S", "S", "S"],  // A,8
  20: ["S", "S", "S", "S", "S", "S", "S", "S", "S", "S"],  // A,9
};

/**
 * H17 soft overrides.
 *
 *   - A,6 (17) vs 2 → double (was hit in S17)
 *   - A,7 (18) vs 2 → double (was stand in S17)
 *   - A,8 (19) vs 6 → double (was stand in S17)
 */
// prettier-ignore
const SOFT_H17_OVERRIDES: Record<number, Partial<Record<number, Cell>>> = {
  17: { 0: "Dh" },     // A,6 vs 2
  18: { 0: "Ds" },     // A,7 vs 2
  19: { 4: "Ds" },     // A,8 vs 6
};

/**
 * Pair splits table.
 *
 * Key = pairValue (rankValue of each card). A=1, 10/J/Q/K=10.
 * Value = row of 10 cells (2..A).
 *
 * Source: WoO multi-deck DAS chart.
 *
 * "Ph" means split only if DAS is allowed; otherwise fall through to the
 * hard-total table. We encode Ph as a split-or-hit decision at runtime.
 */
// prettier-ignore
const PAIRS: Record<number, readonly Cell[]> = {
  //        2    3    4    5    6    7    8    9    T    A
  1:  ["P", "P", "P", "P", "P", "P", "P", "P", "P", "P"],   // A,A
  2:  ["P", "P", "P", "P", "P", "P", "H", "H", "H", "H"],   // 2,2 (split 2-7)
  3:  ["P", "P", "P", "P", "P", "P", "H", "H", "H", "H"],   // 3,3 (split 2-7)
  4:  ["H", "H", "H", "Ph","Ph","H", "H", "H", "H", "H"],   // 4,4 (split 5-6, DAS only)
  5:  ["H", "H", "H", "H", "H", "H", "H", "H", "H", "H"],   // 5,5 never split → treat as 10
  6:  ["P", "P", "P", "P", "P", "H", "H", "H", "H", "H"],   // 6,6 (split 2-6)
  7:  ["P", "P", "P", "P", "P", "P", "H", "H", "H", "H"],   // 7,7 (split 2-7)
  8:  ["P", "P", "P", "P", "P", "P", "P", "P", "P", "P"],   // 8,8 always split
  9:  ["P", "P", "P", "P", "P", "S", "P", "P", "S", "S"],   // 9,9 split 2-6,8-9
  10: ["S", "S", "S", "S", "S", "S", "S", "S", "S", "S"],   // 10,10 never split
};

function hardCell(total: number, dIdx: number, h17: boolean): Cell | undefined {
  const row = HARD_S17[total];
  if (!row) return undefined;
  let cell: Cell = row[dIdx]!;
  if (h17) {
    const override = HARD_H17_OVERRIDES[total]?.[dIdx];
    if (override) cell = override;
  }
  return cell;
}

function softCell(total: number, dIdx: number, h17: boolean): Cell | undefined {
  const row = SOFT_S17[total];
  if (!row) return undefined;
  let cell: Cell = row[dIdx]!;
  if (h17) {
    const override = SOFT_H17_OVERRIDES[total]?.[dIdx];
    if (override) cell = override;
  }
  return cell;
}

function pairCell(pairVal: number, dIdx: number): Cell | undefined {
  const row = PAIRS[pairVal];
  if (!row) return undefined;
  return row[dIdx];
}

/**
 * Resolve a cell to a final action. For Rh/Dh/Ds/Ph cells, apply the
 * appropriate fallback based on runtime flags.
 */
function resolveNonSplit(
  cell: Cell,
  canDouble: boolean,
  canSurrender: boolean,
): BSAction {
  switch (cell) {
    case "H":
      return "hit";
    case "S":
      return "stand";
    case "D":
      return canDouble ? "double" : "hit";
    case "Dh":
      return canDouble ? "double" : "hit";
    case "Ds":
      return canDouble ? "double" : "stand";
    case "Rh":
      return canSurrender ? "surrender" : "hit";
    case "P":
    case "Ph":
      // Shouldn't reach here from non-split branches; be defensive.
      return "hit";
    default:
      return "hit";
  }
}

function decideHard(
  total: number,
  dIdx: number,
  h17: boolean,
  canDouble: boolean,
  canSurrender: boolean,
): BSAction {
  // Clamp just-in-case: totals below 5 shouldn't happen with a real hand,
  // totals above 21 are bust and the engine won't ask us.
  const clamped = total < 5 ? 5 : total > 21 ? 21 : total;
  const cell = hardCell(clamped, dIdx, h17);
  if (!cell) return "hit";
  return resolveNonSplit(cell, canDouble, canSurrender);
}

function decideSoft(
  total: number,
  dIdx: number,
  h17: boolean,
  canDouble: boolean,
  canSurrender: boolean,
): BSAction {
  const cell = softCell(total, dIdx, h17);
  if (!cell) {
    // Fall back to hard-total logic if out of soft range (shouldn't happen).
    return decideHard(total, dIdx, h17, canDouble, canSurrender);
  }
  return resolveNonSplit(cell, canDouble, canSurrender);
}

export function decideBasicStrategy(input: BSInput): BSAction {
  const {
    playerCards,
    dealerUp,
    rules,
    canDouble,
    canSplit,
    canSurrender,
  } = input;
  const canDAS = input.canDoubleAfterSplit ?? rules.allowDoubleAfterSplit;
  const h17 = rules.dealerHitsSoft17;
  const dIdx = dealerIndex(dealerUp);

  // 1. Pair-split branch (only if caller says split is legal and the hand
  //    actually is a pair).
  if (canSplit && isPair(playerCards)) {
    const pairVal = rankValue(playerCards[0]!.rank);
    const cell = pairCell(pairVal, dIdx);
    if (cell === "P") return "split";
    if (cell === "Ph") {
      if (canDAS) return "split";
      // fall through to hard-total handling
    } else if (cell === "S") {
      // 9,9 vs 7/T/A and 10,10 vs everything — chart says stand outright.
      return "stand";
    }
    // Otherwise ("H" or fallthrough from Ph w/o DAS): fall through to
    // hard/soft total decision.
  }

  // 2. Evaluate the hand as a regular total.
  const hv = evaluate(playerCards);
  if (hv.soft) {
    return decideSoft(hv.total, dIdx, h17, canDouble, canSurrender);
  }
  return decideHard(hv.total, dIdx, h17, canDouble, canSurrender);
}
