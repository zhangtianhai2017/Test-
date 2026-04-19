# Deployment Brief — Dealer-AI Service (for an autonomous coding agent)

> **Read this entire document before running any command.** You are deploying
> the dealer-AI service from a public GitHub repo onto the **local machine**
> the user is sitting at. Validate every step. If a step fails, do **not**
> ask the user — diagnose, retry, or fall back as instructed in the
> Troubleshooting section, then continue.

---

## 1. Mission

Bring up a local HTTP service called **dealer-ai** that:

- Serves an OpenAI-compatible blackjack-dealer chat API on `http://127.0.0.1:8787`.
- Generates one-line dealer quips (Chinese or English) in response to game
  events such as `NATURAL_BLACKJACK`, `PLAYER_BUST`, `BIG_WIN`.
- Uses a local **Qwen 2.5 GGUF** model via `llama.cpp`. No cloud calls. No
  API keys.
- Stays up after you exit (run as a background process or service).

Then sanity-check it against the bundled web client.

You are **done** when the **Final Success Checklist** at the bottom of this
document passes in full and you have produced the **Final Report** in the
specified format.

---

## 2. Source repository

| Field | Value |
|---|---|
| Repo | `https://github.com/zhangtianhai2017/test-.git` |
| Branch | `claude/blackjack-game-architecture-k3Yf6` |
| Service code path | `packages/dealer-ai/` |
| Web client path  | `packages/ui-web/` |
| Service docs     | `packages/dealer-ai/README.md` (cross-reference, not authoritative — **this** doc is authoritative for deployment) |

If the repository or branch above is unreachable (e.g. 404, auth required),
abort and report the failure. Do not invent alternate URLs.

---

## 3. Environment detection (run first, save output)

Execute these commands and **record the outputs** — you will need them in
your Final Report and to make decisions in §6.

```bash
# OS
uname -s -r 2>/dev/null || ver
# Python — must be 3.10, 3.11, or 3.12. NOT 3.13 (llama-cpp-python wheels lag).
python3 --version 2>/dev/null || python --version
# RAM (GB)
free -h 2>/dev/null | head -2 || systeminfo | findstr /C:"Total Physical Memory"
# Disk free at the install location
df -h . 2>/dev/null | tail -1 || dir
# GPU? (any of these working = GPU available)
nvidia-smi 2>/dev/null | head -15 || echo "NO_NVIDIA_SMI"
# Network reach to GitHub + HuggingFace (model host)
curl -sIL -o /dev/null -w "github=%{http_code}\n" https://github.com
curl -sIL -o /dev/null -w "hf=%{http_code}\n"     https://huggingface.co
```

**Required minimums**: Python 3.10–3.12; 8 GB free RAM; 6 GB free disk; both
HTTP probes returning `200` or `301`. If any minimum fails, stop and report.

**GPU classification** (choose one based on `nvidia-smi` output):

| Class | Criterion | Effect |
|---|---|---|
| `gpu-cuda` | NVIDIA GPU with ≥ 6 GB VRAM | install CUDA wheel, offload all layers, use 7B model |
| `gpu-low`  | NVIDIA GPU with 4–6 GB VRAM | install CUDA wheel, offload all layers, use 3B model |
| `cpu-only` | no NVIDIA GPU | CPU wheel, use 1.5B model |

---

## 4. Working directory

Create the deployment directory and `cd` into it. Do **not** clone into the
user's home root.

```bash
# Pick whichever the host conventions prefer; below is a sane default.
mkdir -p ~/dealer-ai-deploy && cd ~/dealer-ai-deploy
```

If anything below fails halfway, you may safely delete this directory and
restart the script from §5.

---

## 5. Clone the repository

```bash
git clone --depth 1 --branch claude/blackjack-game-architecture-k3Yf6 \
    https://github.com/zhangtianhai2017/test-.git repo
cd repo
```

**Verify**: `ls packages/dealer-ai/pyproject.toml` must exist and be
non-empty. If it doesn't, report a clone failure.

