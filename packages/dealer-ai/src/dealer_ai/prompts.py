"""Build chat messages from (persona, event, state) in both languages."""
from __future__ import annotations

from .schema import EventType, GameState, Language, Persona


_EVENT_HINT_ZH: dict[EventType, str] = {
    EventType.SESSION_OPEN: "玩家刚入座。说句欢迎。",
    EventType.ROUND_START: "新一轮开始,提示玩家下注。",
    EventType.CARD_DEALT: "刚发出一张牌。",
    EventType.DEALER_UP_CARD: "亮出庄家明牌。",
    EventType.PLAYER_BUST: "玩家爆牌了。",
    EventType.NATURAL_BLACKJACK: "玩家开局天胡 Blackjack。",
    EventType.PLAYER_DOUBLE: "玩家加倍。",
    EventType.PLAYER_SPLIT: "玩家分牌。",
    EventType.PLAYER_SURRENDER: "玩家投降。",
    EventType.DEALER_BUST: "你(庄家)爆牌了,玩家赢。",
    EventType.ROUND_OVER: "本轮结束。",
    EventType.BIG_WIN: "玩家大赢(单轮净赚很多)。",
    EventType.BIG_LOSS: "玩家大输。",
    EventType.SIDEBET_JACKPOT: "玩家边注中大奖。",
    EventType.STREAK_WIN: "玩家连赢多把。",
    EventType.STREAK_LOSS: "玩家连输多把。",
    EventType.IDLE: "牌桌空档,随便聊一句。",
}

_EVENT_HINT_EN: dict[EventType, str] = {
    EventType.SESSION_OPEN: "Player just sat down. Greet them.",
    EventType.ROUND_START: "New round starts. Prompt for bets.",
    EventType.CARD_DEALT: "A card was just dealt.",
    EventType.DEALER_UP_CARD: "Dealer's up-card is revealed.",
    EventType.PLAYER_BUST: "Player busted.",
    EventType.NATURAL_BLACKJACK: "Player hit a natural blackjack.",
    EventType.PLAYER_DOUBLE: "Player doubled down.",
    EventType.PLAYER_SPLIT: "Player split a pair.",
    EventType.PLAYER_SURRENDER: "Player surrendered.",
    EventType.DEALER_BUST: "You (dealer) busted — player wins.",
    EventType.ROUND_OVER: "Round is over.",
    EventType.BIG_WIN: "Player had a big win this round.",
    EventType.BIG_LOSS: "Player had a big loss this round.",
    EventType.SIDEBET_JACKPOT: "Player hit a side-bet jackpot.",
    EventType.STREAK_WIN: "Player on a winning streak.",
    EventType.STREAK_LOSS: "Player on a losing streak.",
    EventType.IDLE: "Quiet moment at the table. Small talk.",
}


def _fmt_state_zh(s: GameState) -> str:
    parts: list[str] = []
    if s.player_name:
        parts.append(f"玩家:{s.player_name}")
    if s.player_total is not None:
        parts.append(f"玩家点数 {s.player_total}")
    if s.dealer_total is not None:
        parts.append(f"庄家点数 {s.dealer_total}")
    if s.dealer_up:
        parts.append(f"庄家明牌 {s.dealer_up}")
    if s.outcome:
        parts.append(f"结果 {s.outcome.value}")
    if s.bet is not None:
        parts.append(f"押注 {s.bet}")
    if s.net is not None:
        parts.append(f"净{'+' if s.net >= 0 else ''}{s.net}")
    if s.bankroll is not None:
        parts.append(f"剩余筹码 {s.bankroll}")
    if s.streak:
        parts.append(f"连{'赢' if s.streak > 0 else '输'} {abs(s.streak)} 把")
    if s.rare_hand:
        parts.append(f"特殊牌型:{s.rare_hand}")
    return "; ".join(parts) or "(无额外信息)"


def _fmt_state_en(s: GameState) -> str:
    parts: list[str] = []
    if s.player_name:
        parts.append(f"player={s.player_name}")
    if s.player_total is not None:
        parts.append(f"player_total={s.player_total}")
    if s.dealer_total is not None:
        parts.append(f"dealer_total={s.dealer_total}")
    if s.dealer_up:
        parts.append(f"dealer_up={s.dealer_up}")
    if s.outcome:
        parts.append(f"outcome={s.outcome.value}")
    if s.bet is not None:
        parts.append(f"bet={s.bet}")
    if s.net is not None:
        parts.append(f"net={'+' if s.net >= 0 else ''}{s.net}")
    if s.bankroll is not None:
        parts.append(f"bankroll={s.bankroll}")
    if s.streak:
        parts.append(f"streak={'+' if s.streak > 0 else ''}{s.streak}")
    if s.rare_hand:
        parts.append(f"rare_hand={s.rare_hand}")
    return ", ".join(parts) or "(no extra info)"


def build_messages(persona: Persona, event: EventType, state: GameState, language: Language) -> list[dict[str, str]]:
    # event.value is embedded verbatim — real models will treat it as context;
    # the mock LLM pattern-matches on it.
    if language == Language.ZH:
        sys = persona.system_prompt_zh
        hint = _EVENT_HINT_ZH.get(event, "说一句合适的话。")
        user = (
            f"[EVENT: {event.value}]\n"
            f"场景:{hint}\n"
            f"当前局面:{_fmt_state_zh(state)}\n"
            f"只用一句中文回复,不超过30字。"
        )
    else:
        sys = persona.system_prompt_en
        hint = _EVENT_HINT_EN.get(event, "Say something fitting.")
        user = (
            f"[EVENT: {event.value}]\n"
            f"Situation: {hint}\n"
            f"Context: {_fmt_state_en(state)}\n"
            f"Reply with exactly ONE short English sentence (under 15 words)."
        )
    return [
        {"role": "system", "content": sys},
        {"role": "user", "content": user},
    ]
