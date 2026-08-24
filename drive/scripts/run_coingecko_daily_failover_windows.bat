@echo off
setlocal

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_coingecko_daily_failover.ps1"
set EXITCODE=%ERRORLEVEL%

if not "%EXITCODE%"=="0" (
  echo Failover runner exited with code %EXITCODE%.
)

endlocal & exit /b %EXITCODE%
