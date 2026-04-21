# DEPLOY_V1 — Integration-test runbook for Blackjack v1 on Windows

> **Audience**: a human operator or autonomous coding agent standing at a
> Windows 10/11 box with a checkout of this repo. Follow the sections
> in order. If a step fails, consult §6 Troubleshooting before retrying.
> You do **not** need to open multiple briefs — this single document
> covers bringing up `dealer-ai`, `game-server`, and the UE game client
> together, and verifying the combined system end-to-end.

For a dealer-ai-only deployment (AI-service-only box, no game server, no
UE), prefer the narrower brief at `docs/DEPLOY_DEALER_AI.md`.

---

## 1. Prerequisites

| Component | Required version | Why |
|---|---|---|
| Windows | 10 22H2 or 11 | UE 5.3 supports both; firewall rules use modern `NetFirewallRule` cmdlets |
| Python | 3.10, 3.11, or 3.12 | llama-cpp-python wheels don't yet cover 3.13 (per `docs/DEPLOY_DEALER_AI.md` §3) |
| Node.js | >= 20 LTS | @yao-pkg/pkg target `node20-win-x64` |
| PowerShell | 5.1 or 7 | All installer scripts use `$ErrorActionPreference = "Stop"` |
| Unreal Engine | 5.3+ | UE plugin in `packages/ue-plugin/` |
| NVIDIA GPU | >= 6 GB VRAM, CUDA 12.x driver | Optional; required only for CosyVoice TTS real-time voice. LLM can run CPU-only. See D-011. |
| Disk space | ~8 GB free | 4.5 GB model + ~3 GB runtime + 500 MB exes |
| RAM | 16 GB | Per D-011 target hardware |

Clients that are useful to have installed for the smoke test:

- `curl` (shipped with Windows 10/11).
- `wscat` for WebSocket pokes: `npm install -g wscat`.
- The UE Editor with the repo's `packages/ue-plugin/` project already
  opened at least once so Intermediate/ caches exist.

---

## 2. First run

From an elevated PowerShell at the repo root:

```powershell
# 2.1 make sure the Node + Python workspaces install cleanly
npm install
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e packages/dealer-ai

# 2.2 build the two exes
cd packaging
./build-all.ps1
# => produces packaging/output/dealer-ai/ and packaging/output/game-server/

# 2.3 install system-wide (requires Admin)
./installer/install.ps1
# registers BlackjackDealerAI and BlackjackGameServer as auto-start services
# and opens inbound 7878/tcp for LocalSubnet.

# 2.4 (alternative, no admin, no services)
./installer/launch-local.ps1
# starts both exes with their stdout/stderr captured under
# %LOCALAPPDATA%\Blackjack\logs\.
```

After a reboot, `Get-Service BlackjackDealerAI, BlackjackGameServer`
should report both as `Running`.

If you installed a CUDA `llama-cpp-python` wheel on this box and want GPU
offload, set the machine env var:

```powershell
[Environment]::SetEnvironmentVariable("DEALER_AI_GPU_LAYERS", "999", "Machine")
Restart-Service BlackjackDealerAI
```

---

## 3. Smoke test

Run each step in order. A failure at step `N` should be diagnosed before
moving on; §6 catalogues the common causes.

### 3.1 dealer-ai /health

```powershell
curl http://127.0.0.1:8787/health
```

Expected JSON:

- `ok: true`
- `llm.ready: true` — `status` will be `loaded` with a real model, or
  `mock_loaded` if `DEALER_AI_USE_MOCK=1`.
- `tts.ready: true` **iff** a GPU with CosyVoice is installed; `false`
  on CPU-only boxes is expected (see D-011).

### 3.2 game-server WebSocket HELLO

```powershell
wscat -c ws://127.0.0.1:7878/game
# then paste:
{"v":1,"type":"HELLO","displayName":"Tester"}
```

Expected: a frame back with `"type":"WELCOME"`, a `sessionId` UUID, and
the server version.

### 3.3 Full round over WS (2 clients, same box)

Open two PowerShell windows, one `wscat` each:

1. **Client A** sends `HELLO` (nickname `A`), then a `CREATE_TABLE` frame
   with `{ "seats": 6, "rules": "vegas_h17" }`. Record the returned
   `tableId`.
2. **Client B** sends `HELLO` (nickname `B`), then
   `JOIN_TABLE { tableId, seat: 2 }`. Expect a `TABLE_STATE` broadcast
   to both clients.
3. Both clients `PLACE_BET { amount: 50 }`. Server broadcasts
   `ROUND_START`, deals, then sends per-turn `YOUR_TURN` frames.
4. Send `ACTION { type: "STAND" }` for each seat. Server resolves the
   dealer and broadcasts `ROUND_END` with `net` amounts.

A valid round traversal is: HELLO → WELCOME → CREATE_TABLE → TABLE_STATE
→ JOIN_TABLE → TABLE_STATE → PLACE_BET×2 → ROUND_START → deal frames →
YOUR_TURN → ACTION → ... → ROUND_END.

### 3.4 UE client connects

Once the user has packaged their UE project (see
`packaging/ue-game/README.md`):

1. Launch `BlackjackGame.exe`.
2. In the opening menu (or via the in-editor Play button), trigger
   `UBlackjackNetClient::Connect(TEXT("127.0.0.1"), 7878, TEXT("Tester"))`.
3. Expected: `OnNetStatus` fires with `Connected`, followed by a
   `WELCOME` frame, then a `TABLE_STATE` after the client auto-joins a
   table.
