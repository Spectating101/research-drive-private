$ErrorActionPreference = "Stop"
$proc = Get-CimInstance Win32_Process |
  Where-Object {
    $_.CommandLine -like "*harvest_dataset_indexes_full.py*" -and
    $_.Name -eq "python.exe"
  } |
  Select-Object -First 1

if (-not $proc) {
  Write-Output "No DataCite Python worker found."
  exit 1
}

$before = Get-Process -Id $proc.ProcessId
$cpuBefore = $before.CPU
$ramBefore = $before.WorkingSet64
Start-Sleep -Seconds 10
$after = Get-Process -Id $proc.ProcessId

[PSCustomObject]@{
  Host = $env:COMPUTERNAME
  Pid = $proc.ProcessId
  CpuDelta10s = [math]::Round($after.CPU - $cpuBefore, 3)
  RamMB = [math]::Round($after.WorkingSet64 / 1MB, 1)
  RamDeltaMB10s = [math]::Round(($after.WorkingSet64 - $ramBefore) / 1MB, 1)
} | Format-List
