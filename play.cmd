@echo off
REM Quick entry: start supervisor + open browser
setlocal
cd /d "%~dp0"
call "%~dp0start.cmd" %*
endlocal
