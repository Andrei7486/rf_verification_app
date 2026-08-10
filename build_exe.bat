@echo off
setlocal
cd /d "%~dp0"

echo ============================================================
echo  RF Verification - build standalone .exe
echo  Run this ONCE on your laptop (needs Python + internet).
echo  Output:  dist\RFVerification\  =  RFVerification.exe + config\ + results\
echo  The COM station needs NO Python and NO install.
echo ============================================================
echo.

REM --- pick the system Python (py launcher preferred) ---
set "SYSPY="
where py >nul 2>nul && set "SYSPY=py"
if not defined SYSPY where python >nul 2>nul && set "SYSPY=python"
if not defined SYSPY (
  echo [ERROR] Python not found on this PC. Install Python 3.9+ first.
  pause & exit /b 1
)
echo Using system Python: %SYSPY%
echo.

REM --- install build tool + runtime deps ---
echo Installing PyInstaller + Flask + pyserial ...
%SYSPY% -m pip install --upgrade pyinstaller flask pyserial
if errorlevel 1 ( echo [ERROR] pip install failed. Check the internet connection. & pause & exit /b 1 )
echo.

REM --- clean previous artifacts ---
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist RFVerification.spec del /q RFVerification.spec

REM --- build a single-file exe; bundle templates/static/default-config inside it ---
echo Building the executable (this can take a minute) ...
%SYSPY% -m PyInstaller --noconfirm --onefile --name RFVerification --add-data "templates;templates" --add-data "static;static" --add-data "config;config" --hidden-import serial app.py
if errorlevel 1 ( echo [ERROR] PyInstaller build failed. & pause & exit /b 1 )
echo.

REM --- assemble the deliverable folder: exe + external config\ + empty results\ + guides ---
echo Assembling dist\RFVerification ...
mkdir "dist\RFVerification"
move /y "dist\RFVerification.exe" "dist\RFVerification\RFVerification.exe" >nul
xcopy /e /i /y config "dist\RFVerification\config" >nul
mkdir "dist\RFVerification\results" >nul 2>nul
if exist EXE_SETUP.md copy /y EXE_SETUP.md "dist\RFVerification\EXE_SETUP.md" >nul
if exist README.md copy /y README.md "dist\RFVerification\README.md" >nul

echo.
echo ============================================================
echo  DONE.
echo  Deliverable folder:  dist\RFVerification
echo  Copy that whole folder to the COM station and double-click
echo  RFVerification.exe. Edit settings in the app or in config\.
echo ============================================================
pause
