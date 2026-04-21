/**
 * npcAgent — top-level NPC decision functions.
 *
 * Composes:
 *   - basicStrategy.ts (baseline chart lookup)
 *   - hiLoCounter.ts  (trueCount for "counter" personality)
 *   - betPolicies.ts  (flat / kelly / reverse-martingale / unit-spread)
 *   - personalities.ts (per-persona config + static deviations)
 *
 * Two pure entry points are exported:
 *   - npcDecidePlay: returns a BSAction for the active hand
 *   - npcDecideBet:  returns an integer chip amount to bet
 *
 * Both are deterministic given the same (input, personality, seed).
 */
import type { Card, Seat, RuleSet, NpcPersonality } from "@blackjack/engine";
import { evaluate, isPair, rankValue } from "@blackjack/engine";
import { decideBasicStrategy } from "./basicStrategy.js";
import type { BSAction } from "./basicStrategy.js";
import { PERSONALITIES } from "./personalities.js";
import type { DeviationRule } from "./personalities.js";
import { decideBet } from "./betPolicies.js";
import type { BetContext, BetResult } from "./betPolicies.js";
import { trueCount } from "./hiLoCounter.js";
import type { CounterState } from "./hiLoCounter.js";

/** Play-decision input. Inherits from engine's Seat + shoe / rules context. */
export interface NpcPlayInput {
  /** The NPC's seat. */
  seat: Seat;
  dealerUp: Card;
  rules: RuleSet;
  /** Optional — used only if personality.usesCounter. */
  counter?: CounterState;
  /** Engine-computed legality. */
  canDouble: boolean;
  canSplit: boolean;
  canSurrender: boolean;
}

export interface NpcBetInput {
  /** The NPC's seat (player.bankroll, tilt, etc.). */
  seat: Seat;
  rules: RuleSet;
  counter?: CounterState;
  lastResult?: BetResult;
  currentBet?: number;
  streak?: number;
}

/**
 * mulberry32-style deterministic hash → [0, 1). Parity with tells.ts.
 * The `tag` discriminates between independent rolls the agent needs to do
 * (e.g. "play-fire", "play-pick") so they aren't correlated.
 */
function seededUnit(
  seed: number,
  seatIndex: number,
  cardsSeenInHand: number,
  tag: string,
): number {
  const s = `${seed}|${seatIndex}|${cardsSeenInHand}|${tag}`;
  let h = 2166136261 >>> 0;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  let t = (h + 0x6d2b79f5) >>> 0;
  t = Math.imul(t ^ (t >>> 15), t | 1);
  t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
  return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
}

/** Enumerate the set of legal actions given the passed-in boolean flags. */
function legalActions(
  canDouble: boolean,
  canSplit: boolean,
  canSurrender: boolean,
): BSAction[] {
  const out: BSAction[] = ["hit", "stand"];
  if (canDouble) out.push("double");
  if (canSplit) out.push("split");
  if (canSurrender) out.push("surrender");
  return out;
}

/** An override is legal only if the engine flags currently allow that action. */
function overrideIsLegal(
  override: BSAction,
  canDouble: boolean,
  canSplit: boolean,
  canSurrender: boolean,
): boolean {
  if (override === "double" && !canDouble) return false;
  if (override === "split" && !canSplit) return false;
  if (override === "surrender" && !canSurrender) return false;
  return true;
}

/**
 * Find the first deviation rule that matches the current hand. Returns the
 * override (if legal) or undefined.
 *
 * Match semantics:
 *   - when="pair": hand must be a pair; playerTotal matches rankValue of the
 *     pair (A=1, T/J/Q/K=10); dealerUp matches if specified.
 *   - when="hard": hand must be hard (no usable ace as 11); playerTotal must
 *     equal the hard total.
 *   - when="soft": hand must be soft; playerTotal must equal the soft total.
 */
function matchDeviation(
  rules: readonly DeviationRule[],
  playerCards: readonly Card[],
  dealerUp: Card,
  canDouble: boolean,
  canSplit: boolean,
  canSurrender: boolean,
): BSAction | undefined {
  if (rules.length === 0) return undefined;

  const hv = evaluate(playerCards);
  const dealerVal = (() => {
    const v = rankValue(dealerUp.rank);
    return v === 1 ? 1 : v; // Ace=1, else nominal 2..10
  })();
  const pair = isPair(playerCards);
  const pairVal = pair ? rankValue(playerCards[0]!.rank) : undefined;

  for (const r of rules) {
    if (r.dealerUp !== undefined && r.dealerUp !== dealerVal) continue;
    if (r.when === "pair") {
      if (!pair) continue;
      if (r.playerTotal !== undefined && r.playerTotal !== pairVal) continue;
    } else if (r.when === "hard") {
      if (hv.soft) continue;
      if (r.playerTotal !== undefined && r.playerTotal !== hv.total) continue;
    } else if (r.when === "soft") {
      if (!hv.soft) continue;
      if (r.playerTotal !== undefined && r.playerTotal !== hv.total) continue;
    }
    if (!overrideIsLegal(r.override, canDouble, canSplit, canSurrender)) {
      continue;
    }
    return r.override;
  }
  return undefined;
}