---

## 6. Install dependencies

### 6.1 Create a Python virtual environment

```bash
# Linux / macOS / WSL
python3 -m venv .venv
source .venv/bin/activate

# Windows PowerShell
# py -3.11 -m venv .venv
# .\.venv\Scripts\Activate.ps1
```

After activation, `python --version` must print 3.10/3.11/3.12.

### 6.2 Install the service package

```bash
pip install --upgrade pip
pip install -e packages/dealer-ai
```

This installs FastAPI, uvicorn, pydantic, llama-cpp-python (CPU build),
httpx, python-multipart.

### 6.3 GPU upgrade (only if §3 GPU class is `gpu-cuda` or `gpu-low`)

The CPU `llama-cpp-python` wheel has just been installed. If the host has a
CUDA-capable NVIDIA GPU, replace it with the matching CUDA build. Detect the
CUDA major version first:

```bash
nvcc --version 2>/dev/null | grep "release" || nvidia-smi | grep "CUDA Version"
```

Common cases:

```bash
# CUDA 12.4 / 12.5 / 12.6 (most modern systems)
pip install --upgrade --force-reinstall --no-cache-dir \
    --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu124/ \
    llama-cpp-python

# CUDA 12.1
pip install --upgrade --force-reinstall --no-cache-dir \
    --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu121/ \
    llama-cpp-python

# CUDA 11.8
pip install --upgrade --force-reinstall --no-cache-dir \
    --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu118/ \
    llama-cpp-python
```

If no matching CUDA wheel exists for the host's CUDA version, fall back to
the CPU wheel (already installed) and **downgrade the GPU class to
`cpu-only`**. Note this in your Final Report.

### 6.4 Install the model downloader's deps

```bash
pip install huggingface_hub
```

### 6.5 Install dev tools (for verification)

```bash
pip install pytest httpx
```

---

## 7. Download the model

Pick the size based on §3 GPU classification:

| GPU class | Model size | File size | Argument |
|---|---|---|---|
| `gpu-cuda` | Qwen 2.5 7B Instruct Q4_K_M | ~4.5 GB | `7B` |
| `gpu-low`  | Qwen 2.5 3B Instruct Q4_K_M | ~2.0 GB | `3B` |
| `cpu-only` | Qwen 2.5 1.5B Instruct Q4_K_M | ~1.0 GB | `1.5B` |

Run:

```bash
python packages/dealer-ai/scripts/download_model.py <SIZE>
# e.g. python packages/dealer-ai/scripts/download_model.py 3B
```

The downloader prints the absolute path of the file when finished. **Save
that path** — you will use it in §8.

If the download fails because of an HTTP error, retry up to 3 times with
exponential backoff (`sleep 2`, `sleep 4`, `sleep 8`). If still failing,
fall back one size smaller (`7B → 3B → 1.5B`) and note it.

If even `1.5B` fails (e.g. no HuggingFace access at all), do **not** abort.
Skip the model and run the service in mock mode (set `DEALER_AI_USE_MOCK=1`
when starting). The service will still pass §9 verification, just with
canned responses, and your report should flag this.

---

## 8. Start the service (background)

### 8.1 Compose the env vars

```bash
export DEALER_AI_HOST=127.0.0.1
export DEALER_AI_PORT=8787
export DEALER_AI_MODEL="/absolute/path/to/qwen2.5-XX-instruct-q4_k_m.gguf"   # from §7

# Only if GPU class is gpu-cuda or gpu-low:
export DEALER_AI_GPU_LAYERS=999

# If you fell back to mock mode in §7:
# unset DEALER_AI_MODEL
# export DEALER_AI_USE_MOCK=1
```

(On Windows PowerShell use `$env:NAME = "value"` instead of `export`.)

### 8.2 Start it

Linux / macOS / WSL:

```bash
nohup python -m dealer_ai.main \
    --host "$DEALER_AI_HOST" --port "$DEALER_AI_PORT" \
    > dealer-ai.log 2>&1 &
echo $! > dealer-ai.pid
```

