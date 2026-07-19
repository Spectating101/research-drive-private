param(
  [Parameter(Mandatory = $true)][string]$ShardName,
  [Parameter(Mandatory = $true)][string]$CreatedYears,
  [string]$DataCiteQuery = "",
  [string]$OutDirRoot = "C:\cw",
  [string]$PythonExe = "py",
  [string]$MaxRecords = "0",
  [string]$SleepSeconds = "0.35"
)

$ErrorActionPreference = "Stop"
$TaskName = "ResearchDataIndexDataCite_$ShardName"
$OutDir = Join-Path $OutDirRoot "dataset_index_$ShardName"
$Script = "C:\Users\user\harvest_dataset_indexes_full.py"
$CmdPath = "C:\Users\user\run_datacite_$ShardName.cmd"

New-Item -ItemType Directory -Force $OutDir | Out-Null

$queryArg = ""
if ($DataCiteQuery) {
  $escaped = $DataCiteQuery.Replace('"', '\"')
  $queryArg = " --datacite-query `"$escaped`""
}

$Cmd = @"
@echo off
if not exist "$OutDir" mkdir "$OutDir"
:supervise
if exist "$OutDir\datacite.complete.json" exit /b 0
"$PythonExe" "$Script" --out-dir "$OutDir" --sources datacite --max-records-per-source $MaxRecords --page-size 500 --sleep $SleepSeconds --datacite-created-years "$CreatedYears"$queryArg >> "$OutDir\harvest.stdout.log" 2>> "$OutDir\harvest.stderr.log"
set worker_exit=%ERRORLEVEL%
echo supervisor_restart exit=%worker_exit% at=%DATE%_%TIME%>> "$OutDir\supervisor.log"
timeout /t 30 /nobreak >nul
goto supervise
"@
Set-Content -Path $CmdPath -Value $Cmd -Encoding ASCII

cmd.exe /c "schtasks.exe /Delete /TN $TaskName /F >nul 2>nul" | Out-Null
schtasks.exe /Create /TN $TaskName /SC ONLOGON /TR $CmdPath /RL LIMITED /F | Out-Null
schtasks.exe /Run /TN $TaskName | Out-Null
Start-Sleep -Seconds 2
schtasks.exe /Query /TN $TaskName /V /FO LIST
