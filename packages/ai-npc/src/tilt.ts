/**
 * Tilt model for NPCs.
 *
 * Tilt is a 0..1 scalar reflecting a player's emotional state.
 * - Rises after losses, busts, surrenders, and big losses.
 * - Drops after wins and pushes.
 * - Decays passively toward 0 over time (via `passiveDecay`).
 *
 * All deltas are scaled by `cfg.sensitivity`, which is typically set per
 * personality (e.g. `optimal` uses 0 for stoic, `chaser` uses 1.0).
 *
 * The module is purely functional — no mutable state.
 */
import type { Outcome } from "@blackjack/engine";

export interface TiltConfig {
  winDecay: number;             // how much tilt drops on win
  pushDecay: number;            // drops on push
  lossBump: number;             // rises on loss
  bustBump: number;             // rises on bust
  surrenderBump: number;        // rises on surrender
  bigLossBump: number;          // rises on big loss (in addition to loss/bust)
  bigLossThreshold: number;     // |netDelta| / unit above which bigLossBump applies
  passiveDecayPerRound: number; // passive decay applied by `passiveDecay`
  maxTilt: number;              // clamp upper
  minTilt: number;              // clamp lower
  sensitivity: number;          // multiplier applied to all deltas
}

export const DEFAULT_TILT: TiltConfig = {
  winDecay: 0.15,
  pushDecay: 0.05,
  lossBump: 0.12,
  bustBump: 0.18,
  surrenderBump: 0.05,
  bigLossBump: 0.25,
  bigLossThreshold: 2,
  passiveDecayPerRound: 0.03,
  maxTilt: 1.0,
  minTilt: 0.0,
  sensitivity: 1.0,
};

function clamp(v: number, lo: number, hi: number): number {
  if (v < lo) return lo;
  if (v > hi) return hi;
  return v;
}

/**
 * Compute a new tilt value given an outcome and its net payout delta.
 *
 * `netDelta` is (payout - bet) from the engine's HandResult semantics. A
 * losing hand of 2 units bet returns `netDelta = -2`. "Big loss" triggers
 * when `-netDelta >= cfg.bigLossThreshold * unit` on a loss/bust outcome.
 *
 * `unit` is the personality's base bet unit, used to scale the big-loss
 * threshold so it remains meaningful regardless of table stakes.
 */
export function updateTilt(
  currentTilt: number,
  outcome: Outcome,
  netDelta: number,
  unit: number,
  cfg?: Partial<TiltConfig>,
): number {
  const c: TiltConfig = { ...DEFAULT_TILT, ...(cfg ?? {}) };
  const s = c.sensitivity;

  let delta = 0;
  switch (outcome) {
    case "win":
    case "blackjack":
      delta = -c.winDecay;
      break;
    case "push":
      delta = -c.pushDecay;
      break;
    case "loss":
      delta = c.lossBump;
      break;
    case "bust":
      delta = c.bustBump;
      break;
    case "surrender":
      delta = c.surrenderBump;
      break;
  }

  // Big-loss bump stacks on top of loss/bust for a sufficiently bad hit.
  if (outcome === "loss" || outcome === "bust") {
    const safeUnit = unit > 0 ? unit : 1;
    if (-netDelta >= c.bigLossThreshold * safeUnit) {
      delta += c.bigLossBump;
    }
  }

  const next = currentTilt + delta * s;
  return clamp(next, c.minTilt, c.maxTilt);
}

/**
 * Passive tilt decay, applied once per round regardless of outcome. Use in
 * addition to (not instead of) `updateTilt` — e.g. call at the end of each
 * round to let tilt bleed off over time even while the player keeps losing.
 */
export function passiveDecay(currentTilt: number, cfg?: Partial<TiltConfig>): number {
  const c: TiltConfig = { ...DEFAULT_TILT, ...(cfg ?? {}) };
  const next = currentTilt - c.passiveDecayPerRound * c.sensitivity;
  return clamp(next, c.minTilt, c.maxTilt);
}
