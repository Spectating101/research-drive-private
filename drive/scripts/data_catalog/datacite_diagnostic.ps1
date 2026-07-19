param([Parameter(Mandatory = $true)][string]$ShardName)

$ErrorActionPreference = "SilentlyContinue"
$taskName = "ResearchDataIndexDataCite_$ShardName"
$outDir = "C:\cw\dataset_index_$ShardName"
$info = Get-ScheduledTaskInfo -TaskName $taskName
$checkpointPath = Join-Path $outDir "datacite.checkpoint.json"
$checkpoint = $null
if (Test-Path $checkpointPath) {
  $checkpoint = Get-Content $checkpointPath -Raw | ConvertFrom-Json
}

[PSCustomObject]@{
  Host = $env:COMPUTERNAME
  Shard = $ShardName
  LastTaskResult = $info.LastTaskResult
  LastRunTimeUtc = $info.LastRunTime.ToUniversalTime().ToString("o")
  CommittedRecords = $(if ($checkpoint) { $checkpoint.committed_records } else { 0 })
  NextChunkIndex = $(if ($checkpoint) { $checkpoint.next_chunk_index } else { 0 })
  CheckpointUpdatedAt = $(if ($checkpoint) { $checkpoint.updated_at } else { "" })
} | Format-List

Write-Output "STDOUT_TAIL"
Get-Content (Join-Path $outDir "harvest.stdout.log") -Tail 5
Write-Output "STDERR_TAIL"
Get-Content (Join-Path $outDir "harvest.stderr.log") -Tail 5
