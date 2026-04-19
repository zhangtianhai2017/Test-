import { createGame, type Card, type EngineEvent, type RuleSetId } from "@blackjack/engine";

const game = createGame({ ruleSetId: "VEGAS" });

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

function render(): void {
  const s = game.getState();
  bankrollEl.textContent = `bankroll: ${s.bankroll}`;
  phaseEl.textContent = `phase: ${s.phase}`;
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
    meta.className = "bet";
    meta.textContent = `bet=${h.bet}  total=${hv.total}${hv.soft ? " soft" : ""}${h.doubled ? "  (doubled)" : ""}${h.surrendered ? "  (surrendered)" : ""}`;
    hd.appendChild(meta);
    playerHands.appendChild(hd);
  });

  const legal = new Set(s.legalActions);
  document.querySelectorAll<HTMLButtonElement>("#actions button").forEach((b) => {
    b.disabled = !legal.has(b.dataset.action as never);
  });
  ($("deal") as HTMLButtonElement).disabled = s.phase !== "betting";
}

game.on((e: EngineEvent) => {
  switch (e.type) {
    case "SIDEBET_WIN":
      log(`side bet ${e.kind}: ${e.label} +${e.payout}`, "log-side");
      break;
    case "BET_SETTLED":
      log(
        `hand ${e.handIndex}: ${e.outcome} +${e.payout}`,
        e.outcome === "win" || e.outcome === "blackjack" ? "log-win" : e.outcome === "push" ? "log-push" : "log-loss",
      );
      break;
    case "NATURAL_BLACKJACK":
      log("★ BLACKJACK!", "log-win");
      break;
    case "HAND_BUST":
      log(`hand ${e.handIndex} BUST`, "log-loss");
      break;
    case "SHOE_SHUFFLED":
      log("— shoe reshuffled —");
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
