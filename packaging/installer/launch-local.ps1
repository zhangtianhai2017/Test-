# launch-local.ps1 — start both services for a user who doesn't want (or
# can't, e.g. non-admin) Windows Service registration. Suitable for quick
# single-machine playtesting.
#
# Reads artefacts from packaging/output/ if present, else from
# %ProgramFiles%\Blackjack if the installer has already run. Pins logs to
# %LOCALAPPDATA%\Blackjack\logs\ so they don't require admin rights.

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $PSCommandPath
$LogDir    = Join-Path $env:LOCALAPPDATA "Blackjack\logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

# Find the exes: output/ first (dev box), then installed location.
$Candidates = @(
    (Join-Path $ScriptDir "..\output"),
    (Join-Path $env:ProgramFiles "Blackjack")
)
$Root = $null
foreach ($c in $Candidates) {
    if (Test-Path (Join-Path $c "dealer-ai\dealer-ai.exe")) {
        $Root = (Resolve-Path $c).Path
        break
    }
}
if (-not $Root) {
    throw "could not locate dealer-ai.exe in: $($Candidates -join '; ')"
}

$DealerExe = Join-Path $Root "dealer-ai\dealer-ai.exe"
$ServerExe = Join-Path $Root "game-server\game-server.exe"

Write-Host "[launch-local] root        : $Root"
Write-Host "[launch-local] logs        : $LogDir"

# Match the installer's env-var policy (D-011 / D-015) but scoped to this
# process tree, not the machine.
$env:DEALER_AI_HOST = "127.0.0.1"
$env:DEALER_AI_PORT = "8787"
$ModelsDir = Join-Path $Root "dealer-ai\models"
if (Test-Path $ModelsDir) {
    $gguf = Get-ChildItem $ModelsDir -Filter *.gguf -ErrorAction SilentlyContinue `
        | Sort-Object Length -Descending | Select-Object -First 1
    if ($gguf) { $env:DEALER_AI_MODEL = $gguf.FullName }
}
if (-not $env:DEALER_AI_MODEL) {
    $env:DEALER_AI_USE_MOCK = "1"
    Write-Host "[launch-local] no .gguf — running dealer-ai with DEALER_AI_USE_MOCK=1"
}

# Start dealer-ai first; game-server depends on its /health readiness.
$dealer = Start-Process -FilePath $DealerExe `
    -RedirectStandardOutput (Join-Path $LogDir "dealer-ai.out.log") `
    -RedirectStandardError  (Join-Path $LogDir "dealer-ai.err.log") `
    -PassThru -WindowStyle Hidden
Write-Host "[launch-local] dealer-ai PID $($dealer.Id)"

# Wait up to 60s for dealer-ai /health.
$ready = $false
for ($i = 0; $i -lt 60; $i++) {
    Start-Sleep -Seconds 1
    try {
        $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 `
             -Uri "http://127.0.0.1:8787/health"
        if ($r.StatusCode -eq 200) { $ready = $true; break }
    } catch { }
}
if (-not $ready) {
    throw "dealer-ai did not become healthy within 60s — see $LogDir"
}
Write-Host "[launch-local] dealer-ai healthy"

$server = Start-Process -FilePath $ServerExe `
    -ArgumentList "--config", (Join-Path $env:ProgramData "Blackjack\server-config.json") `
    -RedirectStandardOutput (Join-Path $LogDir "game-server.out.log") `
    -RedirectStandardError  (Join-Path $LogDir "game-server.err.log") `
    -PassThru -WindowStyle Hidden
Write-Host "[launch-local] game-server PID $($server.Id)"

# Persist PIDs so stop-local.ps1 can find them.
"$($dealer.Id)" | Set-Content (Join-Path $LogDir "dealer-ai.pid")
"$($server.Id)" | Set-Content (Join-Path $LogDir "game-server.pid")

Write-Host "[launch-local] both running. Connect UE client to ws://127.0.0.1:7878/game"
Write-Host "[launch-local] stop with: ./stop-local.ps1"
