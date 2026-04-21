"""TTS provider — CosyVoice 2 adapter (GPU required for real-time).

Current stub just returns a disabled status. The real adapter will load
CosyVoice on GPU machines; on CPU-only machines (the sandbox, low-end laptops)
the server advertises tts_ready=false and clients fall back to browser
Web Speech API (web) or Windows SAPI (UE).

Cross-platform notes:
- CosyVoice is PyTorch-based -> Linux/Windows/macOS all supported by PyTorch.
- Needs a CUDA GPU for real-time (<1 s latency). CPU is 5-15 s/sentence.
- Model (~2 GB) loaded from $DEALER_AI_COSYVOICE_DIR, fallback /opt/cosyvoice.

# CosyVoice 2 on Windows:
# pip install --extra-index-url https://download.pytorch.org/whl/cu124 torch torchaudio
# pip install -r cosyvoice/requirements.txt  (from https://github.com/FunAudioLLM/CosyVoice)
# Set DEALER_AI_COSYVOICE_DIR to the downloaded CosyVoice-300M-Instruct model directory.
"""
from __future__ import annotations

import io
import logging
import os
from dataclasses import dataclass

log = logging.getLogger(__name__)


# CosyVoice 2 default output sample rate.
COSYVOICE_SAMPLE_RATE = 22050

# Voice ids shipped with the default personas. Used when the real backend
# hasn't been loaded so that /voices still returns something useful for
# clients that want to populate a dropdown in CPU-only mode.
_STUB_VOICE_IDS = [
    "cosyvoice_zh_male_mid",
    "cosyvoice_en_male_mid",
    "cosyvoice_zh_female_warm",
    "cosyvoice_en_female_warm",
    "cosyvoice_zh_male_deep",
    "cosyvoice_en_male_deep",
]


@dataclass
class TTSConfig:
    model_dir: str | None = None
    enabled: bool = True
    device: str = "auto"        # auto | cuda | cpu


class TTSProvider:
    def __init__(self, config: TTSConfig):
        self.config = config
        self._backend = None
        self._status = "not_loaded"
        self._device: str = "cpu"
        self._sample_rate: int = COSYVOICE_SAMPLE_RATE

    @property
    def ready(self) -> bool:
        return self._backend is not None

    @property
    def status(self) -> str:
        return self._status

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    def load(self) -> None:
        """Attempt to load CosyVoice. Soft-fails on missing deps / no GPU."""
        if not self.config.enabled:
            self._status = "disabled_by_config"
            return
        model_dir = self.config.model_dir or os.getenv("DEALER_AI_COSYVOICE_DIR")
        if not model_dir:
            self._status = "no_model_dir (set DEALER_AI_COSYVOICE_DIR)"
            return
        try:
            import torch  # type: ignore
        except ImportError as e:
            self._status = f"torch_not_installed: {e}"
            return

        try:
            has_cuda = torch.cuda.is_available()
        except Exception as e:  # pragma: no cover — defensive
            self._status = f"torch_cuda_probe_failed: {e}"
            return

        if self.config.device == "cuda" and not has_cuda:
            self._status = "cuda_requested_but_unavailable"
            return
        if self.config.device == "auto" and not has_cuda:
            # Stay on the stub — CosyVoice on CPU is unusable for real-time.
            self._status = "cpu_only_too_slow_for_realtime"
            return
        if self.config.device == "cpu":
            # Explicit CPU override — still refuse to load CosyVoice on CPU.
            self._status = "cpu_only_too_slow_for_realtime"
            return

        # GPU path — attempt the real load.
        try:
            from cosyvoice.cli.cosyvoice import CosyVoice2  # type: ignore
        except ImportError as e:
            self._status = f"cosyvoice_not_installed: {e}"
            return

        try:
            self._backend = CosyVoice2(model_dir)
            self._device = "cuda"
            self._status = "loaded (gpu)"
            log.info("TTS loaded: CosyVoice2 from %s on cuda", model_dir)
        except Exception as e:
            log.warning("TTS load failed: %s", e)
            self._backend = None
            self._status = f"load_failed: {e}"

    # ------------------------------------------------------------------
    # Synthesis
    # ------------------------------------------------------------------
    def synthesize_wav(
        self,
        text: str,
        voice_id: str | None,
        language: str,
    ) -> bytes | None:
        """Return WAV (16-bit PCM) bytes for *text*. None when backend not ready."""
        if self._backend is None:
            return None
        if not text or not text.strip():
            return None
        try:
            import numpy as np  # type: ignore
            import soundfile as sf  # type: ignore
            import torch  # type: ignore
        except ImportError as e:
            log.warning("TTS runtime deps missing: %s", e)
            return None

        lang = (language or "zh").lower()
        default_voice = (
            "cosyvoice_zh_male_mid" if lang.startswith("zh") else "cosyvoice_en_male_mid"
        )
        speaker = voice_id or default_voice

        try:
            chunks: list = []
            # CosyVoice 2 yields {"tts_speech": tensor[1, N]} dicts.
            for chunk in self._backend.inference_sft(text, speaker):
                piece = chunk.get("tts_speech") if isinstance(chunk, dict) else chunk
                if piece is None:
                    continue
                if hasattr(piece, "detach"):
                    piece = piece.detach().to("cpu")
                chunks.append(piece)
            if not chunks:
                return None
            audio = torch.cat(chunks, dim=-1)
            # Shape -> (N,) mono on CPU float32 in [-1, 1].
            audio_np = audio.squeeze().cpu().numpy()
            # Clip and quantise to 16-bit PCM.
            audio_np = np.clip(audio_np, -1.0, 1.0)
            pcm16 = (audio_np * 32767.0).astype(np.int16)
            buf = io.BytesIO()
            sf.write(buf, pcm16, self._sample_rate, format="WAV", subtype="PCM_16")
            return buf.getvalue()
        except Exception as e:
            log.warning("TTS synthesis failed: %s", e)
            return None

    # ------------------------------------------------------------------
    # Voice discovery
    # ------------------------------------------------------------------
    def list_voices(self) -> list[str]:
        """List available speaker ids. Falls back to the shipped persona set."""
        backend = self._backend
        if backend is not None:
            # CosyVoice 2 exposes ``list_available_spks()`` in the upstream CLI.
            for attr in ("list_available_spks", "list_avaliable_spks"):  # tolerate typo in upstream
                fn = getattr(backend, attr, None)
                if callable(fn):
                    try:
                        voices = list(fn())
                        if voices:
                            return voices
                    except Exception as e:  # pragma: no cover — defensive
                        log.warning("list_voices backend call failed: %s", e)
                        break
        return list(_STUB_VOICE_IDS)
