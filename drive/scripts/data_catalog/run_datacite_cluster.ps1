$ErrorActionPreference = "Stop"
$OutDir = "C:\cw\dataset_index_v3"
$Script = "C:\Users\user\harvest_dataset_indexes_full.py"
$Python = "C:\Users\user\AppData\Local\Programs\Python\Python39\python.exe"

New-Item -ItemType Directory -Force $OutDir | Out-Null

$ArgsList = @(
  $Script,
  "--out-dir", $OutDir,
  "--sources", "datacite",
  "--max-records-per-source", "5000000",
  "--page-size", "500",
  "--sleep", "0.25"
)

$Process = Start-Process `
  -FilePath $Python `
  -ArgumentList $ArgsList `
  -WorkingDirectory "C:\Users\user" `
  -RedirectStandardOutput "$OutDir\harvest.stdout.log" `
  -RedirectStandardError "$OutDir\harvest.stderr.log" `
  -WindowStyle Hidden `
  -PassThru

Write-Output "REMOTE_PID=$($Process.Id)"
