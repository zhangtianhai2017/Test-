# stop-local.ps1 — stop the two processes started by launch-local.ps1.
#
# Reads the pid files out of %LOCALAPPDATA%\Blackjack\logs\. Tolerant of
# stale pid files (process already gone).

$ErrorActionPreference = "Stop"
$LogDir = Join-Path $env:LOCALAPPDATA "Blackjack\logs"

function Stop-Pidfile($file) {
    if (-not (Test-Path $file)) {
        Write-Host "[stop-local] no pid file at $file — skipping"
        return
    }
    $raw = Get-Content $file -Raw
    $p = $raw.Trim()
    if (-not $p) { return }
    $proc = Get-Process -Id $p -ErrorAction SilentlyContinue
    if ($proc) {
        Write-Host "[stop-local] stopping PID $p ($($proc.ProcessName))"
        Stop-Process -Id $p -Force -ErrorAction SilentlyContinue
    } else {
        Write-Host "[stop-local] PID $p already gone"
    }
    Remove-Item $file -ErrorAction SilentlyContinue
}

Stop-Pidfile (Join-Path $LogDir "game-server.pid")
Stop-Pidfile (Join-Path $LogDir "dealer-ai.pid")

Write-Host "[stop-local] done."
