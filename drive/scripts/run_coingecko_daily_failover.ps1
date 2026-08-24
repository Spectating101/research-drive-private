param(
    [int]$RandomDelayMaxSec = $(if ($env:COINGECKO_FAILOVER_RANDOM_DELAY_MAX_SEC) { [int]$env:COINGECKO_FAILOVER_RANDOM_DELAY_MAX_SEC } else { 1800 })
)

$ErrorActionPreference = "Stop"

$ScriptPath = $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent (Split-Path -Parent $ScriptPath)
$PricePanel = Join-Path $Root "data_lake\crypto_pipeline\exports\price_panel_clean.csv"
$StateDir = if ($env:COINGECKO_FAILOVER_STATE_DIR) {
    $env:COINGECKO_FAILOVER_STATE_DIR
} else {
    Join-Path $Root "data_lake\crypto_pipeline\failover_state"
}
$MachineId = if ($env:COINGECKO_MACHINE_ID) {
    $env:COINGECKO_MACHINE_ID
} elseif ($env:COMPUTERNAME) {
    $env:COMPUTERNAME
} elseif ($env:HOSTNAME) {
    $env:HOSTNAME
} else {
    [System.Net.Dns]::GetHostName()
}
$Today = Get-Date -Format "yyyy-MM-dd"
$NowUtc = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
$AttemptsDir = Join-Path $StateDir "attempts\$Today"
$SuccessDir = Join-Path $StateDir "success\$Today"
$MachinesDir = Join-Path $StateDir "machines"
$MutexName = "Local\SharpeRenaissanceCoinGeckoDailyFailover"

foreach ($dir in @($StateDir, $AttemptsDir, $SuccessDir, $MachinesDir)) {
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
}

function Write-State {
    param(
        [string]$Path,
        [string]$Status
    )

    $payload = [ordered]@{
        machine_id    = $MachineId
        date          = $Today
        status        = $Status
        timestamp_utc = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    }

    $payload | ConvertTo-Json | Set-Content -Path $Path -Encoding UTF8
}

function Test-PanelHasToday {
    if (-not (Test-Path -LiteralPath $PricePanel)) {
        return $false
    }

    $tail = Get-Content -LiteralPath $PricePanel -Tail 1
    return $tail -match "^$Today,"
}

function Invoke-PythonScript {
    param(
        [string[]]$Arguments
    )

    $candidates = @()
    if ($env:COINGECKO_PYTHON_BIN) {
        $candidates += $env:COINGECKO_PYTHON_BIN
    }
    $candidates += @(
        "python",
        "py",
        "python3",
        "C:\Users\user\AppData\Local\Cite-Agent\venv\Scripts\python.exe"
    )

    foreach ($candidate in $candidates) {
        $cmd = Get-Command $candidate -ErrorAction SilentlyContinue
        if (-not $cmd) {
            continue
        }

        if ($candidate -eq "py") {
            & $cmd.Source -3 @Arguments | Out-Host
        } else {
            & $cmd.Source @Arguments | Out-Host
        }
        return [int]$LASTEXITCODE
    }

    throw "Python launcher not found. Install Python 3 and ensure 'python', 'py', or 'python3' is on PATH."
}

$mutex = New-Object System.Threading.Mutex($false, $MutexName)
$hasLock = $false

try {
    $hasLock = $mutex.WaitOne(0)
    if (-not $hasLock) {
        Write-Host "[skip] local failover mutex is already held on this machine"
        exit 0
    }

    Write-State -Path (Join-Path $MachinesDir "$MachineId.json") -Status "heartbeat"
    Write-State -Path (Join-Path $AttemptsDir "$MachineId.json") -Status "scheduled"

    if (Test-PanelHasToday) {
        Write-Host "[skip] $Today is already present in price_panel_clean.csv"
        Write-State -Path (Join-Path $SuccessDir "$MachineId.skip.json") -Status "already_present"
        exit 0
    }

    if ($RandomDelayMaxSec -gt 0) {
        $delaySec = Get-Random -Minimum 0 -Maximum ($RandomDelayMaxSec + 1)
        if ($delaySec -gt 0) {
            Write-Host "[wait] sleeping $delaySec s before attempting daily update"
            Start-Sleep -Seconds $delaySec
        }
    }

    if (Test-PanelHasToday) {
        Write-Host "[skip] $Today was synced by another machine during the delay window"
        Write-State -Path (Join-Path $SuccessDir "$MachineId.skip.json") -Status "seen_after_delay"
        exit 0
    }

    Write-Host "[run] machine=$MachineId date=$Today mode=daily api=public"
    $exitCode = Invoke-PythonScript -Arguments @(
        (Join-Path $Root "scripts\coingecko_panel_update.py"),
        "--mode",
        "daily",
        "--use-public-api"
    )

    if ($exitCode -ne 0) {
        throw "Updater exited with code $exitCode"
    }

    if (Test-PanelHasToday) {
        Write-Host "[ok] $Today daily snapshot completed on $MachineId"
        Write-State -Path (Join-Path $SuccessDir "$MachineId.json") -Status "success"
        exit 0
    }

    Write-State -Path (Join-Path $AttemptsDir "$MachineId.failed.json") -Status "missing_after_run"
    throw "Updater exited but today's row is still missing from price_panel_clean.csv"
}
finally {
    if ($hasLock) {
        $mutex.ReleaseMutex() | Out-Null
    }
    $mutex.Dispose()
}
