import { createGame, type Card, type EngineEvent, type Outcome, type RuleSetId } from "@blackjack/engine";
import { createDealerClient, type EventType as DealerEvent, type Language as DealerLang } from "./dealerClient.js";

const dealerClient = createDealerClient();
let uiLanguage: DealerLang = "zh";
let chosenPersona = "veteran";
const PERSONA_NAME: Record<string, { zh: string; en: string }> = {
  veteran: { zh: "老江湖 · 陈师傅", en: "Veteran · Mr. Chen" },
  hostess: { zh: "热情阿姨 · 王姐", en: "Hostess · Auntie Wang" },
  mystic:  { zh: "神秘赌神",        en: "The Mystic" },
};

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

// --- Dealer AI integration ---------------------------------------------

function showDealerBubble(text: string, source: string): void {
  const b = document.getElementById("dealerBubble");
  if (!b) return;
  (document.getElementById("dealerName") as HTMLElement).textContent =
    PERSONA_NAME[chosenPersona]?.[uiLanguage] ?? "Dealer";
  (document.getElementById("dealerText") as HTMLElement).textContent = text;
  (document.getElementById("dealerSrc") as HTMLElement).textContent = source;
  b.classList.add("show");
  window.clearTimeout((showDealerBubble as any)._t);
  (showDealerBubble as any)._t = window.setTimeout(() => b.classList.remove("show"), 5000);
}

async function askDealer(event: DealerEvent, state: Parameters<typeof dealerClient.quip>[1]): Promise<void> {
  const q = await dealerClient.quip(event, state);
  if (q) showDealerBubble(q.text, `${q.source} · ${q.latency_ms}ms`);
}

// Hook into engine events — fires alongside existing UI logic.
game.on((e) => {
  const s = game.getState();
  const dv = s.dealerValue;
  switch (e.type) {
    case "NATURAL_BLACKJACK":
      askDealer("NATURAL_BLACKJACK", { player_total: 21, bet: s.hands[0]?.bet, rare_hand: "natural-blackjack" });
      break;
    case "HAND_BUST":
      askDealer("PLAYER_BUST", { player_total: s.handValues[e.handIndex]?.total, bet: s.hands[e.handIndex]?.bet });
      break;
    case "SIDEBET_WIN":
      if (e.payout >= 100) askDealer("SIDEBET_JACKPOT", { rare_hand: e.kind, net: e.payout });
      break;
    case "PLAYER_ACTION":
      if (e.action === "DOUBLE") askDealer("PLAYER_DOUBLE", { seat_index: e.handIndex });
      else if (e.action === "SPLIT") askDealer("PLAYER_SPLIT", { seat_index: e.handIndex });
      else if (e.action === "SURRENDER") askDealer("PLAYER_SURRENDER", { seat_index: e.handIndex });
      break;
    case "ROUND_OVER": {
      let totalNet = 0, anyBJ = false, anyBust = false;
      for (const r of e.results) {
        const bet = s.hands[r.handIndex]?.bet ?? 0;
        totalNet += r.payout - bet;
        if (r.outcome === "blackjack") anyBJ = true;
        if (r.outcome === "bust") anyBust = true;
      }
      const state = {
        player_total: s.handValues[0]?.total,
        dealer_total: dv.total,
        outcome: anyBJ ? "blackjack" as const : anyBust ? "bust" as const : totalNet > 0 ? "win" as const : totalNet < 0 ? "loss" as const : "push" as const,
        bet: s.hands[0]?.bet,
        net: totalNet,
        bankroll: s.bankroll,
      };
      if (dv.isBust) askDealer("DEALER_BUST", state);
      else if (totalNet >= 200) askDealer("BIG_WIN", state);
      else if (totalNet <= -100) askDealer("BIG_LOSS", state);
      else askDealer("ROUND_OVER", state);
      break;
    }
  }
});

// --- Startup modal -----------------------------------------------------

async function bootDealerFlow(): Promise<void> {
  const modal = document.getElementById("startupModal")!;
  const statusEl = document.getElementById("serverStatus")!;
  const setSeg = (id: string, val: string) => {
    const group = document.getElementById(id)!;
    group.querySelectorAll("button").forEach((b) => b.classList.toggle("on", b.dataset.val === val));
  };
  document.getElementById("langSeg")!.addEventListener("click", (e) => {
    const t = e.target as HTMLButtonElement;
    if (t.dataset.val) { uiLanguage = t.dataset.val as DealerLang; setSeg("langSeg", uiLanguage); }
  });
  document.getElementById("personaSeg")!.addEventListener("click", (e) => {
    const t = e.target as HTMLButtonElement;
    if (t.dataset.val) { chosenPersona = t.dataset.val; setSeg("personaSeg", chosenPersona); }
  });

  // Probe server health.
  try {
    const r = await fetch(`${dealerClient.baseUrl}/health`, { signal: AbortSignal.timeout(1500) });
    if (r.ok) {
      const h = await r.json();
      const llm = h.llm?.ready ? "LLM on" : "fallback";
      const tts = h.tts?.ready ? "TTS on" : "no TTS";
      statusEl.textContent = `${h.version} · ${llm} · ${tts}`;
      statusEl.className = h.llm?.ready ? "ok" : "warn";
    } else {
      statusEl.textContent = "server error — fallback quips only";
      statusEl.className = "err";
    }
  } catch {
    statusEl.textContent = "offline — fallback quips only";
    statusEl.className = "err";
  }

  document.getElementById("startBtn")!.addEventListener("click", async () => {
    modal.classList.add("hidden");
    await dealerClient.open(uiLanguage, chosenPersona);
    askDealer("SESSION_OPEN", { bankroll: game.getState().bankroll });
  }, { once: true });
}

bootDealerFlow();
render();
