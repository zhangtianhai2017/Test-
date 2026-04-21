# dealer-ai — STATE

Updated: 2026-04-21 (PM)

## Files
- `src/dealer_ai/` — 11 files, ~700 lines Python
- `tests/test_integration.py` — 4 live-subprocess tests, all green
- `scripts/run.sh`, `scripts/run.ps1`, `scripts/download_model.py`

## Recent work
- FastAPI service scaffolded with /health /personas /session /quip
- Mock LLM backend for sandbox dev (sandbox has no HF access)
- 3 personas: veteran / hostess / mystic, zh+en
- Fallback quip bank bilingual, deterministic rotation

## Known unfinished / upcoming
- M7: extend event types (heat / bluff / morale / dealer-state / tell)
- M8: CosyVoice 2 TTS (GPU-gated)
- M9: real-time SSE/WS streaming for lower perceived latency
- PyInstaller Windows build — untested on target OS

## Open issues on this module
None.

## External dependencies to watch
- `llama-cpp-python` (pip wheel versions, CUDA variants)
- CosyVoice 2 checkpoint (~2 GB, licensing TBD)
- Qwen 2.5 GGUF family (Apache 2.0, bundled OK)
