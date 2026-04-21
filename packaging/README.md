# packaging — Windows bundle for Blackjack v1

One-page orientation for whoever (human or AI) is standing at a Windows
build box with a cloned checkout of this repo.

## What lives here

```
packaging/
  build-all.ps1          — run this to produce packaging/output/
  dealer-ai/             — PyInstaller recipe for dealer-ai.exe
  game-server/           — pkg recipe for game-server.exe
  installer/             — install.ps1 / uninstall.ps1 / launch-local.ps1
  ue-game/               — notes on UE packaging (done in UE Editor, not here)
  layout/                — describes the shipped on-disk layout
```

Intermediate build products go to `packaging/output/` (gitignored, per
sub-build script). Final installable layout is assembled by the installer
from that folder.

## Prerequisites (builder machine)

- Windows 10 or 11 (x64).
- Python 3.10, 3.11, or 3.12 on PATH. **Not 3.13** — llama-cpp-python
  wheels lag. (See D-011.)
- Node.js >= 20 on PATH.
- `npm install` has been run at the repo root so `@blackjack/engine`,
  `@blackjack/ai-npc`, and `@blackjack/game-server` are wired up.
- `pip install -e packages/dealer-ai` has been run (the build pulls the
  same dependency graph via PyInstaller).
- PowerShell 5.1 or PowerShell 7. All scripts set
  `$ErrorActionPreference = "Stop"` so any failure aborts.

## Three-step build

```powershell
# 1. From the repo root, produce all exes into packaging/output/
cd packaging
./build-all.ps1

# 2. As Administrator, install to %ProgramFiles%\Blackjack, register
#    Windows Services, and open firewall rules.
Start-Process powershell -Verb RunAs -ArgumentList `
    "-File", "$PWD\installer\install.ps1"

# 3. Or, if you just want to run locally without services:
./installer/launch-local.ps1
```

## What NOT to do here

- Do not edit `packages/ue-plugin/` from this directory — UE packaging is
  owned by the user's UE Editor workflow; see `ue-game/README.md`.
- Do not commit `packaging/output/` — it is intermediate.
- Do not ship `.exe` binaries through git; use a release artifact store.

## Design references

- `coordination/DECISIONS.md` D-011, D-015, D-016, D-020, D-022.
- `docs/DEPLOY_DEALER_AI.md` — the original single-service brief, still
  valid for dealer-ai-only deployments.
- `docs/DEPLOY_V1.md` — integration-test runbook for the combined product.

## Open TODOs (explicit out-of-scope for M13)

- [ ] Code-signing (Authenticode) of `dealer-ai.exe`, `game-server.exe`,
      and the installer. Ship unsigned for now; SmartScreen will complain.
- [ ] Auto-update infrastructure.
- [ ] MSI/WiX wrapper around the PowerShell installer.
- [ ] CosyVoice model download step is still a separate manual step
      because the model is ~4 GB and not redistributable.
