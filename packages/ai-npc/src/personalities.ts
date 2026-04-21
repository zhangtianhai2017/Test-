/**
 * Personality configurations for NPC players.
 *
 * Each personality is a data-driven config that composes:
 *   - a bet policy id (from betPolicies.ts)
 *   - a bet unit multiplier (relative to rules.minBet)
 *   - a play-noise factor (probability of a random legal action)
 *   - a set of static deviation rules that override Basic Strategy
 *   - tilt sensitivity + how tilt influences play accuracy and bet size
 *
 * Personalities are paired with tell banks in tells.ts.
 */
import type { NpcPersonality } from "@blackjack/engine";
import type { BetPolicyId } from "./betPolicies.js";

export interface DeviationRule {
  when: "hard" | "soft" | "pair";
  /** For "hard"/"soft": the player's total. For "pair": the pair's rank value (A=1). */
  playerTotal?: number;
  /** Dealer up-card value: 1 = Ace, 2..9 = nominal, 10 = T/J/Q/K. */
  dealerUp?: number;
  override: "hit" | "stand" | "double" | "split" | "surrender";
}

export interface PersonalityConfig {
  id: NpcPersonality;
  nameZh: string;
  nameEn: string;
  description: string;
  betPolicy: BetPolicyId;
  /** Base unit = rules.minBet * this. */
  betUnitMultiplier: number;
  /** 0..1 — probability of making a random legal action instead of BS. */
  playNoise: number;
  deviationRules: DeviationRule[];
  /** Scales the tilt model's deltas (passed into TiltConfig.sensitivity). */
  tiltSensitivity: number;
  /** 0..1 — tilt × this = extra play noise applied at high tilt. */
  tiltPlayImpact: number;
  /**
   * Signed in roughly [-1, +1]. Positive values push bets upward under tilt
   * (chasers), negative values push bets downward (risk-averse).
   */
  tiltBetImpact: number;
  /** True = Hi-Lo true count feeds the bet policy. Only meaningful for counter. */
  usesCounter: boolean;
}

export const PERSONALITIES: Record<NpcPersonality, PersonalityConfig> = {
  optimal: {
    id: "optimal",
    nameZh: "最优",
    nameEn: "Optimal",
    description: "Strict basic strategy, flat bets, unflappable.",
    betPolicy: "flat",
    betUnitMultiplier: 1,
    playNoise: 0,
    deviationRules: [],
    tiltSensitivity: 0,
    tiltPlayImpact: 0,
    tiltBetImpact: 0,
    usesCounter: false,
  },
  counter: {
    id: "counter",
    nameZh: "算牌者",
    nameEn: "Counter",
    description: "Basic strategy with Hi-Lo true-count bet spread.",
    betPolicy: "kelly",
    betUnitMultiplier: 1,
    playNoise: 0,
    deviationRules: [],
    tiltSensitivity: 0.3,
    tiltPlayImpact: 0.05,
    tiltBetImpact: -0.2,
    usesCounter: true,
  },
  amateur: {
    id: "amateur",
    nameZh: "业余",
    nameEn: "Amateur",
    description: "Mostly basic strategy with small mistakes and visible emotion.",
    betPolicy: "flat",
    betUnitMultiplier: 1,
    playNoise: 0.08,
    deviationRules: [
      // Splits 9,9 vs 7 instead of standing.
      { when: "pair", playerTotal: 9, dealerUp: 7, override: "split" },
    ],
    tiltSensitivity: 0.6,
    tiltPlayImpact: 0.3,
    tiltBetImpact: 0.2,
    usesCounter: false,
  },
  chaser: {
    id: "chaser",
    nameZh: "追损者",
    nameEn: "Chaser",
    description: "Presses winners, shoves on losers, tilts hard.",
    betPolicy: "reverse-martingale",
    betUnitMultiplier: 1,
    playNoise: 0.05,
    deviationRules: [
      // Aggressive: hits 12 vs 6 instead of standing.
      { when: "hard", playerTotal: 12, dealerUp: 6, override: "hit" },
    ],
    tiltSensitivity: 1.0,
    tiltPlayImpact: 0.2,
    tiltBetImpact: 0.8,
    usesCounter: false,
  },
  superstitious: {
    id: "superstitious",
    nameZh: "迷信者",
    nameEn: "Superstitious",
    description: "Quirky static deviations driven by folklore.",
    betPolicy: "unit-spread",
    betUnitMultiplier: 1,
    playNoise: 0.1,
    deviationRules: [
      // "12 hates a 4." Hits 12 vs 4 instead of standing.
      { when: "hard", playerTotal: 12, dealerUp: 4, override: "hit" },
      // Always stands on 16 vs 10 (never surrenders — surrender is "unlucky").
      { when: "hard", playerTotal: 16, dealerUp: 10, override: "stand" },
      // Splits 10,10 vs 6 because "the dealer's going to bust."
      { when: "pair", playerTotal: 10, dealerUp: 6, override: "split" },
    ],
    tiltSensitivity: 0.7,
    tiltPlayImpact: 0.2,
    tiltBetImpact: 0.3,
    usesCounter: false,
  },
  ritualistic: {
    id: "ritualistic",
    nameZh: "仪式者",
    nameEn: "Ritualistic",
    description: "Rigorous basic strategy; rituals keep them calm.",
    betPolicy: "flat",
    betUnitMultiplier: 1,
    playNoise: 0.02,
    deviationRules: [],
    tiltSensitivity: 0.2,
    tiltPlayImpact: 0.05,
    tiltBetImpact: 0,
    usesCounter: false,
  },
  risk_averse: {
    id: "risk_averse",
    nameZh: "保守者",
    nameEn: "Risk-Averse",
    description: "Basic strategy minus aggressive moves; shrinks on tilt.",
    betPolicy: "flat",
    betUnitMultiplier: 1,
    playNoise: 0,
    deviationRules: [
      // Won't double 11 vs 10 — just hits.
      { when: "hard", playerTotal: 11, dealerUp: 10, override: "hit" },
      // Won't split 8,8 vs 10 — stands instead.
      { when: "pair", playerTotal: 8, dealerUp: 10, override: "stand" },
    ],
    tiltSensitivity: 0.4,
    tiltPlayImpact: 0.1,
    tiltBetImpact: -0.4,
    usesCounter: false,
  },
};
