@echo off
echo ========================================
echo   PC Reselling Manager - one-click build
echo ========================================

rem ===== Version (edit this on each release) =====
set VERSION=v1.0.0

set "ROOT=%~dp0"
set "RELEASE=%ROOT%Releases\%VERSION%"
set "EXE_NAME=PCResellingManager.exe"

rem ===== Activate conda env PC_Reselling (same fallback as start.bat) =====
echo.
echo [0/3] Activating conda env PC_Reselling ...
call conda activate PC_Reselling >nul 2>&1
if /i "%CONDA_DEFAULT_ENV%"=="PC_Reselling" goto :conda_ok
set "CONDA_ACT="
for /f "delims=" %%C in ('where conda 2^>nul') do if not defined CONDA_ACT if exist "%%~dpCactivate.bat" set "CONDA_ACT=%%~dpCactivate.bat"
if defined CONDA_ACT call "%CONDA_ACT%" PC_Reselling
if /i "%CONDA_DEFAULT_ENV%"=="PC_Reselling" goto :conda_ok
echo ERROR: failed to activate conda env PC_Reselling
echo        Create it first: conda create -y -n PC_Reselling python=3.12
echo        then: pip install -r requirements.txt   (or just run start.bat once)
pause
exit /b 1
:conda_ok
python -c "import sys; print('Using python:', sys.executable)"

rem ===== Ensure build deps are available =====
rem NOTE: call it via "python -m PyInstaller" (NOT the bare "pyinstaller" command).
rem This script is named pyinstaller.bat; cmd resolves "pyinstaller" to THIS file
rem (current dir before PATH), which would recurse into an infinite loop.
python -c "import PyInstaller" >nul 2>&1
if errorlevel 1 (
    echo pyinstaller not found, installing...
    python -m pip install pyinstaller
)
rem pystray / Pillow are only needed by the packaged tray shell, so a dev env may lack them.
python -c "import pystray, PIL" >nul 2>&1
if errorlevel 1 (
    echo pystray/Pillow not found, installing requirements...
    python -m pip install -r "%ROOT%requirements.txt"
)

rem ===== Prepare release directory =====
rem Do NOT wipe the whole release dir: conf.ini next to the exe holds the MySQL password.
rem Only the old exe is replaced.
echo.
echo [1/3] Preparing release dir %RELEASE% ...
if not exist "%RELEASE%" mkdir "%RELEASE%"
if exist "%RELEASE%\%EXE_NAME%" del /f /q "%RELEASE%\%EXE_NAME%"
if exist "%RELEASE%\%EXE_NAME%" (
    echo ERROR: cannot delete old %EXE_NAME%, is it still running? Exit it from the tray first.
    pause
    exit /b 1
)
if exist "%ROOT%build" rmdir /s /q "%ROOT%build"

rem ===== Build frontend =====
echo.
echo [2/3] Building frontend webside ...
where npm >nul 2>&1
if errorlevel 1 (
    echo ERROR: npm not found, please install Node.js: https://nodejs.org/
    pause
    exit /b 1
)
pushd "%ROOT%webside"
if not exist "node_modules" (
    echo Installing frontend deps...
    call npm install
    if errorlevel 1 ( echo ERROR: npm install failed & popd & pause & exit /b 1 )
)
call npm run build
if errorlevel 1 ( echo ERROR: frontend build failed & popd & pause & exit /b 1 )
popd
if not exist "%ROOT%webside\dist\index.html" (
    echo ERROR: webside\dist\index.html not found, frontend build may have failed
    pause
    exit /b 1
)

rem ===== Build exe =====
rem pc_reselling.spec resolves paths from the current directory (ROOT = os.getcwd()),
rem so PyInstaller must run from the project root.
echo.
echo [3/3] Building %EXE_NAME% (windowed, system tray; frontend bundled in) ...
pushd "%ROOT%"
python -m PyInstaller --clean --noconfirm pc_reselling.spec ^
    --distpath "%RELEASE%" --workpath "%ROOT%build"
set BUILD_ERR=%errorlevel%
popd
if not "%BUILD_ERR%"=="0" (
    echo ERROR: %EXE_NAME% build failed
    pause
    exit /b 1
)

rem ===== Clean build intermediates =====
if exist "%ROOT%build" rmdir /s /q "%ROOT%build"

echo.
echo ========================================
echo   Build complete! Output dir: %RELEASE%
echo ========================================
dir /b "%RELEASE%"
echo ----------------------------------------
echo   Run %EXE_NAME%. On first launch it writes a default conf.ini next to
echo   the exe; fill in the [mysql] password, then start it again.
echo   A run window with live logs opens on launch. Clicking X asks whether to
echo   exit or minimize to the tray; the tray icon (bottom-right) restores it.
echo   Then open http://localhost:9910 in your browser.
echo ========================================
pause
