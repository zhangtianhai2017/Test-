# agent.ps1 — Windows side of the command relay.
#
# Long-polls <RelayUrl>?action=pull, executes the returned PowerShell
# script via `powershell -Command`, and POSTs stdout/stderr/exit back
# to <RelayUrl>?action=result.
#
# Usage:
#   $env:RELAY_URL   = "http://your-server/relay.jsp"
#   $env:AGENT_TOKEN = "the-agent-token-from-relay.jsp"
#   .\agent.ps1
#
# Or pass via -RelayUrl / -AgentToken. Run in a long-lived terminal;
# Ctrl+C to stop. No external dependencies — uses Invoke-RestMethod.

param(
    [string]$RelayUrl   = $env:RELAY_URL,
    [string]$AgentToken = $env:AGENT_TOKEN,
    [string]$WorkDir    = (Get-Location).Path
)

if (-not $RelayUrl)   { throw "RelayUrl missing (set RELAY_URL or -RelayUrl)" }
if (-not $AgentToken) { throw "AgentToken missing (set AGENT_TOKEN or -AgentToken)" }

Write-Host "[agent] relay=$RelayUrl  workdir=$WorkDir"
Write-Host "[agent] press Ctrl+C to stop"

$headers = @{ "X-Token" = $AgentToken }

while ($true) {
    # ---- pull (long-poll up to 30s server-side) ----
    try {
        $job = Invoke-RestMethod -Uri "$RelayUrl`?action=pull" `
            -Headers $headers -Method Get -TimeoutSec 40
    } catch {
        Write-Host "[agent] pull error: $($_.Exception.Message)  retrying in 5s"
        Start-Sleep -Seconds 5
        continue
    }

    if (-not $job.id) {
        # empty queue, loop immediately (server already blocked 30s)
        continue
    }

    Write-Host "[agent] running $($job.id)  script.length=$($job.script.Length)"
    $tmpScript = Join-Path $env:TEMP "relay-$($job.id).ps1"
    Set-Content -Path $tmpScript -Value $job.script -Encoding UTF8

    $stdoutFile = Join-Path $env:TEMP "relay-$($job.id).out"
    $stderrFile = Join-Path $env:TEMP "relay-$($job.id).err"

    $proc = Start-Process -FilePath "powershell.exe" `
        -ArgumentList @("-NoProfile","-ExecutionPolicy","Bypass","-File",$tmpScript) `
        -RedirectStandardOutput $stdoutFile `
        -RedirectStandardError  $stderrFile `
        -WorkingDirectory $WorkDir `
        -NoNewWindow -PassThru

    $timeout = if ($job.timeout) { [int]$job.timeout } else { 600 }
    $finished = $proc.WaitForExit($timeout * 1000)
    if (-not $finished) {
        try { $proc.Kill() } catch {}
        $exit = 124
    } else {
        $exit = $proc.ExitCode
    }

    $stdout = if (Test-Path $stdoutFile) { Get-Content $stdoutFile -Raw } else { "" }
    $stderr = if (Test-Path $stderrFile) { Get-Content $stderrFile -Raw } else { "" }
    Remove-Item -Force -ErrorAction SilentlyContinue $tmpScript, $stdoutFile, $stderrFile

    if (-not $stdout) { $stdout = "" }
    if (-not $stderr) { $stderr = "" }

    # truncate to a sane max (1 MB) to stop a runaway log from blowing memory
    $cap = 1_000_000
    if ($stdout.Length -gt $cap) { $stdout = $stdout.Substring(0, $cap) + "`n[truncated]" }
    if ($stderr.Length -gt $cap) { $stderr = $stderr.Substring(0, $cap) + "`n[truncated]" }

    $body = @{
        id     = $job.id
        stdout = $stdout
        stderr = $stderr
        exit   = $exit
    } | ConvertTo-Json -Depth 3 -Compress

    try {
        Invoke-RestMethod -Uri "$RelayUrl`?action=result" `
            -Headers $headers -Method Post -ContentType "application/json" `
            -Body $body -TimeoutSec 30 | Out-Null
        Write-Host "[agent] reported $($job.id)  exit=$exit  stdout.len=$($stdout.Length)"
    } catch {
        Write-Host "[agent] result POST failed: $($_.Exception.Message)"
    }
}