Windows PowerShell:

```powershell
Start-Process -FilePath python `
    -ArgumentList "-m","dealer_ai.main","--host","127.0.0.1","--port","8787" `
    -RedirectStandardOutput dealer-ai.log `
    -RedirectStandardError  dealer-ai.err.log `
    -PassThru | ForEach-Object { $_.Id } | Out-File dealer-ai.pid
```

Wait up to **60 seconds** for first-time model load. Poll with:

```bash
for i in $(seq 1 60); do
    sleep 1
    curl -sf http://127.0.0.1:8787/health > /dev/null && break
done
curl -s http://127.0.0.1:8787/health
```

If `/health` does not respond within 60 s, dump the log
(`tail -50 dealer-ai.log`) and consult §10 Troubleshooting before retrying.

---

## 9. Verification (must all pass)

Run each test in order. Each one is a single `curl` and a single assertion.

### 9.1 Health endpoint

```bash
curl -s http://127.0.0.1:8787/health | tee /tmp/health.json
```

**Must contain** `"ok": true`. `llm.ready` is `true` if a real model loaded
or `true` with status `mock_loaded` in mock mode. `tts.ready` may be `false`
— that is expected (TTS is a future step).

### 9.2 List personas

```bash
curl -s http://127.0.0.1:8787/personas | python -m json.tool
```

**Must contain** three personas with ids `veteran`, `hostess`, `mystic`.

### 9.3 Open a Chinese session and ask for a quip

```bash
SID=$(curl -s -X POST http://127.0.0.1:8787/session \
    -H 'Content-Type: application/json' \
    -d '{"language":"zh","persona":"veteran","player_name":"测试"}' \
    | python -c "import json,sys;print(json.load(sys.stdin)['session_id'])")
echo "session=$SID"

curl -s -X POST "http://127.0.0.1:8787/session/$SID/quip" \
    -H 'Content-Type: application/json' \
    -d '{"event":"NATURAL_BLACKJACK","state":{"player_total":21,"bet":50,"net":75}}'
```

**Must return** a JSON object whose `text` contains at least one CJK
character (`\u4e00`–`\u9fff`) and whose `language` is `"zh"`. Latency
should be under 5 seconds (real model) or under 200 ms (mock).

### 9.4 Open an English session and ask for a quip

```bash
SID=$(curl -s -X POST http://127.0.0.1:8787/session \
    -H 'Content-Type: application/json' \
    -d '{"language":"en","persona":"hostess"}' \
    | python -c "import json,sys;print(json.load(sys.stdin)['session_id'])")

curl -s -X POST "http://127.0.0.1:8787/session/$SID/quip" \
    -H 'Content-Type: application/json' \
    -d '{"event":"BIG_WIN","state":{"net":300,"streak":3}}'
```

**Must return** an English text (ASCII letters only, no CJK), `language`
`"en"`.

### 9.5 Latency budget (real model only — skip in mock mode)

Run `9.3` ten times and record `latency_ms` from each response. Compute
mean and p95.

| Hardware | Acceptable mean | Acceptable p95 |
|---|---|---|
| `gpu-cuda` (7B) | < 1500 ms | < 2500 ms |
| `gpu-low`  (3B) | < 1200 ms | < 2000 ms |
| `cpu-only` (1.5B) | < 5000 ms | < 8000 ms |

If latency is worse than acceptable, do **not** consider the deployment
failed — record the numbers and recommend dropping one model size.

### 9.6 Run the bundled integration tests

```bash
python -m pytest packages/dealer-ai/tests/ -v
```

**Must show 4 passed**.

---

## 10. Troubleshooting (common failures and the canonical fix)

