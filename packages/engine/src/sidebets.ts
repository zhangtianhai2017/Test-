import type { Card } from "./cards.js";
import { rankValue } from "./hand.js";
import { isRed } from "./cards.js";

export interface SideBetResult {
  payout: number;
  label: string;
}

export function evalPerfectPairs(playerTwo: readonly Card[]): SideBetResult {
  if (playerTwo.length < 2) return { payout: 0, label: "—" };
  const [a, b] = [playerTwo[0]!, playerTwo[1]!];
  if (a.rank !== b.rank) return { payout: 0, label: "—" };
  if (a.suit === b.suit) return { payout: 30, label: "Perfect Pair 30:1" };
  if (isRed(a) === isRed(b)) return { payout: 10, label: "Colored Pair 10:1" };
  return { payout: 5, label: "Mixed Pair 5:1" };
}

function suitedSet(cs: readonly Card[]): boolean {
  return cs.every((c) => c.suit === cs[0]!.suit);
}

function consecutive(cs: readonly Card[]): boolean {
  const vals = cs
    .map((c) => (c.rank === "A" ? 1 : rankValue(c.rank)))
    .slice()
    .sort((x, y) => x - y);
  for (let i = 1; i < vals.length; i++) {
    if (vals[i]! - vals[i - 1]! !== 1) {
      const alt = cs.map((c) => (c.rank === "A" ? 14 : rankValue(c.rank))).sort((x, y) => x - y);
      for (let j = 1; j < alt.length; j++) {
        if (alt[j]! - alt[j - 1]! !== 1) return false;
      }
      return true;
    }
  }
  return true;
}

export function evalTwentyOnePlusThree(
  playerTwo: readonly Card[],
  dealerUp: Card | undefined,
): SideBetResult {
  if (playerTwo.length < 2 || !dealerUp) return { payout: 0, label: "—" };
  const three = [playerTwo[0]!, playerTwo[1]!, dealerUp];
  const sameRank = three.every((c) => c.rank === three[0]!.rank);
  const suited = suitedSet(three);
  const consec = consecutive(three);

  if (sameRank && suited) return { payout: 100, label: "Suited Trips 100:1" };
  if (suited && consec) return { payout: 40, label: "Straight Flush 40:1" };
  if (sameRank) return { payout: 30, label: "Three of a Kind 30:1" };
  if (consec) return { payout: 10, label: "Straight 10:1" };
  if (suited) return { payout: 5, label: "Flush 5:1" };
  return { payout: 0, label: "—" };
}

export function evalLuckyLadies(
  playerTwo: readonly Card[],
  dealerFull: readonly Card[],
): SideBetResult {
  if (playerTwo.length < 2) return { payout: 0, label: "—" };
  const [a, b] = [playerTwo[0]!, playerTwo[1]!];
  const total = (a.rank === "A" ? 1 : rankValue(a.rank)) + (b.rank === "A" ? 1 : rankValue(b.rank));
  const isTwenty =
    (a.rank === "A" && rankValue(b.rank) === 10) ||
    (b.rank === "A" && rankValue(a.rank) === 10) ||
    (rankValue(a.rank) === 10 && rankValue(b.rank) === 10) ||
    total === 20;

  const isQhearts = (c: Card): boolean => c.rank === "Q" && c.suit === "♥";
  if (isQhearts(a) && isQhearts(b)) {
    const dealerBlackjack =
      dealerFull.length === 2 &&
      ((dealerFull[0]!.rank === "A" && rankValue(dealerFull[1]!.rank) === 10) ||
        (dealerFull[1]!.rank === "A" && rankValue(dealerFull[0]!.rank) === 10));
    if (dealerBlackjack) return { payout: 1000, label: "QQ♥ + Dealer BJ 1000:1" };
    return { payout: 200, label: "Pair of Queen of Hearts 200:1" };
  }

  if (!isTwenty) return { payout: 0, label: "—" };
  if (a.rank === b.rank && a.suit === b.suit) return { payout: 125, label: "Matched 20 125:1" };
  if (a.suit === b.suit) return { payout: 19, label: "Suited 20 19:1" };
  if (isRed(a) === isRed(b)) return { payout: 9, label: "Colored 20 9:1" };
  return { payout: 4, label: "Any 20 4:1" };
}
