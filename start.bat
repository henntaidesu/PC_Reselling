@echo off
setlocal enabledelayedexpansion
echo ========================================
echo   PC Reselling Manager - dev startup
echo ========================================
echo.

set "ROOT=%~dp0"
set "BACKEND=%ROOT%backend"
set "WEBSIDE=%ROOT%webside"

if not exist "%ROOT%conf.ini" (
    echo [^^!] conf.ini not found. The backend will create a default one on start.
    echo [^^!] After it appears, fill in the [mysql] password and re-run.
    echo.
)

rem ---- conda activate ----
call conda activate PC_Reselling >nul 2>&1
if /i "%CONDA_DEFAULT_ENV%"=="PC_Reselling" goto :conda_ok
set "CONDA_ACT="
for /f "delims=" %%C in ('where conda 2^>nul') do if not defined CONDA_ACT if exist "%%~dpCactivate.bat" set "CONDA_ACT=%%~dpCactivate.bat"
if defined CONDA_ACT call "%CONDA_ACT%" PC_Reselling
if /i "%CONDA_DEFAULT_ENV%"=="PC_Reselling" goto :conda_ok

rem ---- env not found, create it ----
where conda >nul 2>&1
if errorlevel 1 (
    echo [ERROR] conda not on PATH. Install Miniconda: https://www.anaconda.com/download/success
    pause
    exit /b 1
)
echo [*] Env "PC_Reselling" not found, creating ...
call conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main >nul 2>&1
call conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/r >nul 2>&1
call conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/msys2 >nul 2>&1
call conda create -y -n PC_Reselling python=3.12
if errorlevel 1 (
    echo [ERROR] conda create failed.
    pause
    exit /b 1
)
call conda activate PC_Reselling >nul 2>&1
if /i not "%CONDA_DEFAULT_ENV%"=="PC_Reselling" (
    if defined CONDA_ACT call "%CONDA_ACT%" PC_Reselling
)
if /i not "%CONDA_DEFAULT_ENV%"=="PC_Reselling" (
    echo [ERROR] Env created but activation failed. Check: conda env list
    pause
    exit /b 1
)
echo [*] Installing backend deps ...
python -m pip install -r "%ROOT%requirements.txt"
if errorlevel 1 (
    echo [ERROR] pip install failed.
    pause
    exit /b 1
)
:conda_ok
for /f "delims=" %%P in ('where python') do echo Using python: %%P& goto :py_shown
:py_shown

rem ---- backend ----
echo [1/2] Starting backend ...
set "PC_RESELLING_RELOAD=1"
pushd "%BACKEND%"
start "PCReselling-Backend" /b python main.py
popd

timeout /t 2 /nobreak >nul

rem ---- frontend ----
echo [2/2] Preparing frontend dev server ...
where npm >nul 2>&1
if errorlevel 1 (
    echo [ERROR] npm not found. Install Node.js: https://nodejs.org/
    pause
    exit /b 1
)

pushd "%WEBSIDE%"
if not exist "node_modules" (
    echo Installing frontend deps ...
    call npm install
    if errorlevel 1 (
        echo [ERROR] npm install failed
        popd
        pause
        exit /b 1
    )
)

echo.
echo ========================================
echo   Frontend:  http://localhost:9911
echo   Backend :  http://localhost:9910
for /f "tokens=2 delims=:" %%i in ('ipconfig ^| findstr /c:"IPv4"') do (
    set "LANIP=%%i"
    set "LANIP=!LANIP: =!"
    echo   LAN/WAN:  http://!LANIP!:9911
)
netsh advfirewall firewall show rule name="PC Reselling dev frontend 9911" >nul 2>&1
if errorlevel 1 (
    echo   [^^!] No firewall rule - other devices will time out.
    echo       Run open_firewall.bat once as administrator.
)
echo   Close this window to stop both.
echo ========================================
echo.

call npm run dev
popd

echo.
echo Stopping backend on port 9910 ...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":9910" ^| findstr LISTENING') do taskkill /F /PID %%a >nul 2>&1
endlocal
