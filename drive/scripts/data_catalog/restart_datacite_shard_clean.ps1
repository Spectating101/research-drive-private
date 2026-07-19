param([Parameter(Mandatory = $true)][string]$ShardName)

$ErrorActionPreference = "SilentlyContinue"
$taskName = "ResearchDataIndexDataCite_$ShardName"
$outDir = "C:\cw\dataset_index_$ShardName"
$cmdName = "run_datacite_$ShardName.cmd"

Stop-ScheduledTask -TaskName $taskName
Start-Sleep -Seconds 2
Get-CimInstance Win32_Process |
  Where-Object {
    $_.CommandLine -and (
      $_.CommandLine -like "*$outDir*" -or
      $_.CommandLine -like "*$cmdName*"
    )
  } |
  Sort-Object ProcessId -Descending |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

Start-Sleep -Seconds 2
Start-ScheduledTask -TaskName $taskName
Write-Output "Cleanly restarted $taskName"
