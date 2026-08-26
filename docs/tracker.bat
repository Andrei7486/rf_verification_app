@echo off
REM Launch the development tracker from the repository.
REM The page reads ROADMAP.md and VALIDATION_APP_SPEC.md from this folder,
REM which browsers refuse to do over file:// - so serve the folder instead.

setlocal
cd /d "%~dp0"

set PORT=8099
set PY=

REM Prefer the project's portable interpreter when present, then a normal one.
REM The Microsoft Store stub is skipped on purpose - it opens the Store instead.
if exist "..\python\python.exe" set PY=..\python\python.exe
if "%PY%"=="" (
  for /f "delims=" %%P in ('where python 2^>nul') do (
    echo %%P | find /i "WindowsApps" >nul || if "%PY%"=="" set PY=%%P
  )
)
if "%PY%"=="" (
  echo Python was not found on PATH and no portable interpreter is present.
  echo Open progress.html through any local web server instead.
  pause
  exit /b 1
)

echo Serving %CD% on http://localhost:%PORT%/progress.html
start "" "http://localhost:%PORT%/progress.html"
"%PY%" -m http.server %PORT%

endlocal
