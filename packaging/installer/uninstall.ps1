# uninstall.ps1 — symmetric removal of install.ps1.
#
# Must run as Administrator. Stops + removes the two Windows Services,
# removes the firewall rule, clears machine-level env vars, and wipes the
# install tree under %ProgramFiles%\Blackjack. Logs under %ProgramData%\
# Blackjack\logs are preserved unless -Purge is passed.

param(
    [switch]$Purge
)

$ErrorActionPreference = "Stop"

$currentUser = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal   = New-Object Security.Principal.WindowsPrincipal($currentUser)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "uninstall.ps1 must be run as Administrator."
}

$InstallRoot = Join-Path $env:ProgramFiles "Blackjack"
$ConfigRoot  = Join-Path $env:ProgramData  "Blackjack"

$nssm = Get-Command nssm -ErrorAction SilentlyContinue

function Remove-Svc($name) {
    $svc = Get-Service $name -ErrorAction SilentlyContinue
    if (-not $svc) { return }
    Write-Host "[uninstall] stopping $name"
    Stop-Service $name -Force -ErrorAction SilentlyContinue
    # Give the service a moment to release its exe handle.
    Start-Sleep -Seconds 2
    if ($nssm) {
        & nssm remove $name confirm | Out-Null
    } else {
        & sc.exe delete $name | Out-Null
    }
}

# Remove game-server first (it depends on dealer-ai).
Remove-Svc "BlackjackGameServer"
Remove-Svc "BlackjackDealerAI"

# Firewall rule.
Write-Host "[uninstall] removing firewall rule..."
Get-NetFirewallRule -DisplayName "Blackjack Game Server (LAN)" -ErrorAction SilentlyContinue `
    | Remove-NetFirewallRule -ErrorAction SilentlyContinue

# Machine env vars.
foreach ($v in @("DEALER_AI_HOST","DEALER_AI_PORT","DEALER_AI_MODEL","DEALER_AI_USE_MOCK","DEALER_AI_GPU_LAYERS")) {
    [Environment]::SetEnvironmentVariable($v, $null, "Machine")
}

# Files.
if (Test-Path $InstallRoot) {
    Write-Host "[uninstall] removing $InstallRoot"
    Remove-Item -Recurse -Force $InstallRoot
}

if ($Purge -and (Test-Path $ConfigRoot)) {
    Write-Host "[uninstall] purging $ConfigRoot (config + logs)"
    Remove-Item -Recurse -Force $ConfigRoot
} else {
    Write-Host "[uninstall] kept $ConfigRoot (pass -Purge to remove logs too)"
}

Write-Host "[uninstall] done."
