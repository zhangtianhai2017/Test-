"""In-memory session manager — tracks per-table state and short-term chat history."""
from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

from .schema import Language, Persona


def _load_persona(persona_id: str) -> Persona:
    import json

    pkg = resources.files("dealer_ai.personas")
    path = pkg / f"{persona_id}.json"
    if not path.is_file():
        raise FileNotFoundError(f"persona not found: {persona_id}")
    data = json.loads(path.read_text(encoding="utf-8"))
    return Persona.model_validate(data)


def list_personas() -> list[Persona]:
    pkg = resources.files("dealer_ai.personas")
    out: list[Persona] = []
    for p in pkg.iterdir():  # type: ignore[attr-defined]
        if p.name.endswith(".json"):
            try:
                out.append(_load_persona(p.stem))
            except Exception:
                continue
    return out


@dataclass
class Session:
    id: str
    language: Language
    persona: Persona
    player_name: str | None
    created_at: float
    seed: int
    # rolling window of last N exchanges to avoid repetition
    recent_texts: list[str] = field(default_factory=list)
    # --- Dealer-state evolution (M12, Part B) ---
    rounds_played: int = 0
    # "fresh" | "seasoned" | "compromised"
    dealer_state: str = "fresh"
    # Set explicitly via POST /session/{id}/compromise; once true, overrides
    # the rounds-played thresholds and keeps dealer_state == "compromised".
    compromised_flag: bool = False


# Rounds-played thresholds for dealer_state evolution.
# 0..9 → "fresh", 10+ → "seasoned"; compromised overrides everything.
DEALER_SEASONED_AT_ROUNDS = 10


def _derive_dealer_state(rounds_played: int, compromised: bool) -> str:
    if compromised:
        return "compromised"
    if rounds_played >= DEALER_SEASONED_AT_ROUNDS:
        return "seasoned"
    return "fresh"


class SessionManager:
    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}

    def open(self, language: Language, persona_id: str, player_name: str | None, seed: int | None) -> Session:
        persona = _load_persona(persona_id)
        sid = secrets.token_urlsafe(8)
        s = Session(
            id=sid,
            language=language,
            persona=persona,
            player_name=player_name,
            created_at=time.time(),
            seed=seed or secrets.randbits(31),
        )
        self._sessions[sid] = s
        return s

    def get(self, sid: str) -> Session | None:
        return self._sessions.get(sid)

    def close(self, sid: str) -> None:
        self._sessions.pop(sid, None)

    def prune(self, older_than_s: float = 3600) -> int:
        now = time.time()
        stale = [sid for sid, s in self._sessions.items() if now - s.created_at > older_than_s]
        for sid in stale:
            del self._sessions[sid]
        return len(stale)

    # --- Dealer-state evolution helpers (M12, Part B) ---
    def tick_round(self, sid: str) -> Session:
        """Bump the round counter and evolve dealer_state accordingly.

        Raises KeyError if the session doesn't exist — callers (HTTP handlers)
        translate this to 404.
        """
        s = self._sessions.get(sid)
        if s is None:
            raise KeyError(sid)
        s.rounds_played += 1
        s.dealer_state = _derive_dealer_state(s.rounds_played, s.compromised_flag)
        return s

    def mark_compromised(self, sid: str) -> Session:
        """Story-mode hook: mark the dealer as compromised (sticky)."""
        s = self._sessions.get(sid)
        if s is None:
            raise KeyError(sid)
        s.compromised_flag = True
        s.dealer_state = "compromised"
        return s

    def dealer_state_of(self, sid: str) -> str:
        s = self._sessions.get(sid)
        if s is None:
            raise KeyError(sid)
        return s.dealer_state
