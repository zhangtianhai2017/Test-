"""LLM provider — llama.cpp via llama-cpp-python (pure Python, cross-platform).

Cross-platform notes:
- llama-cpp-python ships prebuilt wheels for Windows/macOS/Linux x86_64 and arm64.
- CPU only by default. For GPU on Windows/Linux install the CUDA-built wheel:
    pip install --upgrade --force-reinstall \\
      --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu124/ \\
      llama-cpp-python
  The Python code below is identical; only the wheel changes.
- Model files (.gguf) are loaded from dealer_ai/../models/ or $DEALER_AI_MODEL env var.

Performance targets (rough, Q4_K_M):
  Qwen2.5-0.5B-Instruct : CPU ~40 tok/s, single sentence < 1 s.
  Qwen2.5-1.5B-Instruct : CPU ~20 tok/s, single sentence ~1 s.
  Qwen2.5-3B-Instruct   : CPU ~8 tok/s,  single sentence ~2 s. GPU (RTX 3060) ~60 tok/s.
  Qwen2.5-7B-Instruct   : GPU-only in practice, ~40 tok/s on RTX 3060.
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

try:
    from llama_cpp import Llama  # type: ignore
    _LLAMA_IMPORT_OK = True
    _IMPORT_ERR: str | None = None
except Exception as e:  # pragma: no cover - env dependent
    Llama = None  # type: ignore
    _LLAMA_IMPORT_OK = False
    _IMPORT_ERR = str(e)


# ---------------- Mock backend ----------------
# Lets us validate the whole pipeline on machines without a GGUF model
# (e.g. sandbox with no HF access). Enable with DEALER_AI_USE_MOCK=1.
_MOCK_RESPONSES_ZH = {
    "NATURAL_BLACKJACK": ["开局 A + 10,这手漂亮。", "天胡了,今晚您开光了。"],
    "PLAYER_BUST":       ["哎呀,就差一点。", "21 的门槛,就差那么一点点。"],
    "DEALER_BUST":       ["这把算我背,恭喜您。", "我爆了,拿去。"],
    "BIG_WIN":           ["连赢好几把,手感起飞。", "这把是高光,别急着全押回去。"],
    "BIG_LOSS":          ["输大了,喝口水缓一缓。", "运气流转,下一把找回来。"],
    "PLAYER_DOUBLE":     ["敢翻倍,有气魄。", "加倍了,就看这张牌了。"],
    "PLAYER_SPLIT":      ["分牌分得干脆。", "拆开打,两手都有戏。"],
    "SIDEBET_JACKPOT":   ["边注爆奖了,这把今晚留名。", "这运气,我服。"],
    "ROUND_OVER":        ["结了,下一把?", "这把到这儿,续还是歇?"],
    "PRESSURE_HESITATION": ["想好了吗,别让牌凉了。", "您这犹豫得,我都替您急。"],
    "PRESSURE_HEAT":       ["楼上眼线多,动作规矩点。", "风声紧,收着打。"],
    "PRESSURE_TILT":       ["深呼吸,别跟钱较劲。", "上头归上头,注别乱加。"],
    "BLUFF_CALLED":        ["眼神露馅了,别装。", "这手虚的,我看穿了。"],
    "BLUFF_BELIEVED":      ["这演技,全桌都信了。", "唬住了,漂亮。"],
    "DEALER_STATE_CHANGED": ["今天我的状态,不一样了。", "规矩是规矩,人是会变的。"],
    "TELL_SPOTTED":        ["您眼睛毒,这都看出来。", "行家一眼看穿。"],
    "NPC_BIG_LOSS":        ["这位伤得重,缓缓。", "牌桌无情,再来过。"],
    "NPC_HOT_STREAK":      ["这位今晚手感烫手。", "手气在他那儿,别眼红。"],
    "_default":          ["局面挺稳,您慢慢来。", "嗯,有意思。"],
}
_MOCK_RESPONSES_EN = {
    "NATURAL_BLACKJACK": ["Ace and a ten — textbook.", "Blackjack straight off the deal."],
    "PLAYER_BUST":       ["One card too far.", "Twenty-one's a cruel line."],
    "DEALER_BUST":       ["Dealer busts — on you.", "Over twenty-one. Pay the line."],
    "BIG_WIN":           ["Running hot tonight.", "Big stack — watch the pull."],
    "BIG_LOSS":          ["Rough hand. Shake it off.", "Deck's cold right now."],
    "PLAYER_DOUBLE":     ["Doubling down — bold.", "Big play."],
    "PLAYER_SPLIT":      ["Split 'em.", "Two hands now."],
    "SIDEBET_JACKPOT":   ["Side bet hit big — nice.", "That payout's one to remember."],
    "ROUND_OVER":        ["Hand's done. Another?", "That's the round."],
    "PRESSURE_HESITATION": ["Clock's ticking, your call.", "Make your play."],
    "PRESSURE_HEAT":       ["Pit's watching, keep it clean.", "Eyes on us, by the book."],
    "PRESSURE_TILT":       ["Breathe, don't chase it.", "Steady hands, steady bets."],
    "BLUFF_CALLED":        ["Nice try, saw that coming.", "Not buying it."],
    "BLUFF_BELIEVED":      ["The whole table bought it.", "That was a clean act."],
    "DEALER_STATE_CHANGED": ["Something's different tonight.", "Call it a change of heart."],
    "TELL_SPOTTED":        ["Sharp eyes, you caught it.", "Nice read."],
    "NPC_BIG_LOSS":        ["Rough hand for them.", "That one stung."],
    "NPC_HOT_STREAK":      ["Running hot over there.", "Someone's on fire."],
    "_default":          ["Table's steady.", "Take your time."],
}
# --------------------------------------------------


@dataclass
class LLMConfig:
    model_path: str | None = None
    n_ctx: int = 2048
    n_threads: int = 0           # 0 = auto
    n_gpu_layers: int = 0        # 0 = CPU-only; set >0 on machines with GPU wheel
    temperature: float = 0.8
    top_p: float = 0.9
    max_tokens: int = 80
    repeat_penalty: float = 1.15
    stop: list[str] = field(default_factory=lambda: ["\n\n", "</s>"])
    use_mock: bool = False       # when true, skip llama.cpp and use canned responses


class LLMProvider:
    """Thin wrapper — lazy-loads the model on first use.

    Returns (text, latency_ms) or raises RuntimeError if unavailable.
    With use_mock=True, returns canned event-appropriate responses for
    pipeline testing on machines without a model file."""

    def __init__(self, config: LLMConfig):
        self.config = config
        self._llm: "Llama | None" = None
        self._mock: bool = config.use_mock
        self._status: str = "not_loaded"

    @property
    def ready(self) -> bool:
        return self._mock or self._llm is not None

    @property
    def status(self) -> str:
        return self._status

    def load(self) -> None:
        if self._mock:
            self._status = "mock_loaded"
            log.info("LLM: using MOCK backend (canned responses)")
            return
        if not _LLAMA_IMPORT_OK:
            self._status = f"import_failed: {_IMPORT_ERR}"
            raise RuntimeError(self._status)
        path = self.config.model_path or os.getenv("DEALER_AI_MODEL")
        if not path:
            self._status = "no_model_path"
            raise RuntimeError("DEALER_AI_MODEL not set and no model_path configured")
        p = Path(path)
        if not p.exists():
            self._status = f"model_not_found: {p}"
            raise RuntimeError(self._status)
        log.info("Loading LLM from %s (n_gpu_layers=%d)", p, self.config.n_gpu_layers)
        t0 = time.time()
        self._llm = Llama(
            model_path=str(p),
            n_ctx=self.config.n_ctx,
            n_threads=self.config.n_threads or None,
            n_gpu_layers=self.config.n_gpu_layers,
            verbose=False,
        )
        self._status = "loaded"
        log.info("LLM loaded in %.1f s", time.time() - t0)

    def generate(self, messages: list[dict[str, str]]) -> tuple[str, int]:
        """messages = OpenAI chat format [{'role': 'system'|'user'|'assistant', 'content': '...'}]"""
        if self._mock:
            return self._mock_generate(messages)
        if self._llm is None:
            raise RuntimeError("LLM not loaded")
        t0 = time.time()
        out = self._llm.create_chat_completion(
            messages=messages,  # type: ignore[arg-type]
            temperature=self.config.temperature,
            top_p=self.config.top_p,
            max_tokens=self.config.max_tokens,
            repeat_penalty=self.config.repeat_penalty,
            stop=self.config.stop,
        )
        text = (out["choices"][0]["message"]["content"] or "").strip()
        return text, int((time.time() - t0) * 1000)

    def _mock_generate(self, messages: list[dict[str, str]]) -> tuple[str, int]:
        """Heuristic mock: sniff event + language from the user prompt."""
        import hashlib
        import random

        user = next((m["content"] for m in messages if m["role"] == "user"), "")
        system = next((m["content"] for m in messages if m["role"] == "system"), "")
        lang_is_en = "English" in system or "English" in user
        bank = _MOCK_RESPONSES_EN if lang_is_en else _MOCK_RESPONSES_ZH
        # Prefer the longest matching key so e.g. NPC_BIG_LOSS wins over BIG_LOSS.
        matches = [k for k in bank if k != "_default" and k in user]
        event_key = max(matches, key=len) if matches else "_default"
        lines = bank[event_key]
        idx = int(hashlib.md5(user.encode()).hexdigest()[:8], 16) % len(lines)
        # simulate tiny latency so front-end can see source=llm and a ms value
        time.sleep(0.05 + random.random() * 0.1)
        return lines[idx], 120
