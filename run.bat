@echo off
cd /d "%~dp0"

if not exist "python\python.exe" (
  echo [ERROR] Portable Python not found.
  echo This folder was not built yet. On a PC with Python, run build_portable.bat first,
  echo then copy the whole folder here. See PORTABLE_SETUP.md.
  pause
  exit /b 1
)

echo Starting RF Verification...
echo The browser will open at http://127.0.0.1:5000
echo Keep this window open while you work. Close it (or press Ctrl+C) to stop.
echo.
python\python.exe app.py
pause
