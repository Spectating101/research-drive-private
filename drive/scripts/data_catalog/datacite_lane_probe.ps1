param(
  [Parameter(Mandatory = $true)][string]$ShardName
)

$ErrorActionPreference = "SilentlyContinue"
$outDir = "C:\cw\dataset_index_$ShardName"
$taskName = "ResearchDataIndexDataCite_$ShardName"
$completePath = Join-Path $outDir "datacite.complete.json"
$checkpointPath = Join-Path $outDir "datacite.checkpoint.json"
$heartbeatPath = Join-Path $outDir "datacite.heartbeat.json"

$committed = 0
$activityUtc = ""
$isComplete = "0"

if (Test-Path $completePath) {
  $isComplete = "1"
  try {
    $complete = Get-Content $completePath -Raw | ConvertFrom-Json
    $committed = [int64]$complete.committed_records
    $activityUtc = [string]$complete.completed_at
  } catch {}
} elseif (Test-Path $checkpointPath) {
  try {
    $checkpoint = Get-Content $checkpointPath -Raw | ConvertFrom-Json
    $committed = [int64]$checkpoint.committed_records
    $activityUtc = [string]$checkpoint.updated_at
  } catch {}
}

$heartbeatUtc = ""
if (Test-Path $heartbeatPath) {
  $heartbeatUtc = (Get-Item $heartbeatPath).LastWriteTimeUtc.ToString("o")
  if (-not $activityUtc) { $activityUtc = $heartbeatUtc }
}

$process = Get-CimInstance Win32_Process |
  Where-Object {
    $_.Name -eq "python.exe" -and
    $_.CommandLine -like "*harvest_dataset_indexes_full.py*" -and
    $_.CommandLine -like "*$outDir*"
  } |
  Select-Object -First 1

$pidValue = if ($process) { [string]$process.ProcessId } else { "0" }
$taskState = "Missing"
$task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($task) { $taskState = [string]$task.State }

$status = if ($isComplete -eq "1") { "complete" }
  elseif ($pidValue -ne "0") { "running" }
  elseif (Test-Path $outDir) { "idle" }
  else { "missing" }

$fields = @($ShardName, $status, $isComplete, $committed, $pidValue, $taskState, $activityUtc, $heartbeatUtc)
Write-Output ($fields -join "|")
