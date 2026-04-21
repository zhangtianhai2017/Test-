# build.ps1 — produce game-server.exe from the TypeScript source.
#
# Packager choice (per D-020): @yao-pkg/pkg.
#
# Why @yao-pkg/pkg and not vercel/pkg:
#   - vercel/pkg is archived; latest published build targets Node 18 and lacks
#     support for Node 20+ features we use via `ws` and `zod` v3.23. The
#     community fork @yao-pkg/pkg ships prebuilt Node 20 / 22 snapshots and
#     is actively maintained.
#   - We need WebSocket upgrade handling (ws@8) on a LAN port — works fine
#     with @yao-pkg/pkg's node20-win-x64 snapshot.
#
# Fallback (commented): bun build --compile. Bun can cross-compile TS to a
# single Windows exe too, but it's a different JS runtime and we haven't
# certified the @blackjack/engine+ws stack on it yet.

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $PSCommandPath
$RepoRoot  = Resolve-Path (Join-Path $ScriptDir "..\..")
$ServerDir = Join-Path $RepoRoot "packages\game-server"
$OutRoot   = Join-Path $ScriptDir "..\output"
$StageDir  = Join-Path $OutRoot "game-server"

Write-Host "[game-server/build] source dir: $ServerDir"
Write-Host "[game-server/build] staging to: $StageDir"

if (-not (Test-Path $ServerDir)) {
    throw "game-server package not found at $ServerDir"
}
if (-not (Test-Path $OutRoot)) { New-Item -ItemType Directory -Force -Path $OutRoot | Out-Null }
if (Test-Path $StageDir) { Remove-Item -Recurse -Force $StageDir }
New-Item -ItemType Directory -Force -Path $StageDir | Out-Null

# 1. Make sure @yao-pkg/pkg is available (global install).
$pkgCmd = Get-Command pkg -ErrorAction SilentlyContinue
if (-not $pkgCmd) {
    Write-Host "[game-server/build] installing @yao-pkg/pkg globally..."
    & npm install -g "@yao-pkg/pkg"
    if ($LASTEXITCODE -ne 0) { throw "npm i -g @yao-pkg/pkg failed" }
}

# 2. Ensure the game-server itself has its deps compiled (tsx → js snapshot
#    is handled by pkg, but workspace deps @blackjack/engine + @blackjack/ai-npc
#    must be resolvable from node_modules).
Push-Location $RepoRoot
try {
    & npm install
    if ($LASTEXITCODE -ne 0) { throw "npm install at repo root failed" }
} finally {
    Pop-Location
}

# 3. Build via the package's own bundling script. We call into a wrapper
#    at packages/game-server/scripts/bundle.ps1 so per-server concerns
#    (entry point, asset globs) live next to the server, not here.
$Bundler = Join-Path $ServerDir "scripts\bundle.ps1"
if (-not (Test-Path $Bundler)) {
    throw "expected bundler at $Bundler (packages/game-server/scripts/bundle.ps1)"
}
Push-Location $ServerDir
try {
    & $Bundler -OutputExe (Join-Path $StageDir "game-server.exe")
    if ($LASTEXITCODE -ne 0) { throw "bundle.ps1 failed (exit $LASTEXITCODE)" }
} finally {
    Pop-Location
}

# 4. Copy shipping config into the staging dir for reference (installer also
#    places it at %ProgramData%\Blackjack\server-config.json).
Copy-Item (Join-Path $ScriptDir "server-config.json") `
          (Join-Path $StageDir "server-config.json") -Force

Write-Host "[game-server/build] OK -> $StageDir"

# --- Fallback recipe (kept in source, not executed) -----------------------
# If @yao-pkg/pkg ever breaks on a future Node major, swap bundle.ps1 to use:
#   bun build ./src/main.ts --compile --target=bun-windows-x64 \
#            --outfile ../../packaging/output/game-server/game-server.exe
# Note: bun runtime != node; validate WebSocket + zod behavior end-to-end first.
