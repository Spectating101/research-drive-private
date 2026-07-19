$Python = "C:\Users\user\AppData\Local\Programs\Python\Python39\python.exe"
$Script = "C:\Users\user\harvest_dataset_indexes_full.py"

Write-Output "PYTHON_EXISTS=$(Test-Path $Python)"
Write-Output "SCRIPT_EXISTS=$(Test-Path $Script)"
& $Python -V
& $Python $Script --out-dir "C:\cw\dataset_index_probe" --sources datacite --max-records-per-source 10 --page-size 10 --sleep 0.1
Write-Output "EXIT=$LASTEXITCODE"
Get-ChildItem "C:\cw\dataset_index_probe" -ErrorAction SilentlyContinue |
  Select-Object Name, Length |
  Format-Table -AutoSize
