@echo off
REM Airline Simulator launcher (ASCII only; Chinese messages live in start.ps1)
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" %*
if errorlevel 1 pause
endlocal
