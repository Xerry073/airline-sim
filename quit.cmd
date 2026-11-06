@echo off
REM Quick exit: autosave, then stop backend and supervisor
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0quit.ps1" %*
if errorlevel 1 pause
endlocal
