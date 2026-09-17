@echo off
cd /d "%~dp0"
echo Stopping tooltip...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0kill-helper.ps1"
echo.
pause
