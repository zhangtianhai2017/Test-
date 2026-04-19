"""Offline fallback quip provider — used when LLM is unavailable or as canned backup."""
from __future__ import annotations

import hashlib
import json
from importlib import resources
from pathlib import Path

from ..schema import EventType, GameState, Language, QuipResponse, Tone


_TONE_BY_EVENT: dict[EventType, Tone] = {
    EventType.NATURAL_BLACKJACK: Tone.DRAMATIC,
    EventType.SIDEBET_JACKPOT: Tone.DRAMATIC,
    EventType.BIG_WIN: Tone.CONGRATS,
    EventType.DEALER_BUST: Tone.CONGRATS,
    EventType.STREAK_WIN: Tone.CONGRATS,
    EventType.PLAYER_BUST: Tone.CONDOLE,
    EventType.BIG_LOSS: Tone.CONDOLE,
    EventType.STREAK_LOSS: Tone.CONDOLE,
    EventType.PLAYER_SURRENDER: Tone.FRIENDLY,
    EventType.PLAYER_DOUBLE: Tone.TEASE,
    EventType.PLAYER_SPLIT: Tone.TEASE,
}


class FallbackProvider:
    def __init__(self) -> None:
        self._banks: dict[Language, dict[str, list[str]]] = {
            Language.ZH: self._load("quips_zh.json"),
            Language.EN: self._load("quips_en.json"),
        }

    @staticmethod
    def _load(name: str) -> dict[str, list[str]]:
        pkg = resources.files("dealer_ai.fallback")
        return json.loads((pkg / name).read_text(encoding="utf-8"))

    def quip(self, event: EventType, state: GameState, language: Language, seed: int = 0) -> QuipResponse:
        bank = self._banks[language]
        lines = bank.get(event.value) or bank.get(EventType.IDLE.value, ["..."])
        # Deterministic pick: hash state+event+seed so same situation gives same line,
        # but different situations rotate through the bank.
        key = f"{event.value}|{state.outcome}|{state.net}|{state.streak}|{seed}"
        idx = int(hashlib.md5(key.encode()).hexdigest()[:8], 16) % len(lines)
        text = lines[idx]
        return QuipResponse(
            text=text,
            tone=_TONE_BY_EVENT.get(event, Tone.NEUTRAL),
            language=language,
            source="fallback",
            latency_ms=0,
        )
