$ErrorActionPreference = "Stop"
$TaskName = "ResearchDataIndexDataCite"
$Command = "C:\Users\user\run_datacite_cluster.cmd"

cmd.exe /c "schtasks.exe /Delete /TN $TaskName /F >nul 2>nul" | Out-Null
schtasks.exe /Create /TN $TaskName /SC ONLOGON /TR $Command /RL LIMITED /F | Out-Null
schtasks.exe /Run /TN $TaskName | Out-Null
Start-Sleep -Seconds 2
schtasks.exe /Query /TN $TaskName /V /FO LIST