/** Return the NPC's action. Pure + deterministic given (input, personality, seed). */
export function npcDecidePlay(
  input: NpcPlayInput,
  personality: NpcPersonality,
  seed: number,
): BSAction {
  const { seat, dealerUp, rules, canDouble, canSplit, canSurrender } = input;

  if (seat.player.kind !== "npc") {
    throw new Error("npcDecidePlay called on non-NPC seat");
  }

  // Defensive: no active hand → stand. Shouldn't happen in practice.
  if (seat.hands.length === 0 || seat.activeHandIndex >= seat.hands.length) {
    return "stand";
  }
  const hand = seat.hands[seat.activeHandIndex]!;
  const playerCards = hand.cards;

  const cfg = PERSONALITIES[personality];

  // 1. Basic strategy baseline.
  let action: BSAction = decideBasicStrategy({
    playerCards,
    dealerUp,
    rules,
    canDouble,
    canSplit,
    canSurrender,
    canDoubleAfterSplit: rules.allowDoubleAfterSplit,
  });

  // 2. Static deviations (first match wins, must be legal).
  const deviation = matchDeviation(
    cfg.deviationRules,
    playerCards,
    dealerUp,
    canDouble,
    canSplit,
    canSurrender,
  );
  if (deviation !== undefined) {
    action = deviation;
  }

  // 3. Noise — tilt-scaled. If the seeded roll clears effectiveNoise, swap to
  //    a random *other* legal action.
  const tilt = seat.tilt ?? 0;
  const effectiveNoise = cfg.playNoise + tilt * cfg.tiltPlayImpact;
  if (effectiveNoise > 0) {
    const fireRoll = seededUnit(seed, seat.index, playerCards.length, "play-fire");
    if (fireRoll < effectiveNoise) {
      const legal = legalActions(canDouble, canSplit, canSurrender);
      const alternatives = legal.filter((a) => a !== action);
      if (alternatives.length > 0) {
        const pickRoll = seededUnit(
          seed,
          seat.index,
          playerCards.length,
          "play-pick",
        );
        const idx = Math.floor(pickRoll * alternatives.length);
        // Guard against edge case where pickRoll === 1 (shouldn't happen — the
        // hash returns [0,1), but be defensive).
        action = alternatives[Math.min(idx, alternatives.length - 1)]!;
      }
    }
  }

  return action;
}

/**
 * Return the NPC's bet amount in chips. Integer, clamped by engine rules
 * (minBet/maxBet) and seat bankroll.
 */
export function npcDecideBet(
  input: NpcBetInput,
  personality: NpcPersonality,
  // seed is reserved for future jitter; not currently used. Present for API
  // symmetry with npcDecidePlay and to allow future stochastic policies.
  _seed: number,
): number {
  const { seat, rules, counter, lastResult, currentBet, streak } = input;

  if (seat.player.kind !== "npc") {
    throw new Error("npcDecideBet called on non-NPC seat");
  }

  const cfg = PERSONALITIES[personality];
  const unit = rules.minBet * cfg.betUnitMultiplier;

  const ctx: BetContext = {
    bankroll: seat.player.bankroll,
    rules,
    lastResult,
    currentBet,
    streak,
    trueCount: cfg.usesCounter && counter ? trueCount(counter) : undefined,
    unit,
  };

  const { amount } = decideBet(cfg.betPolicy, ctx);

  // Apply tilt bet impact. Positive (chaser) inflates, negative (risk_averse)
  // deflates.
  const tilt = seat.tilt ?? 0;
  const tiltFactor = 1 + tilt * cfg.tiltBetImpact;
  const tilted = Math.floor(amount * tiltFactor);

  // Final clamp to [minBet, min(maxBet, bankroll)]. If bankroll < minBet the
  // seat is effectively busted; we still clamp to a non-negative ceiling.
  const ceiling = Math.min(rules.maxBet, seat.player.bankroll);
  const floor = Math.min(rules.minBet, ceiling);
  let out = tilted;
  if (!Number.isFinite(out) || out < 0) out = 0;
  if (out < floor) out = floor;
  if (out > ceiling) out = ceiling;
  return out;
}
