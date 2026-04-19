import { createGame, type Card, type EngineEvent, type Outcome, type RuleSetId } from "@blackjack/engine";

const game = createGame({ ruleSetId: "VEGAS" });

const OUTCOME_LABEL: Record<Outcome, { zh: string; en: string; symbol: string }> = {
  win:       { zh: "赢",       en: "WIN",       symbol: "✓" },
  blackjack: { zh: "黑杰克!",  en: "BLACKJACK", symbol: "★" },
  push:      { zh: "平局",     en: "PUSH",      symbol: "=" },
  loss:      { zh: "输",       en: "LOSS",      symbol: "✗" },
  bust:      { zh: "爆牌",     en: "BUST",      symbol: "✗" },
  surrender: { zh: "投降",     en: "SURR",      symbol: "⤺" },
};
function outcomeCls(o: Outcome): string {
  if (o === "win" || o === "blackjack") return "log-win";
  if (o === "push") return "log-push";
  return "log-loss";
}

const $ = <T extends HTMLElement = HTMLElement>(id: string): T =>
  document.getElementById(id) as T;

const dealerCards = $("dealerCards");
const dealerTotal = $("dealerTotal");
const playerHands = $("playerHands");
const betAmount = $<HTMLInputElement>("betAmount");
const sbPP = $<HTMLInputElement>("sbPP");
const sb213 = $<HTMLInputElement>("sb213");
const sbLL = $<HTMLInputElement>("sbLL");
const ruleSetSel = $<HTMLSelectElement>("ruleSet");
const logEl = $("log");
const bankrollEl = $("bankroll");
const phaseEl = $("phase");

function cardEl(c: Card, faceDown = false): HTMLElement {
  const el = document.createElement("div");
  el.className = "card" + (faceDown ? " back" : "") + (c.suit === "♥" || c.suit === "♦" ? " red" : "");
  if (faceDown) {
    el.textContent = "";
    return el;
  }
  el.innerHTML = `<span class="suit">${c.suit}</span><span class="rank">${c.rank}</span><span class="bot">${c.rank}${c.suit}</span>`;
  return el;
}

function log(msg: string, cls = ""): void {
  const line = document.createElement("div");
  if (cls) line.className = cls;
  line.textContent = msg;
  logEl.prepend(line);
}

const PHASE_ZH: Record<string, string> = {
  betting: "下注", dealing: "发牌中", insurance: "保险",
  playerTurn: "你的回合", dealerTurn: "庄家回合",
  settlement: "结算中", roundOver: "本轮结束",
};

function render(): void {
  const s = game.getState();
  bankrollEl.textContent = `筹码: ${s.bankroll}`;
  phaseEl.textContent = `阶段: ${PHASE_ZH[s.phase] ?? s.phase}`;
  ruleSetSel.value = s.ruleSet.id;

  dealerCards.replaceChildren();
  s.dealer.forEach((c, i) => {
    dealerCards.appendChild(cardEl(c, i === 1 && s.dealerHoleHidden));
  });
  dealerTotal.textContent = s.dealer.length
    ? `total: ${s.dealerValue.total}${s.dealerValue.soft ? " soft" : ""}${s.dealerHoleHidden ? " (showing)" : ""}`
    : "";

  playerHands.replaceChildren();
  s.hands.forEach((h, i) => {
    const hd = document.createElement("div");
    hd.className = "hand" + (i === s.activeHandIndex && s.phase === "playerTurn" ? " active" : "");
    const cc = document.createElement("div");
    cc.className = "cards";
    h.cards.forEach((c) => cc.appendChild(cardEl(c)));
    hd.appendChild(cc);
    const meta = document.createElement("div");
    const hv = s.handValues[i]!;
    const result = s.roundResults.find((r) => r.handIndex === i);
    let resultTag = "";
    if (result) {
      const L = OUTCOME_LABEL[result.outcome];
      const net = result.payout - h.bet;
      const netStr = net > 0 ? `+${net}` : net < 0 ? `${net}` : "±0";
      resultTag = `  <span class="result-tag ${outcomeCls(result.outcome)}">${L.symbol} ${L.zh} ${netStr}</span>`;
    }
    meta.className = "bet";
    meta.innerHTML = `押注 ${h.bet}  ·  点数 ${hv.total}${hv.soft ? " 软" : ""}${h.doubled ? "  (加倍)" : ""}${h.surrendered ? "  (投降)" : ""}${resultTag}`;
    hd.appendChild(meta);
    playerHands.appendChild(hd);
  });

  const legal = new Set(s.legalActions);
  document.querySelectorAll<HTMLButtonElement>("#actions button").forEach((b) => {
    b.disabled = !legal.has(b.dataset.action as never);
  });
  ($("deal") as HTMLButtonElement).disabled = s.phase !== "betting";
}

function showBanner(text: string, cls: string): void {
  const b = document.getElementById("resultBanner");
  if (!b) return;
  b.textContent = text;
  b.className = `banner ${cls} show`;
  setTimeout(() => { b.className = `banner ${cls}`; }, 3500);
}

game.on((e: EngineEvent) => {
  switch (e.type) {
    case "SIDEBET_WIN":
      log(`边注: ${e.label} +${e.payout}`, "log-side");
      break;
    case "BET_SETTLED": {
      const bet = game.getState().hands[e.handIndex]?.bet ?? 0;
      const net = e.payout - bet;
      const L = OUTCOME_LABEL[e.outcome];
      const netStr = net > 0 ? `净赚 +${net}` : net < 0 ? `净亏 ${net}` : `平 ±0`;
      log(`${L.symbol} 第${e.handIndex + 1}手: ${L.zh} · 押${bet} · ${netStr}`, outcomeCls(e.outcome));
      break;
    }
    case "ROUND_OVER": {
      let totalNet = 0;
      for (const r of e.results) {
        const bet = game.getState().hands[r.handIndex]?.bet ?? 0;
        totalNet += r.payout - bet;
      }
      if (totalNet > 0) showBanner(`本轮 赢 +${totalNet}`, "banner-win");
      else if (totalNet < 0) showBanner(`本轮 输 ${totalNet}`, "banner-loss");
      else showBanner(`本轮 平局 ±0`, "banner-push");
      break;
    }
    case "NATURAL_BLACKJACK":
      log("★ 天胡!(Blackjack)", "log-win");
      break;
    case "HAND_BUST":
      log(`第${e.handIndex + 1}手 爆牌`, "log-loss");
      break;
    case "SHOE_SHUFFLED":
      log("— 洗牌 —");
      break;
    case "ERROR":
      log(`! ${e.code}: ${e.message}`, "log-loss");
      break;
  }
  render();
});

$("deal").addEventListener("click", () => {
  game.dispatch({
    type: "PLACE_BET",
    amount: Number(betAmount.value),
    sideBets: {
      perfectPairs: Number(sbPP.value) || 0,
      twentyOneP3: Number(sb213.value) || 0,
      luckyLadies: Number(sbLL.value) || 0,
    },
  });
});

document.querySelectorAll<HTMLButtonElement>("#actions button").forEach((b) => {
  b.addEventListener("click", () => {
    const a = b.dataset.action!;
    if (a === "INSURE") {
      const amt = Math.floor(game.getState().hands[0]!.bet / 2);
      game.dispatch({ type: "INSURE", amount: amt });
    } else {
      game.dispatch({ type: a } as Parameters<typeof game.dispatch>[0]);
    }
  });
});

ruleSetSel.addEventListener("change", () => {
  game.setRuleSet(ruleSetSel.value as RuleSetId);
  logEl.replaceChildren();
  log(`ruleset → ${ruleSetSel.value}`);
});

render();
