"""Protocol schema — shared by Python server and all clients (web/UE)."""
from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


# ---------- Enums ----------
class Language(str, Enum):
    ZH = "zh"
    EN = "en"


class EventType(str, Enum):
    SESSION_OPEN = "SESSION_OPEN"
    ROUND_START = "ROUND_START"
    CARD_DEALT = "CARD_DEALT"
    PLAYER_BUST = "PLAYER_BUST"
    NATURAL_BLACKJACK = "NATURAL_BLACKJACK"
    DEALER_UP_CARD = "DEALER_UP_CARD"
    PLAYER_DOUBLE = "PLAYER_DOUBLE"
    PLAYER_SPLIT = "PLAYER_SPLIT"
    PLAYER_SURRENDER = "PLAYER_SURRENDER"
    DEALER_BUST = "DEALER_BUST"
    ROUND_OVER = "ROUND_OVER"
    BIG_WIN = "BIG_WIN"
    BIG_LOSS = "BIG_LOSS"
    SIDEBET_JACKPOT = "SIDEBET_JACKPOT"
    STREAK_WIN = "STREAK_WIN"
    STREAK_LOSS = "STREAK_LOSS"
    IDLE = "IDLE"  # dealer small-talk between rounds


class Outcome(str, Enum):
    WIN = "win"
    LOSS = "loss"
    PUSH = "push"
    BLACKJACK = "blackjack"
    BUST = "bust"
    SURRENDER = "surrender"


class Tone(str, Enum):
    FRIENDLY = "friendly"
    TEASE = "tease"
    CONGRATS = "congrats"
    CONDOLE = "condole"
    DRAMATIC = "dramatic"
    NEUTRAL = "neutral"


# ---------- Nested types ----------
class GameState(BaseModel):
    player_total: int | None = None
    dealer_total: int | None = None
    dealer_up: str | None = None  # e.g. "A♠"
    outcome: Outcome | None = None
    bet: int | None = None
    net: int | None = None          # + for win, - for loss
    bankroll: int | None = None
    streak: int = 0                 # + winning streak, - losing streak
    rare_hand: str | None = None    # "5-card-21", "suited-trips", "QQ-hearts"
    player_name: str | None = None
    seat_index: int | None = None   # for multi-seat tables
    extra: dict[str, str | int | float | bool] = Field(default_factory=dict)


# ---------- Session / requests ----------
class OpenSessionRequest(BaseModel):
    language: Language = Language.ZH
    persona: str = "veteran"        # matches personas/<id>.json
    player_name: str | None = None
    seed: int | None = None         # for deterministic fallback rotation


class OpenSessionResponse(BaseModel):
    session_id: str
    language: Language
    persona: str
    server_version: str
    llm_ready: bool
    tts_ready: bool


class QuipRequest(BaseModel):
    event: EventType
    state: GameState = Field(default_factory=GameState)


class QuipResponse(BaseModel):
    text: str
    tone: Tone = Tone.NEUTRAL
    language: Language
    source: Literal["llm", "fallback"] = "fallback"
    latency_ms: int = 0


class HealthResponse(BaseModel):
    ok: bool
    version: str
    llm: dict[str, str | bool | int]
    tts: dict[str, str | bool]


# ---------- Persona ----------
class Persona(BaseModel):
    id: str
    name_zh: str
    name_en: str
    description_zh: str
    description_en: str
    system_prompt_zh: str
    system_prompt_en: str
    default_tone: Tone = Tone.NEUTRAL
    voice_id_zh: str | None = None   # CosyVoice speaker id
    voice_id_en: str | None = None
