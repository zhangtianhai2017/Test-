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

function showBanner(titleHtml: string, subtitle: string, cls: string, holdMs = 4200): void {
  const b = document.getElementById("resultBanner");
  if (!b) return;
  b.innerHTML = `<div class="banner-title">${titleHtml}</div><div class="banner-sub">${subtitle}</div>`;
  b.className = `banner ${cls} show`;
  setTimeout(() => { b.className = `banner ${cls}`; }, holdMs);
}

interface SideBetWon { kind: string; label: string; payout: number; }
let roundSideBets: SideBetWon[] = [];

function handReason(r: { outcome: string; total: number; cards: readonly Card[] }, dealerTotal: number, dealerBust: boolean, dealerBJ: boolean): string {
  if (r.outcome === "blackjack") return "两张牌凑 21 — 天胡";
  if (r.outcome === "bust") return `玩家爆牌(${r.total})`;
  if (r.outcome === "surrender") return "中途投降,返一半";
  if (r.outcome === "push") return `平手(双方都是 ${r.total})`;
  if (r.outcome === "win") {
    if (r.cards.length >= 5 && r.total === 21) return `五龙 21!${r.cards.length} 张牌凑 21`;
    if (dealerBust) return `庄家爆牌(${dealerTotal}),你 ${r.total} 稳赢`;
    if (r.total === 21) return `你 21 大过庄家 ${dealerTotal}`;
    return `${r.total} 大过庄家 ${dealerTotal}`;
  }
  if (r.outcome === "loss") {
    if (dealerBJ) return `庄家天胡(${dealerTotal})`;
    return `${r.total} 小过庄家 ${dealerTotal}`;
  }
  return "";
}

function bannerForRound(totalNet: number, reasons: string[], isBlackjack: boolean, has5Card21: boolean): { title: string; sub: string; cls: string } {
  const sideBonus = roundSideBets.reduce((s, x) => s + x.payout, 0);
  const sideBigWin = roundSideBets.find((x) => x.payout >= 100);

  if (sideBigWin) {
    return {
      title: `💎 边注巨奖 💎<br><span class="banner-mega">${sideBigWin.label}</span>`,
      sub: `+${sideBonus} 筹码 — ${reasons.join(" · ")}`,
      cls: "banner-mega",
    };
  }
  if (isBlackjack) {
    return {
      title: `★ 天 胡 ★<br><span class="banner-bj">B L A C K J A C K</span>`,
      sub: `+${totalNet} 筹码 · 3:2 赔率`,
      cls: "banner-blackjack",
    };
  }
  if (has5Card21) {
    return {
      title: `🐉 五 龙 21 🐉`,
      sub: `+${totalNet} 筹码 · ${reasons.join(" · ")}`,
      cls: "banner-bigwin",
    };
  }
  if (totalNet >= 200) {
    return {
      title: `💰 爆 赢 +${totalNet} 💰`,
      sub: reasons.join(" · "),
      cls: "banner-bigwin",
    };
  }
  if (totalNet > 0) {
    return {
      title: `✓ 本轮赢 +${totalNet}`,
      sub: reasons.join(" · "),
      cls: "banner-win",
    };
  }
  if (totalNet < 0) {
    return {
      title: `✗ 本轮输 ${totalNet}`,
      sub: reasons.join(" · "),
      cls: "banner-loss",
    };
  }
  return {
    title: `= 本轮平局 ±0`,
    sub: reasons.join(" · "),
    cls: "banner-push",
  };
}

game.on((e: EngineEvent) => {
  switch (e.type) {
    case "PHASE_CHANGED":
      if (e.phase === "betting") roundSideBets = [];
      break;
    case "SIDEBET_WIN":
      roundSideBets.push({ kind: e.kind, label: e.label, payout: e.payout });
      log(`边注中奖: ${e.label} +${e.payout}`, "log-side");
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
      const s = game.getState();
      const dealerEval = s.dealerValue;
      const dealerBust = dealerEval.isBust;
      const dealerBJ = s.dealer.length === 2 && dealerEval.total === 21;
      let totalNet = 0;
      let anyBJ = false;
      let any5Card21 = false;
      const reasons: string[] = [];
      for (const r of e.results) {
        const bet = s.hands[r.handIndex]?.bet ?? 0;
        totalNet += r.payout - bet;
        if (r.outcome === "blackjack") anyBJ = true;
        if (r.outcome === "win" && r.cards.length >= 5 && r.total === 21) any5Card21 = true;
        reasons.push(handReason(r, dealerEval.total, dealerBust, dealerBJ));
      }
      const { title, sub, cls } = bannerForRound(totalNet, reasons, anyBJ, any5Card21);
      showBanner(title, sub, cls);
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
