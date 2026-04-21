/**
 * NPC tells — small visible gestures triggered by game events or states.
 *
 * Each personality owns a bank of (trigger, gesture, strength) entries.
 * When a trigger fires, `pickTell` deterministically decides — based on
 * `(personality, trigger, seed)` — whether a tell surfaces, and which.
 *
 * Purely functional; the mulberry32-style hash gives repeatability.
 */
import type { Gesture, NpcPersonality } from "@blackjack/engine";

export type TellTrigger =
  | "before-hit"
  | "before-stand"
  | "before-double"
  | "before-split"
  | "on-bust"
  | "on-win"
  | "on-loss"
  | "on-strong-hand"
  | "on-weak-hand";

export interface Tell {
  trigger: TellTrigger;
  gesture: Gesture;
  /** 0..1 probability this tell fires when the trigger hits. */
  strength: number;
}

/**
 * Personality tell banks.
 *
 * - `optimal`: poker-faced, no tells.
 * - `counter`: minimal, a brief confident nod on strong hands.
 * - `amateur`: sighs on stand, looks confident on strong hands.
 * - `chaser`: taunts after wins, celebrates loudly.
 * - `superstitious`: nervous before hits, celebrates wins, sighs losses.
 * - `ritualistic`: poker-faced ritual before split/double.
 * - `risk_averse`: nervous before any aggressive action.
 */
export const PERSONALITY_TELLS: Record<NpcPersonality, Tell[]> = {
  optimal: [],
  counter: [
    { trigger: "on-strong-hand", gesture: "confident", strength: 0.25 },
  ],
  amateur: [
    { trigger: "before-stand", gesture: "sigh", strength: 0.4 },
    { trigger: "on-strong-hand", gesture: "confident", strength: 0.6 },
    { trigger: "on-bust", gesture: "sigh", strength: 0.7 },
  ],
  chaser: [
    { trigger: "on-win", gesture: "taunt", strength: 0.7 },
    { trigger: "on-loss", gesture: "taunt", strength: 0.4 },
    { trigger: "before-double", gesture: "confident", strength: 0.6 },
  ],
  superstitious: [
    { trigger: "before-hit", gesture: "nervous", strength: 0.5 },
    { trigger: "on-win", gesture: "celebrate", strength: 0.6 },
    { trigger: "on-loss", gesture: "sigh", strength: 0.5 },
  ],
  ritualistic: [
    { trigger: "before-split", gesture: "poker-face", strength: 0.9 },
    { trigger: "before-double", gesture: "poker-face", strength: 0.9 },
  ],
  risk_averse: [
    { trigger: "before-hit", gesture: "nervous", strength: 0.5 },
    { trigger: "before-double", gesture: "nervous", strength: 0.8 },
    { trigger: "on-weak-hand", gesture: "nervous", strength: 0.6 },
  ],
};

/**
 * mulberry32-style deterministic hash → [0, 1).
 *
 * Same `(personality, trigger, seed)` triple always yields the same value.
 */
function hashToUnit(personality: NpcPersonality, trigger: TellTrigger, seed: number): number {
  // Stable per-string hashing (djb2-ish) folded into a 32-bit seed.
  const s = `${personality}|${trigger}|${seed}`;
  let h = 2166136261 >>> 0;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  // Mulberry32 step on the derived seed.
  let t = (h + 0x6d2b79f5) >>> 0;
  t = Math.imul(t ^ (t >>> 15), t | 1);
  t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
  const out = ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  return out;
}

/**
 * Deterministically resolve whether a tell fires.
 *
 * Returns the gesture if a matching tell exists AND its strength clears a
 * seeded pseudo-random draw in [0, 1); otherwise returns null. If multiple
 * tells share the same trigger (one per trigger is the convention, but we
 * support many), the first matching entry in the bank is evaluated.
 */
export function pickTell(
  personality: NpcPersonality,
  trigger: TellTrigger,
  seed: number,
): Gesture | null {
  const bank = PERSONALITY_TELLS[personality];
  const match = bank.find((t) => t.trigger === trigger);
  if (!match) return null;
  const roll = hashToUnit(personality, trigger, seed);
  return roll < match.strength ? match.gesture : null;
}
