# Windows launcher — mirrors run.sh.
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSCommandPath)
Set-Location ..

$ModelDir = if ($env:MODEL_DIR) { $env:MODEL_DIR } else { ".\models" }
$Default = "qwen2.5-1.5b-instruct-q4_k_m.gguf"
$ModelPath = Join-Path $ModelDir $Default

if (Test-Path $ModelPath) {
    $env:DEALER_AI_MODEL = $ModelPath
    Write-Host ">>> Running with real LLM: $ModelPath"
} else {
    $env:DEALER_AI_USE_MOCK = "1"
    Write-Host ">>> No GGUF found at $ModelDir\ — running with MOCK LLM"
    Write-Host "    (download one via: python scripts\download_model.py 1.5B)"
}

python -m dealer_ai.main @args
