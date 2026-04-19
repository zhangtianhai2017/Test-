import type { Card } from "./cards.js";
import { evaluate } from "./hand.js";
import type { RuleSet } from "./rules.js";

export function dealerShouldHit(cards: readonly Card[], rules: RuleSet): boolean {
  const v = evaluate(cards);
  if (v.isBust) return false;
  if (v.total < 17) return true;
  if (v.total === 17 && v.soft && rules.dealerHitsSoft17) return true;
  return false;
}
