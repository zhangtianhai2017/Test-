import type { Card, Rank } from "@blackjack/engine";

/**
 * Hi-Lo card counting system.
 *
 * Running count is updated as cards are observed:
 *   2, 3, 4, 5, 6 → +1
 *   7, 8, 9       →  0
 *   10, J, Q, K, A → -1
 *
 * True count normalizes running count by decks remaining in the shoe.
 */
export interface CounterState {
  /** Sum of Hi-Lo values seen since last reset. */
  runningCount: number;
  /** Total cards counted since last reset. */
  cardsSeen: number;
  /** Total decks in the shoe. */
  decks: number;
}

export function newCounter(decks: number): CounterState {
  return { runningCount: 0, cardsSeen: 0, decks };
}

export function hiLoValue(rank: Rank): -1 | 0 | 1 {
  switch (rank) {
    case "2":
    case "3":
    case "4":
    case "5":
    case "6":
      return 1;
    case "7":
    case "8":
    case "9":
      return 0;
    case "10":
    case "J":
    case "Q":
    case "K":
    case "A":
      return -1;
  }
}

/** Pure: return a new state with the card observed. */
export function observe(state: CounterState, card: Card): CounterState {
  return {
    runningCount: state.runningCount + hiLoValue(card.rank),
    cardsSeen: state.cardsSeen + 1,
    decks: state.decks,
  };
}

export function runningCount(state: CounterState): number {
  return state.runningCount;
}

/**
 * Exact fractional decks remaining. Clamped to 0 on the low end so the value
 * never goes negative if cardsSeen somehow exceeds the shoe size.
 */
export function decksRemaining(state: CounterState): number {
  const cardsLeft = state.decks * 52 - state.cardsSeen;
  if (cardsLeft <= 0) return 0;
  return cardsLeft / 52;
}

/**
 * True count = runningCount / decksRemaining. When fewer than half a deck
 * remains, return runningCount as-is to avoid div-by-zero and the wildly
 * unstable values you get near the cut card.
 */
export function trueCount(state: CounterState): number {
  const dr = decksRemaining(state);
  if (dr < 0.5) return state.runningCount;
  return state.runningCount / dr;
}

/** Returns a fresh counter with the same deck count. Use on reshuffle. */
export function reset(state: CounterState): CounterState {
  return { runningCount: 0, cardsSeen: 0, decks: state.decks };
}
