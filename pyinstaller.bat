@echo off
setlocal enabledelayedexpansion
echo ========================================
echo   PC Reselling Manager - one-click build
echo ========================================

rem ===== Version (edit on each release) =====
set "VERSION=v1.0.0"

set "ROOT=%~dp0"
set "RELEASE=%ROOT%Releases\%VERSION%"

rem ===== Conda env + backend deps. Shared with start.bat -- see ensure_env.bat.
rem Sets PCRPY to the env python.exe, creating the env / installing deps if
rem needed. The deps matter here too, not just at runtime: the spec collects
rem submodules of uvicorn and pymysql, so they have to be importable at BUILD
rem time or the exe ships without them. =====
call "%ROOT%ensure_env.bat"
if errorlevel 1 (
  pause
  exit /b 1
)
echo Using Python: !PCRPY!

rem ===== Ensure pyinstaller. NOTE: call it via "python -m PyInstaller" (NOT bare
rem "pyinstaller"): this script is named pyinstaller.bat, and cmd resolves the bare
rem command to THIS file (current dir before PATH), recursing into itself. =====
"!PCRPY!" -c "import PyInstaller" >nul 2>&1
if %errorlevel% neq 0 (
    echo pyinstaller not found, installing...
    "!PCRPY!" -m pip install pyinstaller
    if errorlevel 1 (
        echo ERROR: could not install pyinstaller
        pause
        exit /b 1
    )
)

echo.
echo [1/3] Cleaning release dir %RELEASE% ...
if exist "%RELEASE%" rmdir /s /q "%RELEASE%"
mkdir "%RELEASE%"
if exist "%ROOT%build" rmdir /s /q "%ROOT%build"

echo.
echo [2/3] Building frontend ...
where npm >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: npm not found, install Node.js
    pause
    exit /b 1
)
pushd "%ROOT%webside"
if not exist "node_modules" (
    call npm install
    if %errorlevel% neq 0 (
        echo ERROR: npm install failed
        popd
        pause
        exit /b 1
    )
)
call npm run build
if %errorlevel% neq 0 (
    echo ERROR: frontend build failed
    popd
    pause
    exit /b 1
)
popd
if not exist "%ROOT%webside\dist\index.html" (
    echo ERROR: webside\dist\index.html not found
    pause
    exit /b 1
)

echo.
echo [3/3] Building PCResellingManager.exe (frontend bundled in) ...
"!PCRPY!" -m PyInstaller --clean --noconfirm "%ROOT%pc_reselling.spec" --distpath "%RELEASE%" --workpath "%ROOT%build"
if %errorlevel% neq 0 (
    echo ERROR: exe build failed
    pause
    exit /b 1
)

rem ===== Ship conf.ini next to the exe (contains your MySQL settings) =====
if exist "%ROOT%conf.ini" (
    copy "%ROOT%conf.ini" "%RELEASE%\conf.ini" >nul
) else (
    echo [^^!] conf.ini not found; the release has no config file. Create one next to the exe.
)

if exist "%ROOT%build" rmdir /s /q "%ROOT%build"

echo.
echo ========================================
echo   Build complete! Output: %RELEASE%
echo ========================================
dir /b "%RELEASE%"
echo ----------------------------------------
echo   1) Edit conf.ini next to the exe: fill in MySQL host/user/password.
echo   2) Make sure MySQL is running and the database exists (auto-created if the
echo      account has CREATE privilege).
echo   3) Run PCResellingManager.exe, then open http://localhost:9910
echo ========================================
pause
endlocal
