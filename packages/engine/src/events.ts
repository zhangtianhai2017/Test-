import type { Card } from "./cards.js";
import type { Phase, HandResult, Gesture } from "./game.js";
import type { RuleSetId } from "./rules.js";

export type EngineEvent =
  | { type: "PHASE_CHANGED"; phase: Phase }
  | { type: "RULESET_CHANGED"; ruleSet: RuleSetId }
  | { type: "BET_PLACED"; amount: number; sideBets: { perfectPairs: number; twentyOneP3: number; luckyLadies: number } }
  | { type: "CARD_DEALT"; to: "player" | "dealer"; handIndex: number; card: Card; faceDown: boolean }
  | { type: "HOLE_CARD_REVEALED"; card: Card }
  | { type: "PLAYER_ACTION"; action: string; handIndex: number }
  | { type: "HAND_BUST"; handIndex: number }
  | { type: "NATURAL_BLACKJACK"; handIndex: number }
  | { type: "DEALER_ACTION"; action: "HIT" | "STAND"; total: number; soft: boolean }
  | { type: "ROUND_OVER"; results: HandResult[] }
  | { type: "BET_SETTLED"; handIndex: number; outcome: HandResult["outcome"]; payout: number }
  | { type: "BANKROLL_CHANGED"; bankroll: number; delta: number }
  | { type: "SIDEBET_WIN"; kind: "perfectPairs" | "21+3" | "luckyLadies"; payout: number; label: string }
  | { type: "SHOE_SHUFFLED" }
  | { type: "ERROR"; code: string; message: string }
  | { type: "SEAT_CLAIMED"; seatIndex: number; sessionId: string; playerName: string }
  | { type: "SEAT_RELEASED"; seatIndex: number }
  | { type: "GESTURE_MADE"; seatIndex: number; gesture: Gesture };

export type Listener = (ev: EngineEvent) => void;

export class EventBus {
  private readonly listeners = new Set<Listener>();
  on(l: Listener): () => void {
    this.listeners.add(l);
    return () => this.listeners.delete(l);
  }
  emit(ev: EngineEvent): void {
    for (const l of this.listeners) l(ev);
  }
}
