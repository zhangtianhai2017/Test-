# build.ps1 — produce dealer-ai.exe via PyInstaller.
#
# Assumes the caller has already `pip install -e packages/dealer-ai` into the
# active Python environment (a venv is strongly recommended — PyInstaller
# bundles *everything* in the current env). We pip-install pyinstaller here
# on demand; it's not declared in pyproject.toml dev deps because it's
# Windows-packaging-only and adds ~50 MB.

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $PSCommandPath
$RepoRoot  = Resolve-Path (Join-Path $ScriptDir "..\..")
$OutDir    = Resolve-Path (Join-Path $ScriptDir "..\output") `
    -ErrorAction SilentlyContinue
if (-not $OutDir) {
    New-Item -ItemType Directory -Force -Path (Join-Path $ScriptDir "..\output") | Out-Null
    $OutDir = Resolve-Path (Join-Path $ScriptDir "..\output")
}
$StageDir = Join-Path $OutDir "dealer-ai"

Write-Host "[dealer-ai/build] repo root  : $RepoRoot"
Write-Host "[dealer-ai/build] staging to : $StageDir"

# 1. Sanity-check that the source package is importable.
Push-Location $RepoRoot
try {
    & python -c "import dealer_ai; print('dealer_ai OK at', dealer_ai.__file__)"
    if ($LASTEXITCODE -ne 0) {
        throw "dealer_ai not importable. Run 'pip install -e packages/dealer-ai' first."
    }
} finally {
    Pop-Location
}

# 2. Ensure pyinstaller is present.
& python -m pip install --quiet --disable-pip-version-check pyinstaller
if ($LASTEXITCODE -ne 0) { throw "pip install pyinstaller failed" }

# 3. Run PyInstaller against the spec.
Push-Location $ScriptDir
try {
    # -y = overwrite dist/ and build/ without prompting.
    & python -m PyInstaller -y dealer-ai.spec
    if ($LASTEXITCODE -ne 0) { throw "pyinstaller failed (exit $LASTEXITCODE)" }
} finally {
    Pop-Location
}

# 4. Stage the onedir bundle into packaging/output/dealer-ai/.
$DistDir = Join-Path $ScriptDir "dist\dealer-ai"
if (-not (Test-Path $DistDir)) {
    throw "Expected PyInstaller output at $DistDir, not found."
}
if (Test-Path $StageDir) { Remove-Item -Recurse -Force $StageDir }
New-Item -ItemType Directory -Force -Path $StageDir | Out-Null
Copy-Item -Recurse -Force "$DistDir\*" $StageDir

# 5. Optionally stage a pre-downloaded model alongside the exe. The user
#    can drop a .gguf into packages/dealer-ai/models/ and it'll ride along;
#    if nothing is there, dealer-ai falls back to DEALER_AI_USE_MOCK=1 at
#    runtime (see D-015: "Model download can be deferred to first run").
$ModelSrc = Join-Path $RepoRoot "packages\dealer-ai\models"
if (Test-Path $ModelSrc) {
    Write-Host "[dealer-ai/build] bundling models from $ModelSrc"
    Copy-Item -Recurse -Force $ModelSrc (Join-Path $StageDir "models")
} else {
    Write-Host "[dealer-ai/build] no models/ dir found — installer will mock or first-run download"
}

Write-Host "[dealer-ai/build] OK -> $StageDir"
