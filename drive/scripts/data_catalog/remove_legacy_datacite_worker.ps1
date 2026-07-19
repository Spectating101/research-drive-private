$ErrorActionPreference = "Continue"
$legacyTask = "ResearchDataIndexDataCite"
$legacyPath = "C:\cw\dataset_index_v3"

Stop-ScheduledTask -TaskName $legacyTask -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName $legacyTask -Confirm:$false -ErrorAction SilentlyContinue

Get-CimInstance Win32_Process |
  Where-Object {
    $_.CommandLine -like "*harvest_dataset_indexes_full.py*" -and
    $_.CommandLine -like "*$legacyPath*"
  } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

Write-Output "Legacy unfiltered DataCite task/process removed."