| Symptom | Likely cause | Fix |
|---|---|---|
| `pip install -e packages/dealer-ai` fails compiling llama-cpp-python | Build toolchain missing | `apt install build-essential cmake` (Linux), install Visual Studio Build Tools 2022 (Windows). Or skip 6.2 and install the **prebuilt CPU wheel** directly: `pip install llama-cpp-python --prefer-binary` |
| `nvidia-smi` works but inference is slow as CPU | CUDA wheel didn't actually install | Re-run §6.3 with `--force-reinstall --no-cache-dir` and verify the wheel filename in pip's output contains `cu12x` |
| `/health` shows `llm.ready=false`, status `model_not_found` | `DEALER_AI_MODEL` path wrong | `ls -la $DEALER_AI_MODEL` to confirm; restart server |
| `/health` shows `import_failed: No module named 'llama_cpp'` | Wrong venv active | `which python` should be inside `.venv`; reactivate and re-install |
| HuggingFace download hangs or 403s | Geo / firewall block | Try the mirror: `HF_ENDPOINT=https://hf-mirror.com python packages/dealer-ai/scripts/download_model.py 3B` |
| Port 8787 already in use | Another instance running, or another app | `kill $(cat dealer-ai.pid)` to stop ours, or `--port 8788` |
| Long delays on first `/quip` (CPU only) | Model warm-up | Issue one warm-up `/quip` after start before benchmarking |

If none of these match, capture the **last 100 lines of dealer-ai.log**
verbatim into your report. Do not guess.

---

## 11. Final Success Checklist (every box must be checked)

- [ ] Repo cloned at the specified branch
- [ ] Python venv created and activated, version in 3.10–3.12
- [ ] `pip install -e packages/dealer-ai` succeeded
- [ ] (If GPU) CUDA `llama-cpp-python` wheel installed and verified
- [ ] Model downloaded (or mock mode flagged in report)
- [ ] Service launched as a background process and PID file written
- [ ] §9.1–9.4 all passed
- [ ] §9.5 latency measured and within budget (or noted otherwise)
- [ ] §9.6 pytest shows `4 passed`
- [ ] Service is still running when you finish (do not kill it on exit)

---

## 12. Final Report — produce exactly this block

After everything above, output the report below, filling in every field.
**Do not reformat, do not add commentary outside the block.** The user pipes
this back to the upstream agent that wrote this brief.

```
=== DEALER-AI DEPLOYMENT REPORT ===
host_os:           <e.g. Ubuntu 22.04 / Windows 11 23H2>
python_version:    <3.11.x>
gpu_class:         <gpu-cuda | gpu-low | cpu-only>
gpu_name:          <e.g. RTX 4070 / N/A>
ram_gb:            <e.g. 32>
free_disk_gb:      <e.g. 120>

repo_commit:       <git rev-parse HEAD>
install_dir:       <absolute path>
venv_python:       <output of `which python` inside venv>

llama_cpp_wheel:   <pip show llama-cpp-python | grep Version, plus "CPU" or "cu124">
model_size:        <0.5B | 1.5B | 3B | 7B | mock>
model_path:        <absolute path or "N/A (mock)">
model_load_time_s: <seconds, from dealer-ai.log>

service_pid:       <pid>
service_url:       http://127.0.0.1:8787
health_status:     <copy of /health JSON, single line>

verify_9_3_text:   <the dealer's Chinese quip>
verify_9_4_text:   <the dealer's English quip>

latency_mean_ms:   <from §9.5>
latency_p95_ms:    <from §9.5>

pytest_result:     <e.g. "4 passed in 4.05s">

issues_encountered: <bullet list, or "none">
recommendations:   <bullet list, or "none">
=== END REPORT ===
```

---

## 13. Out of scope for this brief

The following are **not** to be installed or attempted by you:

- CosyVoice TTS (separate brief — needs the GPU machine first)
- The Unreal Engine plugin (`packages/ue-plugin/`) — Windows + UE 5.x toolchain
- The 3D web client (`packages/ui-3d/`) — same backend, additional UI work
- The C++ blackjack engine port (`packages/ue-plugin/Source/BlackjackCore/`)
- Multi-seat engine refactor

If the user asks you to do any of these, tell them this brief covers
**dealer-ai service deployment only** and a separate brief is needed.
