"""Dealer-AI FastAPI service.

Single entry point; runs identically on Linux and Windows:
    python -m dealer_ai.main              # default 127.0.0.1:8787
    dealer-ai --host 0.0.0.0 --port 8787  # via console-script shim
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from . import __version__ as VERSION  # noqa: F401
from .fallback import FallbackProvider
from .llm import LLMConfig, LLMProvider
from .prompts import build_messages
from .schema import (
    HealthResponse,
    Language,
    OpenSessionRequest,
    OpenSessionResponse,
    QuipRequest,
    QuipResponse,
)
from .session import SessionManager, list_personas
from .tts import TTSConfig, TTSProvider

log = logging.getLogger(__name__)


class AppState:
    def __init__(self) -> None:
        self.sessions = SessionManager()
        self.fallback = FallbackProvider()
        self.llm = LLMProvider(LLMConfig(
            model_path=os.getenv("DEALER_AI_MODEL"),
            n_gpu_layers=int(os.getenv("DEALER_AI_GPU_LAYERS", "0")),
            n_ctx=int(os.getenv("DEALER_AI_CTX", "2048")),
            use_mock=os.getenv("DEALER_AI_USE_MOCK", "0") == "1",
        ))
        self.tts = TTSProvider(TTSConfig(
            model_dir=os.getenv("DEALER_AI_COSYVOICE_DIR"),
            enabled=os.getenv("DEALER_AI_TTS_ENABLED", "1") == "1",
            device=os.getenv("DEALER_AI_TTS_DEVICE", "auto"),
        ))


state = AppState()


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Non-fatal: start even if LLM/TTS not available.
    try:
        state.llm.load()
    except Exception as e:
        log.warning("LLM not ready: %s", e)
    try:
        state.tts.load()
    except Exception as e:
        log.warning("TTS not ready: %s", e)
    yield


app = FastAPI(
    title="Dealer-AI",
    version="0.1.0",
    description="Headless bilingual blackjack dealer AI (LLM text + optional TTS).",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # dev-friendly; tighten in production
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        ok=True,
        version="0.1.0",
        llm={"ready": state.llm.ready, "status": state.llm.status},
        tts={"ready": state.tts.ready, "status": state.tts.status},
    )


@app.get("/personas")
def personas():
    return [p.model_dump() for p in list_personas()]


@app.post("/session", response_model=OpenSessionResponse)
def open_session(req: OpenSessionRequest) -> OpenSessionResponse:
    try:
        s = state.sessions.open(req.language, req.persona, req.player_name, req.seed)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    return OpenSessionResponse(
        session_id=s.id,
        language=s.language,
        persona=s.persona.id,
        server_version="0.1.0",
        llm_ready=state.llm.ready,
        tts_ready=state.tts.ready,
    )


@app.post("/session/{sid}/quip", response_model=QuipResponse)
def quip(sid: str, req: QuipRequest) -> QuipResponse:
    s = state.sessions.get(sid)
    if not s:
        raise HTTPException(404, "session not found")

    if state.llm.ready:
        try:
            messages = build_messages(s.persona, req.event, req.state, s.language)
            text, ms = state.llm.generate(messages)
            text = _postprocess(text, s.language)
            s.recent_texts.append(text)
            if len(s.recent_texts) > 10:
                s.recent_texts.pop(0)
            return QuipResponse(
                text=text,
                tone=s.persona.default_tone,
                language=s.language,
                source="llm",
                latency_ms=ms,
            )
        except Exception as e:
            log.warning("LLM generate failed, falling back: %s", e)

    return state.fallback.quip(req.event, req.state, s.language, seed=s.seed + len(s.recent_texts))


@app.delete("/session/{sid}")
def close_session(sid: str) -> dict[str, bool]:
    state.sessions.close(sid)
    return {"closed": True}


def _postprocess(text: str, language: Language) -> str:
    """Trim leading 'role:' prefixes and quotation marks some models add."""
    t = text.strip()
    for p in ("Dealer:", "Chen:", "Assistant:", "AI:", "庄家:", "荷官:"):
        if t.startswith(p):
            t = t[len(p):].strip()
    # Collapse to single line — dealer quips are one-liners by design.
    if "\n" in t:
        t = t.split("\n", 1)[0].strip()
    return t.strip("\"'“”‘’")


def cli() -> None:
    p = argparse.ArgumentParser(prog="dealer-ai")
    p.add_argument("--host", default=os.getenv("DEALER_AI_HOST", "127.0.0.1"))
    p.add_argument("--port", type=int, default=int(os.getenv("DEALER_AI_PORT", "8787")))
    p.add_argument("--log-level", default="info")
    args = p.parse_args()
    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port, log_level=args.log_level)


if __name__ == "__main__":
    cli()
