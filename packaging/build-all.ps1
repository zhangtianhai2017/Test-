# build-all.ps1 — orchestrate every sub-build in order.
#
# Usage (from packaging/):
#     ./build-all.ps1
#
# Exits on first failure. Produces packaging/output/ with:
#     output/dealer-ai/dealer-ai.exe   (+ _internal/, personas/, fallback/)
#     output/game-server/game-server.exe
#     output/server-config.json
#
# No GUI, no prompts. Suitable for CI.

$ErrorActionPreference = "Stop"

# All paths relative to this script, absolute-ised.
$ScriptDir = Split-Path -Parent $PSCommandPath
$RepoRoot  = Resolve-Path (Join-Path $ScriptDir "..")
$OutDir    = Join-Path $ScriptDir "output"

Write-Host "[build-all] script dir : $ScriptDir"
Write-Host "[build-all] repo root  : $RepoRoot"
Write-Host "[build-all] output dir : $OutDir"

# Clean/ensure output dir.
if (Test-Path $OutDir) {
    Write-Host "[build-all] cleaning previous output..."
    Remove-Item -Recurse -Force $OutDir
}
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

# --- 1. dealer-ai.exe via PyInstaller ------------------------------------
Write-Host "`n========== [1/3] building dealer-ai.exe =========="
Push-Location (Join-Path $ScriptDir "dealer-ai")
try {
    & ./build.ps1
    if ($LASTEXITCODE -ne 0) { throw "dealer-ai build failed (exit $LASTEXITCODE)" }
} finally {
    Pop-Location
}

# --- 2. game-server.exe via @yao-pkg/pkg ---------------------------------
Write-Host "`n========== [2/3] building game-server.exe =========="
Push-Location (Join-Path $ScriptDir "game-server")
try {
    & ./build.ps1
    if ($LASTEXITCODE -ne 0) { throw "game-server build failed (exit $LASTEXITCODE)" }
} finally {
    Pop-Location
}

# --- 3. stage shipping config --------------------------------------------
Write-Host "`n========== [3/3] staging shipping config =========="
Copy-Item (Join-Path $ScriptDir "game-server/server-config.json") `
          (Join-Path $OutDir "server-config.json") -Force

Write-Host "`n[build-all] OK. Artifacts in: $OutDir"
Get-ChildItem -Recurse $OutDir | Select-Object FullName, Length | Format-Table -AutoSize
