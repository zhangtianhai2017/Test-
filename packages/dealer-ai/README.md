# dealer-ai

Headless bilingual AI service for the blackjack dealer. Runs on Linux (dev) and
Windows (target), exposes a simple HTTP API that all clients (web 2D, web 3D,
UE plugin) consume identically.

## What it does

| Endpoint | Purpose |
|---|---|
| `GET  /health` | liveness + `{llm_ready, tts_ready}` for status pill in clients |
| `GET  /personas` | list shipped dealer personas (id, name, description) |
| `POST /session` | open a table session: pick `language` (`zh`/`en`) + `persona` |
| `POST /session/{id}/quip` | input: game event + state → output: one-liner dealer quip |
| `DELETE /session/{id}` | close session |

All responses include `source` (`"llm"` or `"fallback"`) and `latency_ms`.
Clients can safely ignore the service — fallback quips still come from the
server if it's running, and clients can hard-code their own pre-written
fallbacks if the server is unreachable.

## Run it

```bash
# Install (Linux/WSL; Windows identical with py -3.11 -m pip ...)
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e .

# 1. Fallback-only mode — no model needed, deterministic canned quips.
python -m dealer_ai.main

# 2. Mock LLM mode — simulates latency + source="llm", no model file needed.
DEALER_AI_USE_MOCK=1 python -m dealer_ai.main

# 3. Real Qwen on CPU — download a GGUF first (on a machine with HF access):
huggingface-cli download Qwen/Qwen2.5-1.5B-Instruct-GGUF qwen2.5-1.5b-instruct-q4_k_m.gguf \
    --local-dir packages/dealer-ai/models
DEALER_AI_MODEL=./models/qwen2.5-1.5b-instruct-q4_k_m.gguf python -m dealer_ai.main

# 4. Real Qwen on GPU (Windows/Linux, CUDA):
pip install --upgrade --force-reinstall \
  --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu124/ llama-cpp-python
DEALER_AI_MODEL=./models/qwen2.5-7b-instruct-q4_k_m.gguf \
DEALER_AI_GPU_LAYERS=999 python -m dealer_ai.main
```

Test it:

```bash
curl http://127.0.0.1:8787/health
curl -X POST http://127.0.0.1:8787/session \
     -H 'Content-Type: application/json' \
     -d '{"language":"zh","persona":"veteran"}'
# → {"session_id": "abc123...", ...}
curl -X POST http://127.0.0.1:8787/session/abc123.../quip \
     -H 'Content-Type: application/json' \
     -d '{"event":"NATURAL_BLACKJACK","state":{"player_total":21,"bet":50,"net":75}}'
```

## Environment variables

| Var | Default | Notes |
|---|---|---|
| `DEALER_AI_HOST` | `127.0.0.1` | bind host |
| `DEALER_AI_PORT` | `8787` | bind port |
| `DEALER_AI_MODEL` | *(unset)* | absolute path to a `.gguf` file |
| `DEALER_AI_GPU_LAYERS` | `0` | `0` = CPU only; `999` = offload all layers to GPU |
| `DEALER_AI_CTX` | `2048` | context window |
| `DEALER_AI_USE_MOCK` | `0` | `1` = canned quips (for tests/dev without a model) |
| `DEALER_AI_TTS_ENABLED` | `1` | set `0` to disable TTS probe |
| `DEALER_AI_COSYVOICE_DIR` | *(unset)* | path to CosyVoice 2 model dir |
| `DEALER_AI_TTS_DEVICE` | `auto` | `auto` / `cuda` / `cpu` |

## Personas

| id | zh name | en name | Voice target |
|---|---|---|---|
| `veteran` | 老江湖 陈师傅 | The Veteran (Chen) | male mid-range, dry |
| `hostess` | 热情阿姨 王姐 | The Hostess (Auntie Wang) | female warm |
| `mystic`  | 神秘赌神 | The Mystic | male deep, slow |

Add your own by dropping a `src/dealer_ai/personas/<id>.json` — see `veteran.json`.

## Windows port notes

The whole service is pure Python. To port to Windows:

```powershell
py -3.11 -m venv .venv
.venv\Scripts\activate
pip install -e .
# GPU wheel:
pip install --upgrade --force-reinstall `
  --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu124/ `
  llama-cpp-python

# Download model once:
huggingface-cli download Qwen/Qwen2.5-3B-Instruct-GGUF `
    qwen2.5-3b-instruct-q4_k_m.gguf --local-dir .\models

# Run:
$env:DEALER_AI_MODEL = ".\models\qwen2.5-3b-instruct-q4_k_m.gguf"
$env:DEALER_AI_GPU_LAYERS = "999"
python -m dealer_ai.main
```

Package as a single `.exe`:

```powershell
pip install pyinstaller
pyinstaller --onefile --name dealer-ai `
    --add-data "src\dealer_ai\personas;dealer_ai\personas" `
    --add-data "src\dealer_ai\fallback;dealer_ai\fallback" `
    --collect-all llama_cpp `
    -m dealer_ai.main
# => dist\dealer-ai.exe
```

Install as a Windows Service (optional, using NSSM):

```powershell
choco install nssm
nssm install DealerAI "C:\Program Files\dealer-ai\dealer-ai.exe"
nssm set DealerAI AppEnvironmentExtra DEALER_AI_MODEL=C:\ProgramData\dealer-ai\qwen.gguf
nssm start DealerAI
```

## Testing

```bash
pip install -e '.[dev]'
pytest -v
```

4 integration tests run a live server in a subprocess and verify the full
request/response flow, in both Chinese and English, with and without the LLM
loaded.
