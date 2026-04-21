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


def test_pressure_hesitation_zh(server):
    r = httpx.post(f"{server}/session", json={"language": "zh", "persona": "veteran", "player_name": "张三"})
    sid = r.json()["session_id"]
    q = httpx.post(
        f"{server}/session/{sid}/quip",
        json={
            "event": "PRESSURE_HESITATION",
            "state": {"acting_seat_name": "张三", "player_total": 16},
        },
        timeout=5,
    ).json()
    assert q["language"] == "zh"
    assert q["source"] in ("llm", "fallback")
    assert len(q["text"]) > 0
    assert any("一" <= c <= "鿿" for c in q["text"]), f"no CJK: {q['text']!r}"


def test_bluff_called_en(server):
    r = httpx.post(f"{server}/session", json={"language": "en", "persona": "veteran"})
    sid = r.json()["session_id"]
    q = httpx.post(
        f"{server}/session/{sid}/quip",
        json={
            "event": "BLUFF_CALLED",
            "state": {"bluff_kind": "bet-size", "trust_in_player": 0.3},
        },
        timeout=5,
    ).json()
    assert q["language"] == "en"
    assert q["source"] in ("llm", "fallback")
    assert any(c.isalpha() and c.isascii() for c in q["text"])


def test_npc_hot_streak_zh(server):
    r = httpx.post(f"{server}/session", json={"language": "zh", "persona": "hostess"})
    sid = r.json()["session_id"]
    q = httpx.post(
        f"{server}/session/{sid}/quip",
        json={
            "event": "NPC_HOT_STREAK",
            "state": {"acting_seat_name": "李四", "streak": 5},
        },
        timeout=5,
    ).json()
    assert q["language"] == "zh"
    assert q["source"] in ("llm", "fallback")
    assert len(q["text"]) > 0


def test_new_gamestate_fields_serialize(server):
    """All new psychological-layer fields must be accepted by the request model."""
    r = httpx.post(f"{server}/session", json={"language": "en", "persona": "mystic"})
    sid = r.json()["session_id"]
    full_state = {
        "player_total": 14,
        "dealer_total": 10,
        "dealer_up": "10♠",
        "outcome": "loss",
        "bet": 100,
        "net": -100,
        "bankroll": 500,
        "streak": -2,
        "rare_hand": None,
        "player_name": "Alice",
        "seat_index": 2,
        "heat": 65,
        "morale": 0.42,
        "gesture": "nervous",
        "trust_in_player": 0.8,
        "dealer_state": "seasoned",
        "acting_seat_name": "Alice",
        "bluff_kind": "gesture",
    }
    resp = httpx.post(
        f"{server}/session/{sid}/quip",
        json={"event": "PRESSURE_TILT", "state": full_state},
        timeout=5,
    )
    assert resp.status_code == 200, resp.text
    q = resp.json()
    assert q["language"] == "en"
    assert len(q["text"]) > 0


