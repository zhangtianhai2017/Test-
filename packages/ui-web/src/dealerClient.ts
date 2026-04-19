/** Thin client for the dealer-ai Python service (same API used by ui-3d and UE plugin). */

export type Language = "zh" | "en";
export type EventType =
  | "SESSION_OPEN" | "ROUND_START" | "CARD_DEALT" | "DEALER_UP_CARD"
  | "PLAYER_BUST" | "NATURAL_BLACKJACK" | "PLAYER_DOUBLE" | "PLAYER_SPLIT"
  | "PLAYER_SURRENDER" | "DEALER_BUST" | "ROUND_OVER"
  | "BIG_WIN" | "BIG_LOSS" | "SIDEBET_JACKPOT" | "STREAK_WIN" | "STREAK_LOSS"
  | "IDLE";

export interface DealerState {
  player_total?: number;
  dealer_total?: number;
  dealer_up?: string;
  outcome?: "win" | "loss" | "push" | "blackjack" | "bust" | "surrender";
  bet?: number;
  net?: number;
  bankroll?: number;
  streak?: number;
  rare_hand?: string | null;
  seat_index?: number;
}

export interface DealerQuip {
  text: string;
  tone: string;
  language: Language;
  source: "llm" | "fallback";
  latency_ms: number;
}

export interface DealerClient {
  baseUrl: string;
  sessionId: string | null;
  connected: boolean;
  open(language: Language, persona: string, playerName?: string): Promise<boolean>;
  quip(event: EventType, state: DealerState): Promise<DealerQuip | null>;
  close(): Promise<void>;
}

const DEFAULT_URL =
  (typeof localStorage !== "undefined" && localStorage.getItem("dealerAiUrl")) ||
  "http://127.0.0.1:8787";

export function createDealerClient(baseUrl: string = DEFAULT_URL): DealerClient {
  let sessionId: string | null = null;
  let connected = false;

  return {
    get baseUrl() { return baseUrl; },
    get sessionId() { return sessionId; },
    get connected() { return connected; },

    async open(language, persona, playerName) {
      try {
        const r = await fetch(`${baseUrl}/session`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ language, persona, player_name: playerName }),
        });
        if (!r.ok) { connected = false; return false; }
        const data = await r.json();
        sessionId = data.session_id;
        connected = true;
        return true;
      } catch {
        connected = false;
        return false;
      }
    },

    async quip(event, state) {
      if (!sessionId) return null;
      try {
        const r = await fetch(`${baseUrl}/session/${sessionId}/quip`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ event, state }),
          signal: AbortSignal.timeout(4000),
        });
        if (!r.ok) return null;
        return (await r.json()) as DealerQuip;
      } catch {
        return null;
      }
    },

    async close() {
      if (!sessionId) return;
      try {
        await fetch(`${baseUrl}/session/${sessionId}`, { method: "DELETE" });
      } catch { /* ignore */ }
      sessionId = null;
      connected = false;
    },
  };
}
