# AGENT — ai-npc module

You are the maintainer of the NPC player AI. Read this whole file before
touching code.

## Purpose

NPCs that sit at seats other than the human's. They decide actions (hit /
stand / double / split / surrender / insurance) and bets (size and
progression) based on a **personality**. They have an emotional state
(**tilt**) that can shift their decisions.

They also have **tells** — small quirks visible to the human and to other
NPCs that reveal information about their hand strength or mental state.

## Scope — what you own

- `packages/ai-npc/` — new TS package, needs scaffolding if absent
  - `src/basicStrategy.ts`  — action lookup table (Vegas H17 + S17 variants)
  - `src/hiLoCounter.ts`    — running count / true count helper
  - `src/betPolicies.ts`    — flat / Kelly / reverse-martingale / unit-spread
  - `src/personalities.ts`  — 7 personality configs
  - `src/tells.ts`          — tell generation + detection helpers
  - `src/tilt.ts`            — tilt model + decay / amplification
  - `src/npcAgent.ts`        — top-level: `npcDecide(seatSnapshot, shoeSnapshot, personality) → Action`
  - `src/index.ts`
  - `test/` — Vitest cases

## Scope — what you do NOT own

- Engine rules / FSM (owned by `engine`).
- How NPC actions are fed back to the engine — that's glue code in
  `ue-plugin` or `engine`'s run-loop (see dispatch protocol).
- UI / rendering of NPCs.

## Public API (contract)

```typescript
export type NpcPersonality =
  | "optimal" | "counter" | "amateur" | "chaser"
  | "superstitious" | "ritualistic" | "risk_averse";

export interface NpcDecisionInput {
  seat: Seat;                  // from @blackjack/engine
  dealerUpCard: Card;
  shoe: ShoeInfo;              // public summary: cards seen, decks remaining
  rules: RuleSet;
  tilt: number;                // 0..1
}

export function npcDecidePlay(input: NpcDecisionInput, personality: NpcPersonality): ActionType;
export function npcDecideBet(input: NpcDecisionInput, personality: NpcPersonality): number;
export function npcTellFor(personality: NpcPersonality, seed: number): Tell;
```

## Key invariants

1. **Purely functional.** No mutable module state. Same input → same
   output. This is testable and deterministic.
2. **Independent of engine internals.** Accepts `Seat` and `Card` types
   from `@blackjack/engine` but never reads private state or mutates
   engine state.
3. **Basic Strategy tables must match canonical Wizard of Odds charts.**
   Provide citations in comments near the table data.
4. **Personalities are data-driven** — each personality is a config object
   composed of deviation_rules + bet_policy + tell_bank, not a switch
   statement deep in code.

## Personality specs (high-level, more detail on dispatch)

| id | Decision basis | Bet policy | Tilt reaction | Tell bank |
|---|---|---|---|---|
| `optimal` | Basic strategy, strict | Flat | No tilt effect | Minimal, poker-faced |
| `counter` | Basic strategy + Hi-Lo deviations | 1-8 unit spread by true count | Slight — bet spread shrinks when tilting | Rare micro-glances at shoe |
| `amateur` | Basic strategy with 5-10% random noise | Flat | Chases slightly | Fidgets with chips, visible sighs |
| `chaser` | Basic strategy mostly | Martingale on losses | Doubles down on bust hands near edge | Aggressive gestures |
| `superstitious` | Basic + quirky deviations ("never hit 12 after dealer's Q showed") | Flat | Changes seat when "unlucky" | Hand rituals, lucky charms |
| `ritualistic` | Basic strategy, rigorous | Flat | Rituals intensify | Knocking table 3 times, etc. |
| `risk_averse` | Basic strategy minus aggressive moves (less split, no double < 10) | Small flat | Withdraws, skips rounds | Hesitates, often checks bankroll |

## Tests

Run:

```bash
npm run test --workspace=@blackjack/ai-npc
```

Required coverage:
- Basic Strategy lookup returns known-correct action for every (total, dealer-up, soft/hard) bucket per Wikipedia/WoO reference chart
- Hi-Lo counter agrees with reference examples
- Personality deviations verified by fixtures
- Determinism: same seed → same tilt / same tell

## Escalation triggers

- Proposed personality deviation from Basic Strategy hurts the player's EV
  measurably (> 1% house edge increase) — user may not want that.
- A tell mechanic would require engine changes (not just ai-npc).
- Betting policy would let NPCs run out of bankroll too fast.
