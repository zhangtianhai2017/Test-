# agent.ps1 v3 — GitHub-relayed command agent.
#
# Uses the public claude-relay branch as the channel:
#   inbox.json  (claude pushes commands here)
#   outbox.json (this agent pushes results here)
#
# Auth model:
#   - inbox is read via public raw URL (no auth needed)
#   - outbox push uses your locally cached git credentials (Windows
#     Credential Manager). If you've ever git-push'd this repo from
#     this Windows account, you're set. If not, the first push will
#     pop a credential prompt or fail; instructions below.
#
# No PAT to manage. No tokens to edit. Just run start-agent.bat.

param(
    [string]$RepoOwner  = "zhangtianhai2017",
    [string]$RepoName   = "Test-",
    [string]$Branch     = "claude-relay",
    [string]$RelayDir   = (Join-Path (Get-Location).Path ".relay-clone"),
    [string]$WorkDir    = (Get-Location).Path,
    [int]   $PollSec    = 5
)

$ErrorActionPreference = "Continue"
$RepoUrl = "https://github.com/$RepoOwner/$RepoName.git"
$LogFile = Join-Path $WorkDir "agent.log"
$UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

function Log {
    param([string]$Msg)
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Msg
    Write-Host $line
    try { Add-Content -Path $LogFile -Value $line -Encoding UTF8 } catch {}
}

# ---- one-time clone of the relay branch -------------------------------------
if (-not (Test-Path (Join-Path $RelayDir ".git"))) {
    Log "first run — cloning $RepoUrl ($Branch) into $RelayDir"
    git clone --branch $Branch --single-branch --depth 50 $RepoUrl $RelayDir
    if ($LASTEXITCODE -ne 0) {
        Log "FATAL: clone failed. Is git installed and is the network OK?"
        exit 1
    }
    Push-Location $RelayDir
    git config user.email "agent@local"
    git config user.name  "relay-agent"
    # make slow / flaky GitHub access more tolerant (China network)
    git config http.lowSpeedLimit  1000
    git config http.lowSpeedTime   60
    git config http.postBuffer     524288000
    Pop-Location
}

# ---- main loop --------------------------------------------------------------
$tmpDir = Join-Path $WorkDir ".agent-tmp"
if (-not (Test-Path $tmpDir)) { New-Item -ItemType Directory -Path $tmpDir | Out-Null }

Log "agent ready — polling $RepoUrl branch=$Branch every ${PollSec}s"
Log "press Ctrl+C to stop"

