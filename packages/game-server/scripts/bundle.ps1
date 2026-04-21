# bundle.ps1 — package game-server into a Windows exe.
#
# Invoked by packaging/game-server/build.ps1. Kept here (next to the server
# source) because the entry point, asset globs, and node target are
# per-server concerns, while the outer build.ps1 is just an orchestrator.
#
# Uses @yao-pkg/pkg (see D-020 and packaging/game-server/build.ps1 for the
# rationale). Entry point is src/main.ts; we first tsc-transpile to dist/
# (pkg doesn't handle .ts directly) then pkg the dist/main.js.

param(
    [Parameter(Mandatory=$true)][string]$OutputExe
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $PSCommandPath
$ServerDir = Resolve-Path (Join-Path $ScriptDir "..")

Write-Host "[game-server/bundle] server dir : $ServerDir"
Write-Host "[game-server/bundle] output exe : $OutputExe"

Push-Location $ServerDir
try {
    # 1. Transpile TS -> JS into ./dist/. We invoke tsc via npx so we
    #    don't require a separate global install.
    if (Test-Path "./dist") { Remove-Item -Recurse -Force "./dist" }
    & npx --yes tsc --outDir dist --module commonjs --target es2022 `
        --esModuleInterop --resolveJsonModule --skipLibCheck `
        --moduleResolution node src/main.ts
    if ($LASTEXITCODE -ne 0) { throw "tsc failed (exit $LASTEXITCODE)" }

    # 2. Use pkg to produce a Windows node20 x64 exe.
    $OutDir = Split-Path -Parent $OutputExe
    if (-not (Test-Path $OutDir)) {
        New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
    }
    & pkg ./dist/main.js `
        --target node20-win-x64 `
        --output $OutputExe `
        --compress GZip
    if ($LASTEXITCODE -ne 0) { throw "pkg failed (exit $LASTEXITCODE)" }
} finally {
    Pop-Location
}

if (-not (Test-Path $OutputExe)) {
    throw "pkg reported success but $OutputExe is missing"
}
Write-Host "[game-server/bundle] OK -> $OutputExe"