def test_fallback_mode_all_new_events(monkeypatch, tmp_path):
    """Without a model, every new psychological event must still return a fallback quip."""
    env = os.environ.copy()
    env.pop("DEALER_AI_USE_MOCK", None)
    env["DEALER_AI_MODEL"] = "/nonexistent.gguf"
    env["DEALER_AI_TTS_ENABLED"] = "0"
    proc = subprocess.Popen(
        [sys.executable, "-m", "dealer_ai.main", "--host", "127.0.0.1", "--port", "18789", "--log-level", "warning"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        url = "http://127.0.0.1:18789"
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
        new_events = [
            "PRESSURE_HESITATION",
            "PRESSURE_HEAT",
            "PRESSURE_TILT",
            "BLUFF_CALLED",
            "BLUFF_BELIEVED",
            "DEALER_STATE_CHANGED",
            "TELL_SPOTTED",
            "NPC_BIG_LOSS",
            "NPC_HOT_STREAK",
        ]
        for ev in new_events:
            resp = httpx.post(
                f"{url}/session/{sid}/quip",
                json={"event": ev, "state": {"acting_seat_name": "张三"}},
                timeout=5,
            )
            assert resp.status_code == 200, f"{ev} -> {resp.status_code} {resp.text}"
            q = resp.json()
            assert q["source"] == "fallback", f"{ev} source={q['source']}"
            assert len(q["text"]) > 0, f"{ev} empty text"
    finally:
        proc.terminate()
        proc.wait(timeout=5)


def test_voices_endpoint(server):
    """GET /voices returns a JSON object with a voices list regardless of GPU availability."""
    r = httpx.get(f"{server}/voices")
    assert r.status_code == 200, r.text
    j = r.json()
    assert "voices" in j
    assert isinstance(j["voices"], list)
    assert "ready" in j and isinstance(j["ready"], bool)
    assert "status" in j and isinstance(j["status"], str)


def test_tts_endpoint_503_when_cpu(server):
    """POST /session/{sid}/tts should return 503 with a status payload in sandbox mode."""
    r = httpx.post(f"{server}/session", json={"language": "zh", "persona": "veteran"})
    sid = r.json()["session_id"]
    resp = httpx.post(
        f"{server}/session/{sid}/tts",
        json={"text": "你好,欢迎来到赌场"},
        timeout=5,
    )
    assert resp.status_code == 503, resp.text
    j = resp.json()
    assert j.get("ready") is False
    assert isinstance(j.get("status"), str) and len(j["status"]) > 0


def test_quip_plus_tts_endpoint_no_audio(server):
    """POST /session/{sid}/quip+tts returns quip text; audio fields are null without a GPU."""
    r = httpx.post(f"{server}/session", json={"language": "zh", "persona": "veteran"})
    sid = r.json()["session_id"]
    resp = httpx.post(
        f"{server}/session/{sid}/quip+tts",
        json={"event": "BIG_WIN", "state": {"net": 200}},
        timeout=5,
    )
    assert resp.status_code == 200, resp.text
    j = resp.json()
    assert j["language"] == "zh"
    assert len(j["text"]) > 0
    assert j["source"] in ("llm", "fallback")
    assert j["audio_wav_b64"] is None
    assert j["audio_sample_rate"] is None


def test_dealer_state_fresh_on_open(server):
    """A brand-new session exposes dealer_state=='fresh' and rounds_played==0."""
    r = httpx.post(f"{server}/session", json={"language": "en", "persona": "veteran"})
    sid = r.json()["session_id"]
    resp = httpx.get(f"{server}/session/{sid}/state")
    assert resp.status_code == 200, resp.text
    j = resp.json()
    assert j["dealer_state"] == "fresh"
    assert j["rounds_played"] == 0
    assert j["persona"] == "veteran"
    assert j["language"] == "en"


def test_dealer_state_tick_round_evolution(server):
    """Ticking 10 rounds transitions dealer_state from 'fresh' → 'seasoned'."""
    r = httpx.post(f"{server}/session", json={"language": "en", "persona": "veteran"})
    sid = r.json()["session_id"]
    # First nine ticks keep us in 'fresh' (0..9 rounds_played).
    for i in range(9):
        tick = httpx.post(f"{server}/session/{sid}/tick-round").json()
        assert tick["rounds_played"] == i + 1
        assert tick["dealer_state"] == "fresh"
    # Tenth tick crosses the threshold.
    tick = httpx.post(f"{server}/session/{sid}/tick-round").json()
    assert tick["rounds_played"] == 10
    assert tick["dealer_state"] == "seasoned"
    # Subsequent ticks stay 'seasoned'.
    tick = httpx.post(f"{server}/session/{sid}/tick-round").json()
    assert tick["dealer_state"] == "seasoned"


def test_dealer_state_compromise_endpoint(server):
    """POST /compromise flips to 'compromised' and sticks across further ticks."""
    r = httpx.post(f"{server}/session", json={"language": "en", "persona": "veteran"})
    sid = r.json()["session_id"]
    resp = httpx.post(f"{server}/session/{sid}/compromise")
    assert resp.status_code == 200, resp.text
    assert resp.json()["dealer_state"] == "compromised"
    # Further ticks do not revert the dealer state.
    for _ in range(3):
        tick = httpx.post(f"{server}/session/{sid}/tick-round").json()
        assert tick["dealer_state"] == "compromised"
    # GET /state confirms persistence.
    got = httpx.get(f"{server}/session/{sid}/state").json()
    assert got["dealer_state"] == "compromised"


def test_quip_injects_dealer_state(server):
    """After 10 ticks, a quip call succeeds and the session reports 'seasoned'."""
    r = httpx.post(f"{server}/session", json={"language": "en", "persona": "veteran"})
    sid = r.json()["session_id"]
    for _ in range(10):
        httpx.post(f"{server}/session/{sid}/tick-round")
    # The client does NOT pass dealer_state in state — the server should
    # inject the evolved value before invoking the prompt builder.
    resp = httpx.post(
        f"{server}/session/{sid}/quip",
        json={"event": "ROUND_OVER", "state": {"outcome": "win", "net": 50}},
        timeout=5,
    )
    assert resp.status_code == 200, resp.text
    q = resp.json()
    assert len(q["text"]) > 0
    # Internal state should report seasoned.
    got = httpx.get(f"{server}/session/{sid}/state").json()
    assert got["dealer_state"] == "seasoned"


def test_quip_plus_tts_schema_shape(server):
    """Response JSON must carry the full QuipWithAudioResponse field set."""
    r = httpx.post(f"{server}/session", json={"language": "en", "persona": "hostess"})
    sid = r.json()["session_id"]
    resp = httpx.post(
        f"{server}/session/{sid}/quip+tts",
        json={"event": "PLAYER_BUST", "state": {"player_total": 23}},
        timeout=5,
    )
    assert resp.status_code == 200, resp.text
    j = resp.json()
    for key in (
        "text",
        "tone",
        "language",
        "source",
        "latency_ms",
        "audio_wav_b64",
        "audio_sample_rate",
    ):
        assert key in j, f"missing key: {key}"


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
