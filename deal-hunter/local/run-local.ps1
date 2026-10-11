# run-local.ps1 - Deal Hunter on the owner's PC (Task Scheduler "ObsidianRiver-DealHunter", daily 06:52).
#
# Replaces the cloud routine (paused 2026-10-11): Facebook killed the copied-cookie session
# when the cloud run replayed it from a datacenter IP, logging the owner out. Here the
# browser profile lives on this PC and browses from the home connection.
#
#   1. lock, sync claude/deal-hunter-data      4. claude -p: value / check / draft (RUNBOOK 3-5)
#   2. scan (Python, logged-in profile)        5. digest -> Gmail API (send-only token)
#   3. login lost -> email the owner, stop     6. commit + push data/listings.json
#
# One-time setup (see README "Running on your own PC"):
#   powershell -File local\run-local.ps1 -Setup      # Facebook login + Gmail send consent
#
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File run-local.ps1 [-Setup] [-NoAgent]
param([switch]$Setup, [switch]$NoAgent)
# 'Continue', not 'Stop': in Windows PowerShell 5.1 a native command's stderr (git progress)
# becomes a terminating error under 'Stop'. Native results are checked via $LASTEXITCODE.
$ErrorActionPreference = 'Continue'
$Dh      = Split-Path -Parent $PSScriptRoot             # ...\claude-sandbox\deal-hunter
$Repo    = Split-Path -Parent $Dh
$Branch  = 'claude/deal-hunter-data'
# Not under AppData\Local: Microsoft Store Python redirects writes there into its package cache.
$WorkDir = Join-Path $env:USERPROFILE '.claude\dealhunter'
$RunLog  = Join-Path $WorkDir 'runner.log'
$Lock    = Join-Path $WorkDir 'run.lock'
$Budget  = 3.00   # 20 valuations with web search; raise if runs stop short
$env:DH_PROFILE_DIR = Join-Path $WorkDir 'browser-profile'
$env:PYTHONIOENCODING = 'utf-8'
New-Item -ItemType Directory -Force $WorkDir | Out-Null
$OutputEncoding = New-Object System.Text.UTF8Encoding $false
[Console]::OutputEncoding = $OutputEncoding

function Log([string]$m) { Add-Content -Path $RunLog -Encoding utf8 -Value ("{0} {1}" -f (Get-Date -Format 's'), $m) }
function Dh { & python -m dealhunter @args }
function Mail([string]$subject, [string]$body) {
    $f = Join-Path $WorkDir 'email-body.txt'
    Set-Content -Path $f -Value $body -Encoding utf8
    $r = Dh email --subject $subject --body-file $f
    $ok = $LASTEXITCODE -eq 0
    Log ("email '{0}': {1}" -f $subject, ($r -join ' '))
    Remove-Item $f -ErrorAction SilentlyContinue
    return $ok
}

