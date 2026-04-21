/**
 * @blackjack/ai-npc — NPC player AI for the blackjack engine.
 *
 * Module layout (filled in by M2b..M2e):
 *   basicStrategy.ts — Vegas H17/S17 action lookup tables
 *   hiLoCounter.ts   — running + true count
 *   betPolicies.ts   — flat / Kelly / reverse-Martingale / unit-spread
 *   personalities.ts — 7 personality configs
 *   tells.ts         — per-NPC tell generators
 *   tilt.ts          — tilt model
 *   npcAgent.ts      — top-level decidePlay / decideBet
 *
 * Public API lives here (see exports).
 */

// Re-exports come in later milestones; M2a ships the skeleton only.
export const __moduleScaffolded = true;

export { decideBasicStrategy } from "./basicStrategy.js";
export type { BSAction, BSInput } from "./basicStrategy.js";

export {
  newCounter,
  observe,
  runningCount,
  decksRemaining,
  trueCount,
  reset,
  hiLoValue,
} from "./hiLoCounter.js";
export type { CounterState } from "./hiLoCounter.js";

export { decideBet } from "./betPolicies.js";
export type { BetPolicyId, BetContext, BetPolicyResult } from "./betPolicies.js";

export { PERSONALITIES } from "./personalities.js";
export type { PersonalityConfig, DeviationRule } from "./personalities.js";

export { updateTilt, passiveDecay, DEFAULT_TILT } from "./tilt.js";
export type { TiltConfig } from "./tilt.js";

export { PERSONALITY_TELLS, pickTell } from "./tells.js";
export type { Tell, TellTrigger } from "./tells.js";
