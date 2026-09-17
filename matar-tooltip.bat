@echo off
cd /d "%~dp0"
echo Stopping tooltip...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0_kill_tooltip.ps1"
echo.
pause
