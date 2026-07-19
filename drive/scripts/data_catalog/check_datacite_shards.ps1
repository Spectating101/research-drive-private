$ErrorActionPreference = "Continue"

Write-Output "=== HOST ==="
Write-Output $env:COMPUTERNAME

Write-Output "=== TASKS ==="
Get-ScheduledTask -TaskName "ResearchDataIndexDataCite*" -ErrorAction SilentlyContinue |
  ForEach-Object {
    $info = Get-ScheduledTaskInfo -TaskName $_.TaskName -ErrorAction SilentlyContinue
    [PSCustomObject]@{
      TaskName = $_.TaskName
      State = $_.State
      LastRunTime = $info.LastRunTime
      LastTaskResult = $info.LastTaskResult
    }
  } | Format-Table -AutoSize
Write-Output "=== PROCESSES ==="
Get-CimInstance Win32_Process |
  Where-Object { $_.CommandLine -like "*harvest_dataset_indexes_full.py*" } |
  Select-Object ProcessId, Name, CommandLine |
  Format-List

Write-Output "=== SHARDS ==="
Get-ChildItem C:\cw -Directory -Filter "dataset_index_*" -ErrorAction SilentlyContinue |
  ForEach-Object {
    $complete = @(Get-ChildItem $_.FullName -File -Filter "*.jsonl.gz" -ErrorAction SilentlyContinue)
    $partial = @(Get-ChildItem $_.FullName -File -Filter "*.partial" -ErrorAction SilentlyContinue)
    [PSCustomObject]@{
      Directory = $_.FullName
      CompleteChunks = $complete.Count
      CompleteBytes = ($complete | Measure-Object Length -Sum).Sum
      PartialChunks = $partial.Count
      PartialBytes = ($partial | Measure-Object Length -Sum).Sum
      ErrorLogBytes = (Get-Item (Join-Path $_.FullName "harvest.stderr.log") -ErrorAction SilentlyContinue).Length
    }
  } | Format-Table -AutoSize
