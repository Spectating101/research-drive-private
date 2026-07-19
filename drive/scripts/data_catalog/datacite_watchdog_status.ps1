param(
  [Parameter(Mandatory = $true)][string]$ShardName
)

$ErrorActionPreference = "SilentlyContinue"
$taskName = "ResearchDataIndexDataCite_$ShardName"
$outDir = "C:\cw\dataset_index_$ShardName"
$task = Get-ScheduledTask -TaskName $taskName
$process = Get-CimInstance Win32_Process |
  Where-Object {
    $_.Name -eq "python.exe" -and
    $_.CommandLine -like "*harvest_dataset_indexes_full.py*" -and
    $_.CommandLine -like "*$outDir*"
  } |
  Select-Object -First 1
$latest = Get-ChildItem $outDir -File |
  Where-Object { $_.Name -like "datacite_*.jsonl.gz*" } |
  Sort-Object LastWriteTimeUtc -Descending |
  Select-Object -First 1
$complete = @(Get-ChildItem $outDir -File -Filter "datacite_*.jsonl.gz")
$errorLog = Get-Item (Join-Path $outDir "harvest.stderr.log")
$heartbeat = Get-Item (Join-Path $outDir "datacite.heartbeat.json")
$checkpoint = Get-Item (Join-Path $outDir "datacite.checkpoint.json")

$fields = @(
  $env:COMPUTERNAME,
  $ShardName,
  $(if ($task) { [string]$task.State } else { "Missing" }),
  $(if ($process) { [string]$process.ProcessId } else { "0" }),
  $(if ($latest) { $latest.LastWriteTimeUtc.ToString("o") } else { "" }),
  $(if ($latest) { [string]$latest.Length } else { "0" }),
  [string]$complete.Count,
  $(if ($errorLog) { [string]$errorLog.Length } else { "0" }),
  $(if ($heartbeat) { $heartbeat.LastWriteTimeUtc.ToString("o") } else { "" }),
  $(if ($checkpoint) { $checkpoint.LastWriteTimeUtc.ToString("o") } else { "" })
)
Write-Output ($fields -join "|")
