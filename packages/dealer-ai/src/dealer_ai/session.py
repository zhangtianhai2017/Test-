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
