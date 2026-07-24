#Requires -Version 5.1
<#
.SYNOPSIS
  Supervised launcher for the thin Windows YZU remote_worker (claim loop only).

.DESCRIPTION
  Loads YZU_WORKER_CONTROL_TOKEN from the process environment or a protected
  local token file, then runs drive/scripts/yzu_cluster/remote_worker.py in a
  restart loop. Does not submit or approve jobs. Token value is never printed,
  hashed, or fingerprinted — only a source label (env|file) is logged.
#>
param(
    [Parameter(Mandatory = $true)][string]$ControllerUrl,
    [Parameter(Mandatory = $true)][string]$WorkerId,
    [string]$RepoRoot = "C:\cw\Sharpe-Renaissance",
    [string]$Pool = "windows_lab",
    [string]$Capabilities = "http,python",
    [string]$Spool = ".yzu-worker-spool",
    [string]$TokenFile = "",
    [string]$PythonExe = "py",
    [string]$LogDir = "",
    [int]$RestartDelaySeconds = 30,
    [int]$PollSeconds = 5,
    [int]$LeaseSeconds = 120,
    [int]$HeartbeatSeconds = 30
)

$ErrorActionPreference = "Stop"

function Write-Info([string]$Message) {
    $ts = Get-Date -Format "yyyy-MM-ddTHH:mm:ss"
    Write-Host "[$ts] $Message"
}

function Resolve-WorkerToken {
    param(
        [string]$PreferredFile
    )
    $fromEnv = [string]$env:YZU_WORKER_CONTROL_TOKEN
    if ($fromEnv -and $fromEnv.Trim().Length -gt 0) {
        return @{ Token = $fromEnv.Trim(); Source = "env" }
    }

    $candidates = @()
    if ($PreferredFile) { $candidates += $PreferredFile }
    $candidates += (Join-Path $RepoRoot ".yzu-worker-token")
    $candidates += (Join-Path $RepoRoot "drive\.yzu-worker-token")

    foreach ($path in $candidates) {
        if (-not $path) { continue }
        if (-not (Test-Path -LiteralPath $path)) { continue }
        $raw = (Get-Content -LiteralPath $path -Raw -ErrorAction Stop).Trim()
        if (-not $raw) { continue }
        # Allow KEY=value lines without printing secrets.
        if ($raw -match '(?m)^\s*YZU_WORKER_CONTROL_TOKEN\s*=\s*(.+)\s*$') {
            $raw = $Matches[1].Trim().Trim('"').Trim("'")
        }
        if ($raw.Length -gt 0) {
            # Source label only — never include path or secret material in logs.
            return @{ Token = $raw; Source = "file" }
        }
    }

    throw "YZU_WORKER_CONTROL_TOKEN missing. Set the environment variable or create a protected local token file (.yzu-worker-token)."
}

$RepoRoot = (Resolve-Path -LiteralPath $RepoRoot).Path
$WorkerScript = Join-Path $RepoRoot "drive\scripts\yzu_cluster\remote_worker.py"
if (-not (Test-Path -LiteralPath $WorkerScript)) {
    throw "remote_worker.py not found at $WorkerScript (thin checkout required)"
}

$DriveRoot = Join-Path $RepoRoot "drive"
$RepoRootArg = $DriveRoot
if (-not (Test-Path -LiteralPath $DriveRoot)) {
    $RepoRootArg = $RepoRoot
}

if (-not $LogDir) {
    $LogDir = Join-Path $RepoRoot "logs\yzu-remote-worker"
}
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$StdoutLog = Join-Path $LogDir "$WorkerId.stdout.log"
$StderrLog = Join-Path $LogDir "$WorkerId.stderr.log"
$SupervisorLog = Join-Path $LogDir "$WorkerId.supervisor.log"

$tokenInfo = Resolve-WorkerToken -PreferredFile $TokenFile
$env:YZU_WORKER_CONTROL_TOKEN = $tokenInfo.Token
# Presence + source label only — never echo, hash, or fingerprint the secret.
Write-Info "token source=$($tokenInfo.Source) present=true"

$pythonPathParts = @(
    $RepoRoot,
    (Join-Path $RepoRoot "kernel"),
    (Join-Path $RepoRoot "drive")
) | Where-Object { Test-Path -LiteralPath $_ }
$env:PYTHONPATH = ($pythonPathParts -join ";")

$spoolPath = $Spool
if (-not [System.IO.Path]::IsPathRooted($spoolPath)) {
    $spoolPath = Join-Path $RepoRootArg $Spool
}

$workerArgs = @(
    $WorkerScript,
    "--controller", $ControllerUrl,
    "--repo-root", $RepoRootArg,
    "--worker-id", $WorkerId,
    "--pool", $Pool,
    "--capabilities", $Capabilities,
    "--spool", $spoolPath,
    "--poll-seconds", "$PollSeconds",
    "--lease-seconds", "$LeaseSeconds",
    "--heartbeat-seconds", "$HeartbeatSeconds"
)

Write-Info "starting supervised remote_worker worker_id=$WorkerId pool=$Pool controller=$ControllerUrl"
Write-Info "script=$WorkerScript spool=$spoolPath"
Add-Content -LiteralPath $SupervisorLog -Value "$(Get-Date -Format o) supervise_start worker_id=$WorkerId"

while ($true) {
    $code = 1
    try {
        $argLine = ($workerArgs | ForEach-Object {
            if ($_ -match '[\s"]') { '"' + ($_ -replace '"', '\"') + '"' } else { $_ }
        }) -join " "
        # Append-only logs; token is in process env only (never on the command line).
        $cmd = "`"$PythonExe`" $argLine >> `"$StdoutLog`" 2>> `"$StderrLog`""
        $proc = Start-Process -FilePath "cmd.exe" `
            -ArgumentList @("/c", $cmd) `
            -WorkingDirectory $RepoRoot `
            -NoNewWindow `
            -PassThru `
            -Wait
        $code = $proc.ExitCode
    } catch {
        $code = 1
        Add-Content -LiteralPath $SupervisorLog -Value "$(Get-Date -Format o) supervise_launch_error=$($_.Exception.Message)"
    }
    $line = "$(Get-Date -Format o) supervisor_restart exit=$code delay=${RestartDelaySeconds}s"
    Add-Content -LiteralPath $SupervisorLog -Value $line
    Write-Info $line
    Start-Sleep -Seconds ([Math]::Max(5, $RestartDelaySeconds))
}