Push-Location $Dh
try {
    if ($Setup) {
        Write-Host 'Step 1 of 2: a browser window opens. Log in to Facebook there (it closes itself).'
        Dh login
        Write-Host 'Step 2 of 2: a Google consent page opens. Allow "Send email on your behalf".'
        Dh email --auth
        exit 0
    }

    # --- 1. lock (stale after 60 min) + sync ---
    if ((Test-Path $Lock) -and ((Get-Date) - (Get-Item $Lock).LastWriteTime).TotalMinutes -lt 60) { Log 'skip: previous run still holds the lock'; exit 0 }
    Set-Content -Path $Lock -Value $PID
    & git -C $Repo fetch --quiet origin *> $null
    & git -C $Repo checkout --quiet $Branch *> $null
    & git -C $Repo pull --ff-only --quiet origin $Branch *> $null
    if ($LASTEXITCODE -ne 0) { Log 'warn: pull --ff-only failed; continuing on local branch' }
    & git -C $Repo merge --no-edit --quiet origin/main *> $null
    if ($LASTEXITCODE -ne 0) { & git -C $Repo merge --abort *> $null }

    # --- 2/3. scan ---
    $scan = (Dh scan) -join "`n"
    $code = $LASTEXITCODE
    Log ("scan exit={0}: {1}" -f $code, ($scan -replace '\s+', ' ').Substring(0, [Math]::Min(300, $scan.Length)))
    if ($code -eq 2) {
        $body = "Deal Hunter couldn't scan Marketplace this morning: its browser profile on your PC is no longer logged in to Facebook.`n`nTo fix it, open PowerShell and run:`n`n    powershell -ExecutionPolicy Bypass -File `"$PSCommandPath`" -Setup`n`nLog in to Facebook in the window that opens. Tomorrow's run picks it up."
        Mail 'Deal Hunter: Facebook login needed' $body | Out-Null
        exit 0
    }
    if ($code -ne 0) {
        Mail 'Deal Hunter: scan failed' ("The Marketplace scan exited with code $code.`n`n$scan`n`nRunner log: $RunLog") | Out-Null
        exit 0
    }

    # --- 4. agent: value / check / draft ---
    $todo = (Dh todo) -join "`n"
    if (-not $NoAgent -and $todo.Trim() -ne '[]') {
        foreach ($v in @('CLAUDECODE','CLAUDE_CODE_CHILD_SESSION','CLAUDE_CODE_ENTRYPOINT',
            'CLAUDE_CODE_SDK_HAS_OAUTH_REFRESH','CLAUDE_CODE_SDK_HAS_HOST_AUTH_REFRESH',
            'CLAUDE_CODE_SESSION_ID','CLAUDE_CODE_HOST_SESSION_ID','CLAUDE_AGENT_SDK_VERSION',
            'CLAUDE_PID','CLAUDE_CODE_MESSAGING_SOCKET','CLAUDE_CODE_MESSAGING_TOKEN',
            'CLAUDE_CODE_OAUTH_SCOPES','ANTHROPIC_BASE_URL',
            # A machine-level ANTHROPIC_API_KEY exists on this laptop; it would bill the API
            # instead of the subscription token below (same hygiene as the fleet scripts).
            'ANTHROPIC_API_KEY','ANTHROPIC_AUTH_TOKEN')) {
            Remove-Item "env:$v" -ErrorAction SilentlyContinue
        }
        $tokenFile = Join-Path $env:USERPROFILE '.claude\fleet-token.xml'
        if (-not $env:CLAUDE_CODE_OAUTH_TOKEN -and (Test-Path $tokenFile)) {
            $sec = Import-Clixml $tokenFile
            $env:CLAUDE_CODE_OAUTH_TOKEN = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
                [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec))
        }
        $allowed = @('Read', 'Grep', 'Glob', 'WebSearch', 'WebFetch',
            'Bash(python -m dealhunter *)', 'PowerShell(python -m dealhunter *)') -join ','
        $prompt = Get-Content (Join-Path $PSScriptRoot 'PROMPT.md') -Raw -Encoding utf8
        # Prompt on stdin: PowerShell 5.1 mangles long quoted native arguments.
        $out = $prompt | & claude -p --model sonnet --permission-mode dontAsk `
            --allowedTools $allowed --max-budget-usd $Budget `
            --output-format stream-json --verbose --setting-sources user 2>$null
        $exit = $LASTEXITCODE
        $cost = 0.0; $result = ''; $keySource = 'unknown'
        foreach ($line in $out) {
            try { $e = $line | ConvertFrom-Json } catch { continue }
            if ($e.type -eq 'system' -and $e.subtype -eq 'init' -and $e.apiKeySource) { $keySource = $e.apiKeySource }
            if ($e.type -eq 'result') {
                if ($null -ne $e.total_cost_usd) { $cost = [double]$e.total_cost_usd }
                if ($e.result) { $result = ($e.result -split "`r?`n")[-1] }
            }
        }
        Log ("agent exit={0}, cost=`${1:N2}, auth={2} :: {3}" -f $exit, $cost, $keySource, $result)
    }

    # --- 5. digest ---
    $digest = (Dh digest) -join "`n"
    if ($digest.Trim() -ne 'NOTHING NEW') {
        $deals = @((Dh deals) -join "`n" | ConvertFrom-Json)
        $subject = 'Deal Hunter: price changes'
        if ($deals.Count -gt 0) {
            $best = $deals | Sort-Object { [double]$_.valuation.value - [double]$_.price } -Descending | Select-Object -First 1
            $under = [int]([double]$best.valuation.value - [double]$best.price)
            $subject = 'Deal Hunter: {0} deal(s) - {1} ${2:N0} under' -f $deals.Count, $best.title, $under
        }
        if (Mail $subject $digest) { Dh mark-notified | Out-Null }
    } else { Log 'digest: nothing new' }
} finally {
    # --- 6. save (always, like RUNBOOK step 7) ---
    if (-not $Setup) {
        & git -C $Repo add -- deal-hunter/data/listings.json 2>$null
        & git -C $Repo -c user.name='deal-hunter-local' -c user.email='nat@obsidianriver.com' commit -q -m ("Deal Hunter local run {0}" -f (Get-Date -Format 'yyyy-MM-dd')) *> $null
        if ($LASTEXITCODE -eq 0) {
            & git -C $Repo pull --rebase --quiet origin $Branch *> $null
            & git -C $Repo push --quiet origin $Branch *> $null
            if ($LASTEXITCODE -eq 0) { Log 'saved: pushed listings.json' } else { Log 'warn: push failed; committed locally' }
        }
        Remove-Item $Lock -ErrorAction SilentlyContinue
    }
    Pop-Location
}
