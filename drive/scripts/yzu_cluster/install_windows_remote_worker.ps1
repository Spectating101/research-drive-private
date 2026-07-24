#Requires -Version 5.1
<#
.SYNOPSIS
  Operator bootstrap: install / status / stop / uninstall a supervised Windows
  Task Scheduler entry for the thin YZU remote_worker.

.DESCRIPTION
  Makes an existing thin checkout (remote_worker.py present) continuously
  available to claim http_manifest jobs. Does not submit or approve jobs.

  ContinuityProfile:
    InteractiveLogon (default) — AtLogOn + Interactive principal; safe for
      non-admin installs. Requires a signed-in user session.
    NonInteractiveStartup (opt-in) — AtStartup + S4U principal for always-ready
      lab hosts with nobody signed in. Requires Administrator rights.

  Token is resolved only from YZU_WORKER_CONTROL_TOKEN or a protected local
  file; the secret is never written to the scheduled task command line,
  never echoed, and never fingerprinted in logs.
#>
param(
    [ValidateSet("Install", "Status", "Stop", "Uninstall")]
    [string]$Mode = "Install",

    [ValidateSet("InteractiveLogon", "NonInteractiveStartup")]
    [string]$ContinuityProfile = "InteractiveLogon",

    [string]$ControllerUrl = "",
    [string]$WorkerId = "",
    [string]$RepoRoot = "C:\cw\Sharpe-Renaissance",
    [string]$Pool = "windows_lab",
    [string]$Capabilities = "http,python",
    [string]$Spool = ".yzu-worker-spool",
    [string]$TokenFile = "",
    [string]$PythonExe = "py",
    [string]$TaskName = "",
    [int]$RestartDelaySeconds = 30,
    [int]$StartupDelaySeconds = 60,
    [switch]$StartNow
)

$ErrorActionPreference = "Stop"

function Write-Info([string]$Message) {
    Write-Host $Message
}

function Resolve-RepoRoot([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) {
        throw "RepoRoot not found: $Path"
    }
    return (Resolve-Path -LiteralPath $Path).Path
}

function Default-WorkerId {
    $hostName = $env:COMPUTERNAME
    if ($hostName) { return $hostName.ToLowerInvariant() }
    return "windows-worker"
}

function Resolve-TaskName([string]$Name, [string]$Id) {
    if ($Name) { return $Name }
    return "YzuWindowsRemoteWorker-$Id"
}

function Assert-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw @"
NonInteractiveStartup requires an elevated Administrator PowerShell session.
Re-run from 'Run as administrator', or use -ContinuityProfile InteractiveLogon
(the default) for non-admin installs that start at interactive logon only.
"@
    }
}

function Assert-ThinWorker([string]$Root) {
    $worker = Join-Path $Root "drive\scripts\yzu_cluster\remote_worker.py"
    if (-not (Test-Path -LiteralPath $worker)) {
        throw "Thin worker missing remote_worker.py at $worker"
    }
    $runner = Join-Path $Root "drive\scripts\yzu_cluster\run_windows_remote_worker.ps1"
    if (-not (Test-Path -LiteralPath $runner)) {
        throw "Continuity runner missing at $runner — sync this worktree/checkout first"
    }
    $py = Get-Command $PythonExe -ErrorAction SilentlyContinue
    if (-not $py) {
        throw "Python launcher '$PythonExe' not found on PATH"
    }
    return @{ WorkerScript = $worker; RunnerScript = $runner }
}

function Protect-TokenFile([string]$Path) {
    # Best-effort ACL lockdown for the worker account; ignore failures on locked-down SKUs.
    try {
        icacls $Path /inheritance:r /grant:r "$($env:USERNAME):(R)" | Out-Null
    } catch {
        Write-Info "token: warning could not tighten ACL on file (continuing)"
    }
}

