import type { RuleSet } from "@blackjack/engine";

export type BetPolicyId = "flat" | "kelly" | "reverse-martingale" | "unit-spread";

export type BetResult =
  | "win"
  | "loss"
  | "push"
  | "blackjack"
  | "bust"
  | "surrender"
  | "none";

export interface BetContext {
  bankroll: number;
  rules: RuleSet;
  lastResult?: BetResult;
  /** Last bet amount (for progression policies). */
  currentBet?: number;
  /** +N winning streak, -N losing streak. */
  streak?: number;
  /** For "kelly". */
  trueCount?: number;
  /** Base unit for "unit-spread"; defaults to rules.minBet. */
  unit?: number;
}

export interface BetPolicyResult {
  /** Integer, clamped to [minBet, min(maxBet, bankroll)]. */
  amount: number;
  /** Human-readable, short. */
  rationale: string;
}

function clampBet(amount: number, ctx: BetContext): number {
  const { minBet, maxBet } = ctx.rules;
  const ceiling = Math.min(maxBet, ctx.bankroll);
  // If bankroll is below minBet the player is busted; still clamp to ceiling
  // which may be < minBet in that pathological case.
  const lo = Math.min(minBet, ceiling);
  let out = Math.round(amount);
  if (out < lo) out = lo;
  if (out > ceiling) out = ceiling;
  if (out < 0) out = 0;
  return out;
}

function flatPolicy(ctx: BetContext): BetPolicyResult {
  const unit = ctx.unit ?? ctx.rules.minBet;
  return { amount: clampBet(unit, ctx), rationale: "flat" };
}

function reverseMartingalePolicy(ctx: BetContext): BetPolicyResult {
  const unit = ctx.unit ?? ctx.rules.minBet;
  const cap = unit * 4;
  const last = ctx.lastResult ?? "none";
  const current = ctx.currentBet ?? unit;

  let next: number;
  let note: string;
  if (last === "win" || last === "blackjack") {
    const doubled = current * 2;
    if (doubled > cap) {
      next = cap;
      note = `rev-martingale cap ${cap}`;
    } else {
      next = doubled;
      note = `rev-martingale press ${next}`;
    }
  } else if (last === "push") {
    next = current;
    note = "rev-martingale push hold";
  } else if (
    last === "loss" ||
    last === "bust" ||
    last === "surrender"
  ) {
    next = unit;
    note = "rev-martingale reset";
  } else {
    next = unit;
    note = "rev-martingale start";
  }
  return { amount: clampBet(next, ctx), rationale: note };
}

function kellyPolicy(ctx: BetContext): BetPolicyResult {
  const unit = ctx.unit ?? ctx.rules.minBet;
  const tc = ctx.trueCount ?? 0;
  // 1-8 ramp: multiplier = clamp(floor(tc - 0.5), 1, 8)
  let multiplier = Math.floor(tc - 0.5);
  if (multiplier < 1) multiplier = 1;
  if (multiplier > 8) multiplier = 8;
  const raw = unit * multiplier;
  const amount = clampBet(Math.max(ctx.rules.minBet, raw), ctx);
  return { amount, rationale: `Kelly tc=${tc}` };
}

function unitSpreadPolicy(ctx: BetContext): BetPolicyResult {
  const unit = ctx.unit ?? ctx.rules.minBet;
  const streak = ctx.streak ?? 0;
  let mult: number;
  let note: string;
  if (streak >= 3) {
    mult = 4;
    note = `spread hot streak=${streak}`;
  } else if (streak >= 1) {
    mult = 2;
    note = `spread warm streak=${streak}`;
  } else if (streak <= -2) {
    mult = 1;
    note = `spread cold streak=${streak}`;
  } else {
    mult = 1;
    note = `spread neutral streak=${streak}`;
  }
  return { amount: clampBet(unit * mult, ctx), rationale: note };
}

export function decideBet(policy: BetPolicyId, ctx: BetContext): BetPolicyResult {
  switch (policy) {
    case "flat":
      return flatPolicy(ctx);
    case "reverse-martingale":
      return reverseMartingalePolicy(ctx);
    case "kelly":
      return kellyPolicy(ctx);
    case "unit-spread":
      return unitSpreadPolicy(ctx);
  }
}
