import { createGame, type Action, type EngineEvent, type RuleSetId } from "@blackjack/engine";
import { writeFileSync, mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const outDir = resolve(here, "../vectors");
mkdirSync(outDir, { recursive: true });

interface Step {
  action: Action;
  events: EngineEvent[];
  bankrollAfter: number;
  phaseAfter: string;
}

interface Vector {
  description: string;
  ruleSetId: RuleSetId;
  seed: number;
  steps: Step[];
  finalBankroll: number;
  finalResults: { handIndex: number; outcome: string; payout: number; total: number }[];
}

function runScript(ruleSetId: RuleSetId, seed: number, script: Action[], description: string): Vector {
  const game = createGame({ ruleSetId, seed });
  const steps: Step[] = [];
  for (const action of script) {
    const captured: EngineEvent[] = [];
    const unsub = game.on((e) => captured.push(e));
    game.dispatch(action);
    unsub();
    const st = game.getState();
    steps.push({ action, events: captured, bankrollAfter: st.bankroll, phaseAfter: st.phase });
    if (st.phase === "roundOver") break;
    if (st.phase === "playerTurn" && action.type !== "STAND" && action.type !== "DOUBLE" && action.type !== "SURRENDER") {
      // continue scripted flow
    }
  }
  // If still in playerTurn after script, auto-stand remaining hands so we reach settlement
  while (game.getState().phase === "playerTurn") {
    const captured: EngineEvent[] = [];
    const unsub = game.on((e) => captured.push(e));
    const action: Action = { type: "STAND" };
    game.dispatch(action);
    unsub();
    steps.push({ action, events: captured, bankrollAfter: game.getState().bankroll, phaseAfter: game.getState().phase });
  }
  const final = game.getState();
  return {
    description,
    ruleSetId,
    seed,
    steps,
    finalBankroll: final.bankroll,
    finalResults: final.roundResults.map((r) => ({
      handIndex: r.handIndex,
      outcome: r.outcome,
      payout: r.payout,
      total: r.total,
    })),
  };
}

const scripts: Array<{ name: string; ruleSetId: RuleSetId; seed: number; actions: Action[]; desc: string }> = [
  { name: "vegas-stand", ruleSetId: "VEGAS", seed: 1, desc: "bet 25, stand", actions: [{ type: "PLACE_BET", amount: 25 }, { type: "STAND" }] },
  { name: "vegas-hit-stand", ruleSetId: "VEGAS", seed: 2, desc: "bet 25, hit, stand", actions: [{ type: "PLACE_BET", amount: 25 }, { type: "HIT" }, { type: "STAND" }] },
  { name: "vegas-double", ruleSetId: "VEGAS", seed: 3, desc: "bet 25, double", actions: [{ type: "PLACE_BET", amount: 25 }, { type: "DOUBLE" }] },
  { name: "vegas-stand-seed-123", ruleSetId: "VEGAS", seed: 123, desc: "bet 50, stand", actions: [{ type: "PLACE_BET", amount: 50 }, { type: "STAND" }] },
  { name: "vegas-stand-seed-7777", ruleSetId: "VEGAS", seed: 7777, desc: "bet 100, stand", actions: [{ type: "PLACE_BET", amount: 100 }, { type: "STAND" }] },
  { name: "spanish21-stand", ruleSetId: "SPANISH21", seed: 1, desc: "Spanish 21 bet 25, stand", actions: [{ type: "PLACE_BET", amount: 25 }, { type: "STAND" }] },
  { name: "pontoon-stand", ruleSetId: "PONTOON", seed: 1, desc: "Pontoon bet 25, stand", actions: [{ type: "PLACE_BET", amount: 25 }, { type: "STAND" }] },
  { name: "superfun-stand", ruleSetId: "SUPER_FUN_21", seed: 1, desc: "Super Fun 21 bet 25, stand", actions: [{ type: "PLACE_BET", amount: 25 }, { type: "STAND" }] },
];

const all = [];
for (const s of scripts) {
  const v = runScript(s.ruleSetId, s.seed, s.actions, s.desc);
  writeFileSync(resolve(outDir, `${s.name}.json`), JSON.stringify(v, null, 2));
  all.push({ name: s.name, file: `${s.name}.json`, ruleSetId: s.ruleSetId, seed: s.seed });
  console.log(`wrote ${s.name}.json  (final bankroll=${v.finalBankroll})`);
}
writeFileSync(resolve(outDir, "index.json"), JSON.stringify({ version: 1, vectors: all }, null, 2));
console.log(`index.json written with ${all.length} vectors`);