function Assert-TokenAvailable([string]$Root, [string]$PreferredFile) {
    $defaultFile = Join-Path $Root ".yzu-worker-token"
    $candidates = @()
    if ($PreferredFile) { $candidates += $PreferredFile }
    $candidates += $defaultFile
    $candidates += (Join-Path $Root "drive\.yzu-worker-token")

    foreach ($path in $candidates) {
        if ($path -and (Test-Path -LiteralPath $path)) {
            $raw = (Get-Content -LiteralPath $path -Raw).Trim()
            if ($raw) {
                # Presence only — never print, hash, or fingerprint the secret.
                Write-Info "token: present (source=file)"
                return
            }
        }
    }

    $envToken = [string]$env:YZU_WORKER_CONTROL_TOKEN
    if ($envToken -and $envToken.Trim().Length -gt 0) {
        $trimmed = $envToken.Trim()
        $target = if ($PreferredFile) { $PreferredFile } else { $defaultFile }
        # Persist for Task Scheduler across reboot/logon (install-session env does not survive).
        # Never echo or fingerprint the secret; keep it out of the task command line.
        Set-Content -LiteralPath $target -Value $trimmed -Encoding ascii
        Protect-TokenFile -Path $target
        Write-Info "token: present (source=env->file)"
        Write-Info "token: wrote protected local file for continuity (value never logged)"
        return
    }

    throw "YZU_WORKER_CONTROL_TOKEN not available. Set the env var in this session or create a protected .yzu-worker-token file under RepoRoot (never commit it)."
}

function Get-TaskState([string]$Name) {
    try {
        return Get-ScheduledTask -TaskName $Name -ErrorAction Stop
    } catch {
        return $null
    }
}

function Show-Status([string]$Name, [string]$Root, [string]$Id) {
    $task = Get-TaskState -Name $Name
    if (-not $task) {
        Write-Info "task: missing ($Name)"
        return 1
    }
    $info = Get-ScheduledTaskInfo -TaskName $Name
    Write-Info "task: $($task.TaskName)"
    Write-Info "state: $($task.State)"
    Write-Info "last_result: $($info.LastTaskResult)"
    Write-Info "last_run: $($info.LastRunTime)"
    Write-Info "next_run: $($info.NextRunTime)"
    try {
        $trig = @($task.Triggers) | ForEach-Object { $_.CimClass.CimClassName }
        Write-Info "triggers: $($trig -join ',')"
        Write-Info "logon_type: $($task.Principal.LogonType)"
        Write-Info "run_level: $($task.Principal.RunLevel)"
        Write-Info "user_id: $($task.Principal.UserId)"
    } catch {
        # Older SKUs may omit CIM details; status still useful without them.
    }
    $logDir = Join-Path $Root "logs\yzu-remote-worker"
    $sup = Join-Path $logDir "$Id.supervisor.log"
    if (Test-Path -LiteralPath $sup) {
        Write-Info "supervisor_log: $sup"
        Get-Content -LiteralPath $sup -Tail 5 | ForEach-Object { Write-Info "  $_" }
    } else {
        Write-Info "supervisor_log: (none yet)"
    }
    return 0
}

function Stop-WorkerTask([string]$Name) {
    $task = Get-TaskState -Name $Name
    if (-not $task) {
        Write-Info "task: missing ($Name) — nothing to stop"
        return 0
    }
    if ($task.State -eq "Running") {
        Stop-ScheduledTask -TaskName $Name -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 1
    }
    # Also stop orphaned python remote_worker processes for this task's working tree when possible.
    Write-Info "task: stop requested ($Name)"
    Show-Status -Name $Name -Root $RepoRoot -Id $WorkerId | Out-Null
    return 0
}

function Uninstall-WorkerTask([string]$Name) {
    $task = Get-TaskState -Name $Name
    if (-not $task) {
        Write-Info "task: already absent ($Name)"
        return 0
    }
    if ($task.State -eq "Running") {
        Stop-ScheduledTask -TaskName $Name -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 1
    }
    Unregister-ScheduledTask -TaskName $Name -Confirm:$false
    Write-Info "task: uninstalled ($Name)"
    return 0
}

