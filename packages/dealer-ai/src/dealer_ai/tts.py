"""TTS provider — CosyVoice 2 adapter (GPU required for real-time).

Current stub just returns a disabled status. The real adapter will load
CosyVoice on GPU machines; on CPU-only machines (the sandbox, low-end laptops)
the server advertises tts_ready=false and clients fall back to browser
Web Speech API (web) or Windows SAPI (UE).

Cross-platform notes:
- CosyVoice is PyTorch-based → Linux/Windows/macOS all supported by PyTorch.
- Needs a CUDA GPU for real-time (<1 s latency). CPU is 5-15 s/sentence.
- Model (~2 GB) loaded from $DEALER_AI_COSYVOICE_DIR, fallback /opt/cosyvoice.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass

log = logging.getLogger(__name__)


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

    @property
    def ready(self) -> bool:
        return self._backend is not None

    @property
    def status(self) -> str:
        return self._status

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

            has_cuda = torch.cuda.is_available()
            if self.config.device == "cuda" and not has_cuda:
                self._status = "cuda_requested_but_unavailable"
                return
            if self.config.device == "auto" and not has_cuda:
                self._status = "cpu_only_too_slow_for_realtime"
                return
            # Real CosyVoice load goes here — left as TODO until GPU machine.
            # from cosyvoice.cli.cosyvoice import CosyVoice
            # self._backend = CosyVoice(model_dir)
            self._status = "stub_not_wired"
            log.info("TTS stub: would load CosyVoice from %s on %s", model_dir, "cuda" if has_cuda else "cpu")
        except ImportError as e:
            self._status = f"import_failed: {e}"

    def synthesize_wav(self, text: str, voice_id: str | None, language: str) -> bytes | None:
        """Return 16-bit PCM WAV bytes. None if TTS not ready."""
        if self._backend is None:
            return None
        # TODO: call CosyVoice inference, encode WAV, return bytes.
        return None
