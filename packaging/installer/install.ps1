# install.ps1 — install Blackjack v1 system-wide.
#
# Must run as Administrator. Copies build artefacts to %ProgramFiles%\Blackjack,
# registers two Windows Services (dealer-ai, game-server) with a start-order
# dependency, and opens an inbound firewall rule for port 7878/tcp scoped to
# the LocalSubnet (LAN play, not public internet).
#
# Service wrapping strategy (tried in order):
#   1. NSSM if `Get-Command nssm` resolves. NSSM is the most forgiving wrapper
#      for processes that weren't designed as Windows Services.
#   2. sc.exe as a fallback. Works but logging + restart behaviour are
#      less pleasant; we set failure-action to restart on crash.

$ErrorActionPreference = "Stop"

# --- 0. Require admin --------------------------------------------------
$currentUser = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal   = New-Object Security.Principal.WindowsPrincipal($currentUser)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "install.ps1 must be run as Administrator."
}

$ScriptDir = Split-Path -Parent $PSCommandPath
$OutDir    = Resolve-Path (Join-Path $ScriptDir "..\output")
if (-not (Test-Path $OutDir)) {
    throw "no build artefacts at $OutDir — run packaging/build-all.ps1 first"
}

$InstallRoot = Join-Path $env:ProgramFiles "Blackjack"
$ConfigRoot  = Join-Path $env:ProgramData "Blackjack"
$LogRoot     = Join-Path $env:ProgramData "Blackjack\logs"

Write-Host "[install] install root : $InstallRoot"
Write-Host "[install] config root  : $ConfigRoot"

foreach ($d in @($InstallRoot, $ConfigRoot, $LogRoot)) {
    New-Item -ItemType Directory -Force -Path $d | Out-Null
}

# --- 1. Copy artefacts -------------------------------------------------
Write-Host "[install] copying dealer-ai + game-server..."
Copy-Item -Recurse -Force (Join-Path $OutDir "dealer-ai")   $InstallRoot
Copy-Item -Recurse -Force (Join-Path $OutDir "game-server") $InstallRoot
Copy-Item -Force (Join-Path $OutDir "server-config.json") `
          (Join-Path $ConfigRoot "server-config.json")

$DealerExe = Join-Path $InstallRoot "dealer-ai\dealer-ai.exe"
$ServerExe = Join-Path $InstallRoot "game-server\game-server.exe"
if (-not (Test-Path $DealerExe)) { throw "missing $DealerExe" }
if (-not (Test-Path $ServerExe)) { throw "missing $ServerExe" }

# --- 2. Environment, per D-011 / D-015 ---------------------------------
# Persist machine-level env so the services inherit them. Keep loopback-only
# by default (D-011: "Server-side (dealer-ai) runs on Windows headless").
[Environment]::SetEnvironmentVariable("DEALER_AI_HOST", "127.0.0.1", "Machine")
[Environment]::SetEnvironmentVariable("DEALER_AI_PORT", "8787",      "Machine")
# If a model was bundled alongside the exe, point at the largest .gguf we find.
$ModelsDir = Join-Path $InstallRoot "dealer-ai\models"
if (Test-Path $ModelsDir) {
    $gguf = Get-ChildItem $ModelsDir -Filter *.gguf -ErrorAction SilentlyContinue `
        | Sort-Object Length -Descending | Select-Object -First 1
    if ($gguf) {
        [Environment]::SetEnvironmentVariable("DEALER_AI_MODEL", $gguf.FullName, "Machine")
        Write-Host "[install] DEALER_AI_MODEL = $($gguf.FullName)"
    }
} else {
    [Environment]::SetEnvironmentVariable("DEALER_AI_USE_MOCK", "1", "Machine")
    Write-Host "[install] no .gguf found — DEALER_AI_USE_MOCK=1"
}

# --- 3. Register services ---------------------------------------------
$nssm = Get-Command nssm -ErrorAction SilentlyContinue

function Install-Svc($name, $exe, $depends) {
    if ($nssm) {
        Write-Host "[install] registering $name via NSSM"
        & nssm install $name $exe | Out-Null
        & nssm set $name AppDirectory (Split-Path -Parent $exe) | Out-Null
        & nssm set $name AppStdout (Join-Path $LogRoot "$name.out.log") | Out-Null
        & nssm set $name AppStderr (Join-Path $LogRoot "$name.err.log") | Out-Null
        & nssm set $name Start SERVICE_AUTO_START | Out-Null
        if ($depends) { & nssm set $name DependOnService $depends | Out-Null }
    } else {
        Write-Host "[install] registering $name via sc.exe"
        $depArg = if ($depends) { "depend= $depends" } else { "" }
        & sc.exe create $name binPath= "`"$exe`"" start= auto $depArg | Out-Null
        # Restart on first 3 failures at 5s intervals.
        & sc.exe failure $name reset= 86400 actions= restart/5000/restart/5000/restart/5000 | Out-Null
    }
}

Install-Svc "BlackjackDealerAI" $DealerExe $null
Install-Svc "BlackjackGameServer" $ServerExe "BlackjackDealerAI"

# --- 4. Firewall rule (LAN only) ---------------------------------------
Write-Host "[install] opening inbound 7878/tcp for LocalSubnet..."
New-NetFirewallRule -DisplayName "Blackjack Game Server (LAN)" `
    -Direction Inbound -Protocol TCP -LocalPort 7878 `
    -Action Allow -Profile Any -RemoteAddress LocalSubnet `
    -ErrorAction SilentlyContinue | Out-Null

# --- 5. Start services -------------------------------------------------
Start-Service BlackjackDealerAI
Start-Service BlackjackGameServer
Write-Host "[install] done. Services:"
Get-Service BlackjackDealerAI, BlackjackGameServer | Format-Table -AutoSize