function New-ContinuityTriggerAndPrincipal {
    param(
        [ValidateSet("InteractiveLogon", "NonInteractiveStartup")]
        [string]$Profile,
        [int]$DelaySeconds
    )

    if ($Profile -eq "NonInteractiveStartup") {
        Assert-Administrator
        $trigger = New-ScheduledTaskTrigger -AtStartup
        if ($DelaySeconds -gt 0) {
            # Give Tailscale / NIC time to come up on lab hosts with nobody signed in.
            $trigger.Delay = "PT${DelaySeconds}S"
        }
        # S4U = noninteractive principal (run whether user is signed in or not), no stored password.
        $principal = New-ScheduledTaskPrincipal `
            -UserId $env:USERNAME `
            -LogonType S4U `
            -RunLevel Highest
        return @{
            Trigger = $trigger
            Principal = $principal
            Profile = $Profile
            Note = "AtStartup + S4U (noninteractive; Administrator install)"
        }
    }

    # Safe default: interactive logon only — no admin elevation required.
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
    $principal = New-ScheduledTaskPrincipal `
        -UserId $env:USERNAME `
        -LogonType Interactive `
        -RunLevel Limited
    return @{
        Trigger = $trigger
        Principal = $principal
        Profile = "InteractiveLogon"
        Note = "AtLogOn + Interactive (non-admin safe; needs signed-in session)"
    }
}

function Install-WorkerTask {
    if (-not $ControllerUrl) {
        throw "ControllerUrl is required for Install (example: http://<optiplex-tailscale-ip>:8780)"
    }
    $root = Resolve-RepoRoot -Path $RepoRoot
    $script:RepoRoot = $root
    if (-not $WorkerId) { $script:WorkerId = Default-WorkerId }
    $name = Resolve-TaskName -Name $TaskName -Id $WorkerId
    $paths = Assert-ThinWorker -Root $root
    Assert-TokenAvailable -Root $root -PreferredFile $TokenFile

    $tokenFileArg = ""
    if ($TokenFile) {
        $tokenFileArg = " -TokenFile `"$TokenFile`""
    }

    # Token stays out of the scheduled command line: runner resolves env/file at start.
    $argument = "-NoProfile -ExecutionPolicy Bypass -File `"$($paths.RunnerScript)`" -ControllerUrl `"$ControllerUrl`" -WorkerId `"$WorkerId`" -RepoRoot `"$root`" -Pool `"$Pool`" -Capabilities `"$Capabilities`" -Spool `"$Spool`" -PythonExe `"$PythonExe`" -RestartDelaySeconds $RestartDelaySeconds$tokenFileArg"

    $action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $argument
    $tp = New-ContinuityTriggerAndPrincipal -Profile $ContinuityProfile -DelaySeconds $StartupDelaySeconds
    $settings = New-ScheduledTaskSettingsSet `
        -StartWhenAvailable `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -DontStopOnIdleEnd `
        -MultipleInstances IgnoreNew `
        -RestartCount 3 `
        -RestartInterval (New-TimeSpan -Minutes 1) `
        -ExecutionTimeLimit ([TimeSpan]::Zero)

    Register-ScheduledTask `
        -TaskName $name `
        -Action $action `
        -Trigger $tp.Trigger `
        -Settings $settings `
        -Principal $tp.Principal `
        -Description "YZU thin remote_worker continuity (claim-only; does not submit jobs; profile=$($tp.Profile))" `
        -Force | Out-Null

    Write-Info "task: installed ($name)"
    Write-Info "continuity_profile: $($tp.Profile)"
    Write-Info "continuity_note: $($tp.Note)"
    Write-Info "worker_id: $WorkerId"
    Write-Info "pool: $Pool"
    Write-Info "capabilities: $Capabilities"
    Write-Info "controller: $ControllerUrl"
    Write-Info "repo: $root"
    Write-Info "runner: $($paths.RunnerScript)"
    Write-Info "note: does not submit or approve jobs; worker only claims when work exists"

    if ($StartNow) {
        Start-ScheduledTask -TaskName $name
        Start-Sleep -Seconds 2
        Write-Info "task: start requested"
    }
    return (Show-Status -Name $name -Root $root -Id $WorkerId)
}

# ---- dispatch ----
if (-not $WorkerId) { $WorkerId = Default-WorkerId }
$TaskName = Resolve-TaskName -Name $TaskName -Id $WorkerId

switch ($Mode) {
    "Install" {
        exit (Install-WorkerTask)
    }
    "Status" {
        $RepoRoot = Resolve-RepoRoot -Path $RepoRoot
        exit (Show-Status -Name $TaskName -Root $RepoRoot -Id $WorkerId)
    }
    "Stop" {
        $RepoRoot = Resolve-RepoRoot -Path $RepoRoot
        exit (Stop-WorkerTask -Name $TaskName)
    }
    "Uninstall" {
        exit (Uninstall-WorkerTask -Name $TaskName)
    }
}
