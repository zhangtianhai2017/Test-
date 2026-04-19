import type { Rng } from "./rng.js";

export type Suit = "♠" | "♥" | "♦" | "♣";
export type Rank =
  | "A"
  | "2"
  | "3"
  | "4"
  | "5"
  | "6"
  | "7"
  | "8"
  | "9"
  | "10"
  | "J"
  | "Q"
  | "K";

export interface Card {
  readonly rank: Rank;
  readonly suit: Suit;
}

export const SUITS: readonly Suit[] = ["♠", "♥", "♦", "♣"];
export const RANKS: readonly Rank[] = [
  "A",
  "2",
  "3",
  "4",
  "5",
  "6",
  "7",
  "8",
  "9",
  "10",
  "J",
  "Q",
  "K",
];

export function cardId(c: Card): string {
  return `${c.rank}${c.suit}`;
}

export function isRed(c: Card): boolean {
  return c.suit === "♥" || c.suit === "♦";
}

export interface DeckOptions {
  decks: number;
  removeTens?: boolean;
}

export function buildDeck({ decks, removeTens = false }: DeckOptions): Card[] {
  const out: Card[] = [];
  for (let d = 0; d < decks; d++) {
    for (const s of SUITS) {
      for (const r of RANKS) {
        if (removeTens && r === "10") continue;
        out.push({ rank: r, suit: s });
      }
    }
  }
  return out;
}

export function fisherYates<T>(arr: T[], rng: Rng): T[] {
  for (let i = arr.length - 1; i > 0; i--) {
    const j = Math.floor(rng.next() * (i + 1));
    const tmp = arr[i]!;
    arr[i] = arr[j]!;
    arr[j] = tmp;
  }
  return arr;
}

export interface Shoe {
  draw(): Card;
  remaining(): number;
  needsShuffle(): boolean;
  reshuffle(): void;
}

export interface ShoeOptions {
  decks: number;
  penetration?: number;
  removeTens?: boolean;
}

export function createShoe(rng: Rng, opts: ShoeOptions): Shoe {
  const { decks, penetration = 0.75, removeTens = false } = opts;
  let cards: Card[] = [];
  let cut = 0;
  let drawn = 0;

  const fill = (): void => {
    cards = fisherYates(buildDeck({ decks, removeTens }), rng);
    cut = Math.floor(cards.length * penetration);
    drawn = 0;
  };
  fill();

  return {
    draw(): Card {
      if (drawn >= cards.length) fill();
      return cards[drawn++]!;
    },
    remaining(): number {
      return cards.length - drawn;
    },
    needsShuffle(): boolean {
      return drawn >= cut;
    },
    reshuffle(): void {
      fill();
    },
  };
}
