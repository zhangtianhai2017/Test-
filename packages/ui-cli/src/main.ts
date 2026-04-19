import { createGame, type EngineEvent, type RuleSetId } from "@blackjack/engine";
import { createInterface } from "node:readline/promises";
import { stdin as input, stdout as output } from "node:process";

const rl = createInterface({ input, output });

const fmtCard = (c: { rank: string; suit: string }): string => `${c.rank}${c.suit}`;

const ruleSetId = (process.argv[2] as RuleSetId) || "VEGAS";
const game = createGame({ ruleSetId });

game.on((e: EngineEvent) => {
  switch (e.type) {
    case "CARD_DEALT":
      console.log(`  ${e.to} [hand ${e.handIndex}] ← ${fmtCard(e.card)}${e.faceDown ? " (hole)" : ""}`);
      break;
    case "HOLE_CARD_REVEALED":
      console.log(`  dealer reveals hole: ${fmtCard(e.card)}`);
      break;
    case "SIDEBET_WIN":
      console.log(`  ✦ side bet ${e.kind}: ${e.label} → +${e.payout}`);
      break;
    case "NATURAL_BLACKJACK":
      console.log("  ★ BLACKJACK!");
      break;
    case "HAND_BUST":
      console.log(`  ✗ hand ${e.handIndex} BUST`);
      break;
    case "DEALER_ACTION":
      console.log(`  dealer ${e.action} (${e.soft ? "soft " : ""}${e.total})`);
      break;
    case "ROUND_OVER":
      console.log("— round over —");
      for (const r of e.results) {
        console.log(`  hand ${r.handIndex}: ${r.outcome} → +${r.payout}  [${r.cards.map(fmtCard).join(" ")}]${r.label ? " " + r.label : ""}`);
      }
      break;
    case "BANKROLL_CHANGED":
      // quiet
      break;
    case "ERROR":
      console.log(`  ! ${e.code}: ${e.message}`);
      break;
  }
});

function banner(): void {
  const s = game.getState();
  console.log(`\n[${s.ruleSet.name}]  bankroll=${s.bankroll}  phase=${s.phase}`);
}

async function main(): Promise<void> {
  console.log("Blackjack CLI — type 'q' to quit.");
  let playing = true;
  while (playing) {
    banner();
    const s = game.getState();
    if (s.phase === "betting") {
      const ans = await rl.question(`bet (or q): `);
      if (ans.trim() === "q") break;
      const amt = Number(ans);
      if (!Number.isFinite(amt)) continue;
      const sbStr = await rl.question("side bets? pp=0 21+3=0 lucky=0 > ");
      const m = /pp=(\d+).*21\+3=(\d+).*lucky=(\d+)/.exec(sbStr);
      const sb = m
        ? { perfectPairs: +m[1]!, twentyOneP3: +m[2]!, luckyLadies: +m[3]! }
        : undefined;
      game.dispatch({ type: "PLACE_BET", amount: amt, sideBets: sb });
    } else if (s.phase === "insurance") {
      const ans = await rl.question("insurance amount (0 to decline): ");
      const amt = Number(ans);
      if (amt > 0) game.dispatch({ type: "INSURE", amount: amt });
      else game.dispatch({ type: "DECLINE_INSURANCE" });
    } else if (s.phase === "playerTurn") {
      const h = s.hands[s.activeHandIndex]!;
      const v = s.handValues[s.activeHandIndex]!;
      console.log(
        `  hand ${s.activeHandIndex}: [${h.cards.map(fmtCard).join(" ")}] total=${v.total}${v.soft ? " soft" : ""}  dealer up=${fmtCard(s.dealer[0]!)}`,
      );
      const acts = s.legalActions.join("/");
      const ans = await rl.question(`action [${acts}] > `);
      const a = ans.trim().toUpperCase();
      if (a === "H") game.dispatch({ type: "HIT" });
      else if (a === "S") game.dispatch({ type: "STAND" });
      else if (a === "D") game.dispatch({ type: "DOUBLE" });
      else if (a === "P") game.dispatch({ type: "SPLIT" });
      else if (a === "R") game.dispatch({ type: "SURRENDER" });
      else game.dispatch({ type: "STAND" });
    } else if (s.phase === "roundOver") {
      const ans = await rl.question("[n]ext round / [q]uit / [r]uleset > ");
      if (ans.trim() === "q") playing = false;
      else if (ans.trim() === "r") {
        const r = await rl.question("VEGAS|SPANISH21|PONTOON|SUPER_FUN_21 > ");
        game.setRuleSet(r.trim() as RuleSetId);
      } else game.dispatch({ type: "NEW_ROUND" });
    } else {
      // transient phase; loop
    }
  }
  rl.close();
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
