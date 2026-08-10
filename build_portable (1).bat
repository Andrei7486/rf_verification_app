@echo off
setlocal enableextensions
cd /d "%~dp0"

echo ============================================================
echo  RF Verification - build PORTABLE package (NO installation)
echo  Uses the embeddable Python in .\python. Nothing is installed.
echo  No PowerShell used. Needs internet for this one-time build.
echo ============================================================
echo.

REM --- the embeddable Python must be extracted into .\python ---
if not exist "python\python.exe" (
  echo [ERROR] "python\python.exe" not found.
  echo   1^) Download the "Windows embeddable package" ZIP from python.org
  echo      ^(for the Win7 32-bit station: Python 3.8.10, 32-bit^).
  echo   2^) Extract it into a subfolder named  python  next to this file.
  echo   3^) Run build_portable.bat again.
  pause & exit /b 1
)

REM --- 1) detect the portable Python version ---
set "PYVER="
for /f "delims=" %%v in ('python\python.exe -c "import sys;print('%%s.%%s'%%sys.version_info[:2])"') do set "PYVER=%%v"
if not defined PYVER ( echo [ERROR] Could not run python\python.exe. & pause & exit /b 1 )
set "PYNODOT=%PYVER:.=%"
echo Portable Python version: %PYVER%  ^(python%PYNODOT%^)
echo.

REM --- 2) enable pip support in the ._pth (pure batch, no PowerShell) ---
echo Writing python\python%PYNODOT%._pth ...
(
echo python%PYNODOT%.zip
echo .
echo ..
echo Lib\site-packages
echo import site
)> "python\python%PYNODOT%._pth"
if not exist "python\python%PYNODOT%._pth" ( echo [ERROR] Could not write ._pth & pause & exit /b 1 )

REM --- 3) get-pip.py : version-correct URL, download via curl or by browser ---
set "GETPIP_URL=https://bootstrap.pypa.io/get-pip.py"
if "%PYVER%"=="3.8" set "GETPIP_URL=https://bootstrap.pypa.io/pip/3.8/get-pip.py"
if "%PYVER%"=="3.7" set "GETPIP_URL=https://bootstrap.pypa.io/pip/3.7/get-pip.py"
if "%PYVER%"=="3.6" set "GETPIP_URL=https://bootstrap.pypa.io/pip/3.6/get-pip.py"

if not exist "get-pip.py" (
  where curl >nul 2>nul && (
    echo Downloading get-pip.py via curl ...
    curl -L -o "get-pip.py" "%GETPIP_URL%"
  )
)
if not exist "get-pip.py" (
  echo.
  echo [ACTION NEEDED] Could not download get-pip.py automatically.
  echo   Open this link in your browser:
  echo       %GETPIP_URL%
  echo   Save the file as  get-pip.py  into THIS folder, then run build_portable.bat again.
  echo.
  pause & exit /b 1
)

echo Installing pip into the portable Python ...
python\python.exe get-pip.py --no-warn-script-location
if errorlevel 1 ( echo [ERROR] pip bootstrap failed. & pause & exit /b 1 )
echo.

REM --- 4) install the app dependencies (Flask 2.3.3 keeps Python 3.8 / Win7 support) ---
echo Installing Flask + pyserial ...
python\python.exe -m pip install --no-warn-script-location "flask==2.3.3" pyserial
if errorlevel 1 ( echo [ERROR] pip install failed. Check internet / proxy. & pause & exit /b 1 )

echo.
echo ============================================================
echo  DONE.
echo  Copy this WHOLE folder to the station (NSLAB04-PC) and run
echo  run.bat there. No installation is needed anywhere.
echo ============================================================
pause
