"""End-to-end smoke test — replicates what the web/UE clients do."""
from __future__ import annotations

import os
import subprocess
import sys
import time

import httpx
import pytest


@pytest.fixture(scope="module")
def server():
    env = os.environ.copy()
    env["DEALER_AI_USE_MOCK"] = "1"
    env["DEALER_AI_TTS_ENABLED"] = "0"
    proc = subprocess.Popen(
        [sys.executable, "-m", "dealer_ai.main", "--host", "127.0.0.1", "--port", "18787", "--log-level", "warning"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    # wait until healthy
    url = "http://127.0.0.1:18787"
    for _ in range(40):
        try:
            r = httpx.get(f"{url}/health", timeout=0.5)
            if r.status_code == 200:
                break
        except Exception:
            pass
        time.sleep(0.2)
    else:
        proc.kill()
        raise RuntimeError("server did not start")
    yield url
    proc.terminate()
    proc.wait(timeout=5)


def test_health_and_personas(server):
    r = httpx.get(f"{server}/health")
    assert r.status_code == 200
    j = r.json()
    assert j["ok"] is True
    assert j["llm"]["ready"] is True  # mock backend
    r = httpx.get(f"{server}/personas")
    ids = [p["id"] for p in r.json()]
    assert {"veteran", "hostess", "mystic"}.issubset(set(ids))


def test_full_round_zh(server):
    r = httpx.post(f"{server}/session", json={"language": "zh", "persona": "veteran", "player_name": "张三"})
    sid = r.json()["session_id"]
    for event, state in [
        ("SESSION_OPEN", {"bankroll": 1000}),
        ("NATURAL_BLACKJACK", {"player_total": 21, "dealer_up": "10♠", "bet": 50, "net": 75}),
        ("PLAYER_BUST",       {"player_total": 23, "bet": 50}),
        ("DEALER_BUST",       {"player_total": 18, "dealer_total": 23, "bet": 50, "net": 50}),
        ("SIDEBET_JACKPOT",   {"rare_hand": "suited-trips", "net": 500}),
        ("BIG_WIN",           {"outcome": "win", "bet": 100, "net": 250, "streak": 3}),
        ("BIG_LOSS",          {"outcome": "loss", "bet": 100, "net": -200, "streak": -3}),
    ]:
        q = httpx.post(f"{server}/session/{sid}/quip", json={"event": event, "state": state}, timeout=5).json()
        assert q["language"] == "zh"
        assert q["source"] in ("llm", "fallback")
        # Chinese output must contain CJK characters.
        assert any("\u4e00" <= c <= "\u9fff" for c in q["text"]), f"no CJK in: {q['text']!r}"
        assert len(q["text"]) > 0


def test_full_round_en(server):
    r = httpx.post(f"{server}/session", json={"language": "en", "persona": "hostess"})
    sid = r.json()["session_id"]
    q = httpx.post(f"{server}/session/{sid}/quip", json={"event": "BIG_WIN", "state": {"net": 300}}, timeout=5).json()
    assert q["language"] == "en"
    # English output should be ASCII-ish.
    assert any(c.isalpha() and c.isascii() for c in q["text"])


def test_fallback_when_llm_disabled(monkeypatch, tmp_path):
    """If LLM can't load, server should still answer via fallback (without 500-ing)."""
    env = os.environ.copy()
    env.pop("DEALER_AI_USE_MOCK", None)
    env["DEALER_AI_MODEL"] = "/nonexistent.gguf"
    env["DEALER_AI_TTS_ENABLED"] = "0"
    proc = subprocess.Popen(
        [sys.executable, "-m", "dealer_ai.main", "--host", "127.0.0.1", "--port", "18788", "--log-level", "warning"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        url = "http://127.0.0.1:18788"
        for _ in range(40):
            try:
                r = httpx.get(f"{url}/health", timeout=0.5)
                if r.status_code == 200:
                    break
            except Exception:
                pass
            time.sleep(0.2)
        h = httpx.get(f"{url}/health").json()
        assert h["llm"]["ready"] is False
        r = httpx.post(f"{url}/session", json={"language": "zh", "persona": "veteran"})
        sid = r.json()["session_id"]
        q = httpx.post(f"{url}/session/{sid}/quip", json={"event": "PLAYER_BUST", "state": {}}).json()
        assert q["source"] == "fallback"
        assert len(q["text"]) > 0
    finally:
        proc.terminate()
        proc.wait(timeout=5)
