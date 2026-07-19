Get-CimInstance Win32_Process |
  Where-Object {
    $_.Name -match "python|py" -or
    $_.CommandLine -match "harvest_dataset_indexes"
  } |
  Select-Object ProcessId, Name, CommandLine |
  Format-List

Write-Output "STDERR"
Get-Content "C:\cw\dataset_index_v3\harvest.stderr.log" -ErrorAction SilentlyContinue
Write-Output "STDOUT"
Get-Content "C:\cw\dataset_index_v3\harvest.stdout.log" -ErrorAction SilentlyContinue
Write-Output "FILES"
Get-ChildItem "C:\cw\dataset_index_v3" |
  Select-Object Name, Length, LastWriteTime |
  Format-Table -AutoSize
