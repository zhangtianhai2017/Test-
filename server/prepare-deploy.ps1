# prepare-deploy.ps1 — generate tokens and produce an upload-ready
# relay-deploy.jsp with those tokens baked in.
#
# Outputs the two tokens to the console. The OPERATOR_TOKEN goes to
# the remote operator (Claude); the AGENT_TOKEN goes into start-agent.bat.
#
# Run from the repo root:
#   powershell -NoProfile -ExecutionPolicy Bypass -File server/prepare-deploy.ps1
#
# The deploy file is written to .\server\relay-deploy.jsp (gitignored).

param(
    [string]$Template   = (Join-Path $PSScriptRoot "relay.jsp"),
    [string]$OutFile    = (Join-Path $PSScriptRoot "relay-deploy.jsp"),
    [string]$OperatorTokenOverride = "",
    [string]$AgentTokenOverride    = ""
)

function NewToken {
    # 48 random bytes -> base64url, ~64 chars
    $b = New-Object byte[] 48
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b)
    return [Convert]::ToBase64String($b).Replace('+','-').Replace('/','_').TrimEnd('=')
}

if (-not (Test-Path $Template)) { throw "template not found: $Template" }

$op = if ($OperatorTokenOverride) { $OperatorTokenOverride } else { NewToken }
$ag = if ($AgentTokenOverride)    { $AgentTokenOverride }    else { NewToken }

$content = Get-Content -Path $Template -Raw -Encoding UTF8
$content = $content `
    -replace 'REPLACE_WITH_LONG_RANDOM_STRING_FOR_OPERATOR', $op `
    -replace 'REPLACE_WITH_LONG_RANDOM_STRING_FOR_AGENT',    $ag

Set-Content -Path $OutFile -Value $content -Encoding UTF8

Write-Host ""
Write-Host "===== TOKENS (save these!) ====="
Write-Host "OPERATOR_TOKEN  (give to Claude): $op"
Write-Host "AGENT_TOKEN     (put in start-agent.bat): $ag"
Write-Host "================================"
Write-Host ""
Write-Host "deploy file ready: $OutFile"
Write-Host ""
Write-Host "Next steps:"
Write-Host "  1. Upload $OutFile to your Tomcat webapps/ROOT/ as relay.jsp"
Write-Host "     (rename during upload, or after — Tomcat picks up the new file)"
Write-Host "  2. Edit start-agent.bat:"
Write-Host "       set AGENT_TOKEN=$ag"
Write-Host "       set RELAY_URL=http://<your-host>/relay.jsp"
Write-Host "  3. Double-click start-agent.bat"
Write-Host "  4. Send Claude the OPERATOR_TOKEN and the relay URL"
