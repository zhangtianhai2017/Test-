# agent.ps1 — Windows side of the command relay.
#
# Long-polls <RelayUrl>?action=pull, runs the returned script via
# powershell.exe, and POSTs stdout/stderr/exit back to ?action=result.
#
# Designed for no-admin environments:
#   - No registry / ExecutionPolicy changes (callers must use -Bypass)
#   - Temp files written to the working dir, not %TEMP%
#   - Network blips and HTTP errors do not crash the loop
#   - All output mirrored to .\agent.log so you can tail it post-mortem
#
# Usage (call via start-agent.bat, or):
#   powershell -NoProfile -ExecutionPolicy Bypass -File agent.ps1 `
#     -RelayUrl http://your-server/relay.jsp -AgentToken ABC...
#
# Or set $env:RELAY_URL and $env:AGENT_TOKEN before invoking.

param(
    [string]$RelayUrl   = $env:RELAY_URL,
    [string]$AgentToken = $env:AGENT_TOKEN,
    [string]$WorkDir    = (Get-Location).Path,
    [string]$LogFile    = (Join-Path (Get-Location).Path "agent.log"),
    [int]   $PullTimeoutSec = 40,
    [int]   $RetryDelaySec  = 5
)

if (-not $RelayUrl)   { throw "RelayUrl missing (set RELAY_URL or -RelayUrl)" }
if (-not $AgentToken) { throw "AgentToken missing (set AGENT_TOKEN or -AgentToken)" }

function Log {
    param([string]$Msg)
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Msg
    Write-Host $line
    try { Add-Content -Path $LogFile -Value $line -Encoding UTF8 } catch {}
}

# Tmp dir inside the work dir — avoids %TEMP% on locked-down profiles.
$TmpDir = Join-Path $WorkDir ".agent-tmp"
if (-not (Test-Path $TmpDir)) { New-Item -ItemType Directory -Path $TmpDir | Out-Null }

Log "agent start  relay=$RelayUrl  workdir=$WorkDir  logfile=$LogFile"
Log "press Ctrl+C to stop"

$headers = @{ "X-Token" = $AgentToken }

while ($true) {
    # ---- pull (server long-polls up to 30s) ------------------------------
    $job = $null
    try {
        $job = Invoke-RestMethod -Uri "$RelayUrl`?action=pull" `
            -Headers $headers -Method Get -TimeoutSec $PullTimeoutSec
    } catch {
        Log "pull error: $($_.Exception.Message) — retry in ${RetryDelaySec}s"
        Start-Sleep -Seconds $RetryDelaySec
        continue
    }

    if (-not $job -or -not $job.id) { continue }   # empty queue

    $jobId = $job.id
    $scriptLen = $job.script.Length
    Log "running $jobId  script.length=$scriptLen"

    $tmpScript = Join-Path $TmpDir "$jobId.ps1"
    $stdoutFile = Join-Path $TmpDir "$jobId.out"
    $stderrFile = Join-Path $TmpDir "$jobId.err"
    Set-Content -Path $tmpScript -Value $job.script -Encoding UTF8

    $proc = $null
    try {
        $proc = Start-Process -FilePath "powershell.exe" `
            -ArgumentList @("-NoProfile","-ExecutionPolicy","Bypass","-File",$tmpScript) `
            -RedirectStandardOutput $stdoutFile `
            -RedirectStandardError  $stderrFile `
            -WorkingDirectory $WorkDir `
            -NoNewWindow -PassThru
    } catch {
        Log "Start-Process failed: $($_.Exception.Message)"
    }

    $exit = -1
    if ($proc) {
        $timeoutSec = if ($job.timeout) { [int]$job.timeout } else { 600 }
        $finished = $proc.WaitForExit($timeoutSec * 1000)
        if (-not $finished) {
            try { $proc.Kill() } catch {}
            $exit = 124
            Log "$jobId TIMED OUT after ${timeoutSec}s"
        } else {
            $exit = $proc.ExitCode
        }
    }

    $stdout = ""
    $stderr = ""
    if (Test-Path $stdoutFile) { $stdout = (Get-Content $stdoutFile -Raw); if (-not $stdout) { $stdout = "" } }
    if (Test-Path $stderrFile) { $stderr = (Get-Content $stderrFile -Raw); if (-not $stderr) { $stderr = "" } }
    Remove-Item -Force -ErrorAction SilentlyContinue $tmpScript, $stdoutFile, $stderrFile

    $cap = 1000000
    if ($stdout.Length -gt $cap) { $stdout = $stdout.Substring(0, $cap) + "`n[truncated]" }
    if ($stderr.Length -gt $cap) { $stderr = $stderr.Substring(0, $cap) + "`n[truncated]" }

    $body = @{
        id     = $jobId
        stdout = $stdout
        stderr = $stderr
        exit   = $exit
    } | ConvertTo-Json -Depth 3 -Compress

    # ---- POST result, retry briefly on transient failure -----------------
    $reported = $false
    for ($attempt = 1; $attempt -le 3; $attempt++) {
        try {
            Invoke-RestMethod -Uri "$RelayUrl`?action=result" `
                -Headers $headers -Method Post -ContentType "application/json" `
                -Body $body -TimeoutSec 30 | Out-Null
            $reported = $true
            break
        } catch {
            Log "result POST attempt $attempt failed: $($_.Exception.Message)"
            Start-Sleep -Seconds $attempt
        }
    }
    if ($reported) {
        Log "reported $jobId  exit=$exit  stdout.len=$($stdout.Length)  stderr.len=$($stderr.Length)"
    } else {
        Log "GIVING UP on $jobId after 3 POST attempts — result lost"
    }
}
