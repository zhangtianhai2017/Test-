# AGENT — dealer-ai module

You are the maintainer of the `packages/dealer-ai` Python service.

## Purpose

Headless HTTP service, Linux/Windows cross-platform, that:

1. Receives game events (NATURAL_BLACKJACK / PLAYER_BUST / HIGH_HEAT /
   PLAYER_GESTURE / ...) from any client (UE plugin primary; web UIs frozen
   but compatible).
2. Generates one-line **dealer quips** in the current session's language
   (zh or en) using a small local LLM (Qwen 2.5 family, GGUF, llama.cpp).
3. Optionally synthesizes voice via **CosyVoice 2** when a GPU is present.
4. Falls back to canned responses when LLM is down, so the service
   NEVER 500s due to LLM issues.

## Scope — what you own

- `packages/dealer-ai/` — everything under this directory
- Shipped personas (`src/dealer_ai/personas/*.json`)
- Shipped fallback quip banks (`src/dealer_ai/fallback/*.json`)
- Integration tests that run a live subprocess

## Scope — what you do NOT own

- Any game logic (rules, NPC decisions, scoring — all in `engine` / `ai-npc`)
- How the UE plugin consumes the HTTP API (that's ue-plugin's problem)
- UI

## Key invariants

1. **OpenAI-compatible protocol** where possible — lets us swap backends.
2. **Cross-platform**: every code path that works on Linux must work on
   Windows. No `os.setsid`, no `signal.SIGKILL`, no Unix-only fs paths.
3. **Model file never committed** — GGUF lives in `packages/dealer-ai/models/`
   (gitignored) and is downloaded via `scripts/download_model.py`.
4. **Fallback mode is always available** — `DEALER_AI_USE_MOCK=1` for
   dev without a model file. Production fallback is the JSON quip bank.

## Current API surface (contract)

```
GET  /health                      HealthResponse
GET  /personas                    list[Persona]
POST /session                     OpenSessionRequest → OpenSessionResponse
POST /session/{id}/quip           QuipRequest  → QuipResponse
POST /session/{id}/tts            (future: TTSRequest → audio stream)
DELETE /session/{id}              close session
```

Pydantic schemas in `src/dealer_ai/schema.py` — treat that file as the
canonical contract. Never break field names once a client depends on them.

## Planned extensions (upcoming milestones)

- **M7**: new event types for heat / bluff / morale / dealer-state;
  enriched `state` payload with seat-index-aware info
- **M8**: CosyVoice 2 integration — GPU-only, falls back cleanly on
  CPU-only hosts (returns `tts_ready=false`, clients use Windows SAPI /
  Web Speech API)

## Personas

Three ship today (`veteran`, `hostess`, `mystic`). When adding more:
- Add `<id>.json` with zh + en system prompts and voice ids
- Update README.md persona table
- No code change needed (auto-discovered by `list_personas()`)

## Tests

```bash
cd packages/dealer-ai
pytest -v
```

Integration tests spawn a real subprocess. Mock-mode LLM is enabled by
setting `DEALER_AI_USE_MOCK=1` — this is how CI without GPU still passes.

## Packaging for Windows

See `README.md` Windows section. Key points:
- PyInstaller `--onefile` with `--collect-all llama_cpp`
- Register via NSSM as Windows Service
- Installer must include a default GGUF model or download on first run

## Escalation triggers

- Any change to `schema.py` that renames or removes a field — UE client
  breaks. Must go through PM → DECISIONS.md.
- A new CosyVoice voice id that isn't in the shipped model.
- Noticeable Windows behavior divergence (file paths, signal handling).

## Known portability footguns

- `os.fork()` doesn't exist on Windows — do not use (uvicorn handles).
- `nohup` is Unix — Windows launchers use `Start-Process`.
- Paths with backslashes in env vars — always `Path(...)` normalize.
- CosyVoice requires specific PyTorch + CUDA matching — pin in
  `pyproject.toml` `tts` extras.
