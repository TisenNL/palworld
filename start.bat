@echo off
cd /d "%~dp0"
echo.
echo ========================================
echo  Palworld Checklist + HUD tooltip
echo ========================================
echo.
echo Starting via run.py — Ctrl+C stops the helper.
echo.
py -3 run.py
if errorlevel 1 (
  echo.
  pause
  exit /b 1
)
