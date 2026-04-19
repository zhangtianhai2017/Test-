import type { Card, Rank } from "./cards.js";

export function rankValue(r: Rank): number {
  if (r === "A") return 1;
  if (r === "J" || r === "Q" || r === "K") return 10;
  if (r === "10") return 10;
  return parseInt(r, 10);
}

export interface HandValue {
  total: number;
  soft: boolean;
  isBust: boolean;
  is21: boolean;
}

export function evaluate(cards: readonly Card[]): HandValue {
  let total = 0;
  let aces = 0;
  for (const c of cards) {
    total += rankValue(c.rank);
    if (c.rank === "A") aces++;
  }
  let soft = false;
  if (aces > 0 && total + 10 <= 21) {
    total += 10;
    soft = true;
  }
  return {
    total,
    soft,
    isBust: total > 21,
    is21: total === 21,
  };
}

export function isBlackjack(cards: readonly Card[]): boolean {
  if (cards.length !== 2) return false;
  const v = evaluate(cards);
  return v.total === 21;
}

export function isPair(cards: readonly Card[]): boolean {
  if (cards.length !== 2) return false;
  return rankValue(cards[0]!.rank) === rankValue(cards[1]!.rank);
}