while ($true) {
    Push-Location $RelayDir

    # --- pull latest (tolerate network blips) ---
    $fetchOut = (git fetch origin $Branch 2>&1) -join " "
    if ($LASTEXITCODE -eq 0) {
        git reset --hard "origin/$Branch" 2>&1 | Out-Null
    } else {
        Log "fetch failed (will retry next loop): $fetchOut"
        Pop-Location
        Start-Sleep -Seconds 10
        continue
    }

    # --- read inbox & outbox ---
    $inbox  = $null
    $outbox = $null
    try {
        if (Test-Path inbox.json)  { $inbox  = Get-Content inbox.json  -Raw -Encoding UTF8 | ConvertFrom-Json }
        if (Test-Path outbox.json) { $outbox = Get-Content outbox.json -Raw -Encoding UTF8 | ConvertFrom-Json }
    } catch { Log "JSON parse error: $($_.Exception.Message)" }

    # --- decide: is there a new command? ---
    $newJob = $false
    if ($inbox -and $inbox.id -and $inbox.id.Length -gt 0) {
        if (-not ($outbox -and $outbox.id -eq $inbox.id)) {
            $newJob = $true
        }
    }

    if (-not $newJob) {
        Pop-Location
        Start-Sleep -Seconds $PollSec
        continue
    }

    # --- execute ---
    $jobId = $inbox.id
    $scriptText = [string]$inbox.script
    $timeoutSec = if ($inbox.timeout) { [int]$inbox.timeout } else { 600 }
    Log "executing $jobId  script.length=$($scriptText.Length)  timeout=${timeoutSec}s"

    $tmpScript  = Join-Path $tmpDir "$jobId.ps1"
    $stdoutFile = Join-Path $tmpDir "$jobId.out"
    $stderrFile = Join-Path $tmpDir "$jobId.err"
    Set-Content -Path $tmpScript -Value $scriptText -Encoding UTF8

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
        $finished = $proc.WaitForExit($timeoutSec * 1000)
        if (-not $finished) {
            try { $proc.Kill() } catch {}
            $exit = 124
            Log "$jobId TIMED OUT after ${timeoutSec}s"
        } else {
            $exit = $proc.ExitCode
        }
    }

    $stdout = ""; $stderr = ""
    if (Test-Path $stdoutFile) { $stdout = (Get-Content $stdoutFile -Raw); if (-not $stdout) { $stdout = "" } }
    if (Test-Path $stderrFile) { $stderr = (Get-Content $stderrFile -Raw); if (-not $stderr) { $stderr = "" } }
    Remove-Item -Force -ErrorAction SilentlyContinue $tmpScript, $stdoutFile, $stderrFile

    # cap each at 200 KB so commits don't blow up; tail kept (more useful for error diag)
    $cap = 200000
    if ($stdout.Length -gt $cap) { $stdout = "[truncated]`n" + $stdout.Substring($stdout.Length - $cap) }
    if ($stderr.Length -gt $cap) { $stderr = "[truncated]`n" + $stderr.Substring($stderr.Length - $cap) }

    $result = [ordered]@{
        id           = $jobId
        stdout       = $stdout
        stderr       = $stderr
        exit         = $exit
        completed_at = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    }
    $resultJson = $result | ConvertTo-Json -Depth 3 -Compress
    Set-Content -Path outbox.json -Value $resultJson -Encoding UTF8

    # --- commit + push (distinguish network errors from non-ff) ---
    $pushed = $false
    for ($attempt = 1; $attempt -le 5; $attempt++) {
        git add outbox.json 2>&1 | Out-Null
        git commit --allow-empty -m "relay-agent: result $jobId" 2>&1 | Out-Null
        $pushOut = (git push origin $Branch 2>&1) -join "`n"
        $pushExit = $LASTEXITCODE
        if ($pushExit -eq 0) { $pushed = $true; break }

        Log "push attempt $attempt failed (exit=$pushExit): $pushOut"

        if ($pushOut -match "Username|Authentication|denied|403|401|could not read") {
            Log "PUSH AUTH FAILED. fix: run interactively once:"
            Log "  cd $RelayDir"
            Log "  git push origin $Branch"
            Log "  (complete the GitHub login popup, then restart this agent)"
            break
        }

        if ($pushOut -match "Could not connect|Failed to connect|Connection refused|Connection timed out|Could not resolve host|TLS|SSL|GnuTLS|RPC failed") {
            Log "network error — sleeping 15s then retrying (commit stays local)"
            Start-Sleep -Seconds 15
            continue   # keep local commit; just try the push again
        }

        # genuine non-ff: someone else pushed. rebase by saving outbox, resetting, replaying.
        Log "non-fast-forward — rebasing outbox onto remote"
        git fetch origin $Branch 2>&1 | Out-Null
        git reset --hard "origin/$Branch" 2>&1 | Out-Null
        Set-Content -Path outbox.json -Value $resultJson -Encoding UTF8
    }

    if ($pushed) {
        Log "completed $jobId  exit=$exit  stdout.len=$($stdout.Length)  stderr.len=$($stderr.Length)  -> pushed"
    } else {
        Log "FAILED to push $jobId — will retry on next loop"
    }

    Pop-Location
    Start-Sleep -Seconds $PollSec
}