4. Trigger a `POST /session/{id}/quip` indirectly (dealing a natural
   blackjack is the easiest path) and observe the `OnDealerQuip` event
   firing with a short text string. If TTS is loaded on the server, an
   audio clip reference accompanies the event.

---

## 4. Acceptance criteria

Every item below must pass on the target box.

- [ ] **dealer-ai unit tests**: from the repo root with the venv active,
      `pytest packages/dealer-ai/tests/ -v` shows **13 passed**.
- [ ] **game-server unit tests**: `cd packages/game-server && npm test`
      shows **64 passed**.
- [ ] **engine unit tests**: `cd packages/engine && npm test` shows
      **57 passed**.
- [ ] **ai-npc unit tests**: `cd packages/ai-npc && npm test` shows
      **93 passed**.
- [ ] **Combined run**: UE client connects to game-server; at least one
      round completes with 1 human + 2 NPC seats; at least one
      `OnDealerQuip` event is observed; if TTS is loaded, audio plays.
- [ ] Services survive a `Restart-Service BlackjackGameServer`
      (reconnect grace per D-022).

Record the pass counts verbatim in your report — if the game-server or
ai-npc suites have grown since this document, note the delta rather
than calling it a failure.

---

## 5. Where things live

See `packaging/layout/README.md` for the full on-disk tree. Quick
pointers while troubleshooting:

- Services logs (installer mode): `%ProgramData%\Blackjack\logs\`.
- Services logs (launch-local mode): `%LOCALAPPDATA%\Blackjack\logs\`.
- Shipping config: `%ProgramData%\Blackjack\server-config.json`.
- Machine env vars set by installer: `DEALER_AI_HOST`, `DEALER_AI_PORT`,
  `DEALER_AI_MODEL` or `DEALER_AI_USE_MOCK`. `DEALER_AI_GPU_LAYERS`
  is **not** set by the installer; set it yourself if you want GPU
  offload.

---

## 6. Troubleshooting

| # | Symptom | Likely cause | Fix |
|---|---|---|---|
| 1 | `BlackjackGameServer` won't start, log shows `EADDRINUSE :7878` | Port 7878 already taken by another process (common: a prior crashed node instance) | `Get-NetTCPConnection -LocalPort 7878 \| Select-Object OwningProcess` then `Stop-Process <pid>`; or change `port` in `%ProgramData%\Blackjack\server-config.json` and `Restart-Service BlackjackGameServer` |
| 2 | UE client on a second LAN machine gets `connection refused` | Windows firewall dropped the LAN inbound | Verify `Get-NetFirewallRule -DisplayName "Blackjack Game Server (LAN)"` exists and is enabled; confirm the second machine is on the same subnet (`LocalSubnet` scope). Re-run `install.ps1` as Admin to recreate the rule |
| 3 | `pip install -e packages/dealer-ai` fails building llama-cpp-python | MSVC build tools missing | Install Visual Studio Build Tools 2022 (C++ workload), reopen PowerShell, retry. As an escape hatch: `pip install llama-cpp-python --prefer-binary` picks a prebuilt wheel |
| 4 | `/health` shows `llm.ready: false` with `import_failed: No module named 'torch'` after GPU upgrade | PyTorch / CUDA mismatch — TTS extras pulled a torch build that clashed with system CUDA | The base bundle shouldn't need torch at all; confirm the installer didn't pick up the `[tts]` extra by mistake. Reinstall with `pip install -e packages/dealer-ai` (without `[tts]`) and rebuild. If you *want* TTS, follow `packages/dealer-ai/README.md` for the matching CUDA `torch` wheel |
| 5 | `install.ps1` log reads `sc.exe create` succeeded but service won't start, event viewer shows exit 1077 | NSSM absent **and** sc.exe cannot cleanly host an interactive exe | Install NSSM (`choco install nssm`) and re-run `install.ps1` — it prefers NSSM when available. NSSM handles stdout/stderr redirection which raw sc.exe does not |
| 6 | UE plugin fails to compile with `UBlackjackNetClient` symbol not found | Build cache is stale from before the M8 rename | In UE Editor: close, delete `packages/ue-plugin/{Binaries,Intermediate,Saved}`, reopen, accept the rebuild prompt. Do **not** edit the C++ from this packaging tree (M8 is concurrent) |
| 7 | `game-server.exe` exits immediately with `ENOENT` on server-config.json | `launch-local.ps1` couldn't locate the config file | Make sure `%ProgramData%\Blackjack\server-config.json` exists, or pass `--config <path>` yourself. Fresh `install.ps1` writes this file; `launch-local.ps1` does not |
| 8 | On first launch, dealer-ai takes > 60 s and `launch-local.ps1` times out | Cold model load from disk | Normal on CPU with a 3B/7B model. Either increase the timeout in `launch-local.ps1` (the 60 s `for ($i…)` loop) or switch to a smaller model size as per `docs/DEPLOY_DEALER_AI.md` §7 |

---

## 7. When you are done

Produce a short report containing:

- Output of `curl http://127.0.0.1:8787/health` (one line).
- `Get-Service BlackjackDealerAI, BlackjackGameServer` output.
- Unit test pass counts for engine / ai-npc / game-server / dealer-ai.
- UE smoke-test result (WELCOME observed Y/N; OnDealerQuip observed Y/N).
- Any §6 entries you had to apply, and whether the fix was permanent.
