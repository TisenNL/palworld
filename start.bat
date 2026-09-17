@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\register-protocol.ps1"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\kill-helper.ps1"
echo.
echo ========================================
echo  Palworld Checklist + HUD tooltip
echo ========================================
echo.
echo Starting server on http://127.0.0.1:8765/
echo Keep this window open.
echo Use scripts\stop-server.bat to stop the server.
echo.
where node >nul 2>&1
if errorlevel 1 (
  echo ERROR: Node.js 20 or newer was not found.
  echo Install Node.js and try again.
  pause
  exit /b 1
)
powershell.exe -NoProfile -Command "if (!(Test-Path 'node_modules\.package-lock.json') -or ((Get-Item 'package-lock.json').LastWriteTimeUtc -gt (Get-Item 'node_modules\.package-lock.json').LastWriteTimeUtc)) { exit 1 }"
if errorlevel 1 (
  echo Installing frontend dependencies...
  call npm ci
  if errorlevel 1 (
    echo ERROR: Could not install frontend dependencies.
    pause
    exit /b 1
  )
)
echo Building Vue frontend...
call npm run build
if errorlevel 1 (
  echo ERROR: Frontend build failed.
  pause
  exit /b 1
)
py -3 -c "import rapidocr_onnxruntime" >nul 2>&1
if errorlevel 1 (
  echo Installing local OCR engine on first use...
  py -3 -m pip install rapidocr-onnxruntime
  if errorlevel 1 (
    echo WARNING: OCR engine could not be installed.
  )
)
start /b py -3 -c "import time,urllib.request; time.sleep(1.2); urllib.request.urlopen('http://127.0.0.1:8765/health', timeout=5); import webbrowser; webbrowser.open('http://127.0.0.1:8765/')"
py -3 -m server.coord_tooltip
pause
