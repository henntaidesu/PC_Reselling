@echo off
setlocal enabledelayedexpansion
echo ========================================
echo   PC Reselling Manager - dev startup
echo ========================================
echo.

set "ROOT=%~dp0"
set "BACKEND=%ROOT%backend"
set "WEBSIDE=%ROOT%webside"

rem conf.ini is the single config file (MySQL connection + listen port). The backend
rem also auto-generates a comment-free one on first run; this is just an early notice.
if not exist "%ROOT%conf.ini" (
    echo [^^!] conf.ini not found. The backend will create a default one on start.
    echo [^^!] After it appears, fill in the [mysql] password and re-run.
    echo.
)

rem Conda env + backend deps. Shared with pyinstaller.bat -- see ensure_env.bat.
rem Sets PCRPY to the env python.exe, creates the env / installs deps if needed.
call "%ROOT%ensure_env.bat"
if errorlevel 1 (
  pause
  exit /b 1
)

echo [1/2] Starting backend with:
echo        !PCRPY!
rem Enable backend hot reload (uvicorn watches backend\*.py). Dev only; the exe
rem build ignores this flag.
set "PC_RESELLING_RELOAD=1"
rem /b keeps the backend in THIS same console (no second window). Its log and the
rem frontend's log interleave in one CLI. The backend keeps running in the
rem background; closing this window stops both.
pushd "%BACKEND%"
start "PCReselling-Backend" /b "!PCRPY!" main.py
popd

timeout /t 2 /nobreak >nul

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
echo   Backend :  http://localhost:9910   (backend + frontend logs share this window)
rem Both servers bind 0.0.0.0, so every address of this machine serves them.
rem Printing them saves an ipconfig round trip when opening the page on a phone.
for /f "tokens=2 delims=:" %%i in ('ipconfig ^| findstr /c:"IPv4"') do (
    set "LANIP=%%i"
    set "LANIP=!LANIP: =!"
    echo   LAN/WAN:  http://!LANIP!:9911
)
rem Listening is not the same as reachable: with no inbound rule Windows drops
rem outside connections without a word in either console, which reads like the
rem server is down rather than like a firewall. Probe the rule open_firewall.bat
rem creates (same name -- keep the two in sync) and say so instead.
netsh advfirewall firewall show rule name="PC Reselling dev frontend 9911" >nul 2>&1
if errorlevel 1 (
    echo   [^^!] No firewall rule yet - other devices will just time out.
    echo       Run open_firewall.bat once as administrator to allow 9910/9911.
)
echo   Close this window to stop both.
echo ========================================
echo.

call npm run dev
popd

rem If npm exited on its own (not via Ctrl+C), the backend may still be holding
rem port 9910. Best-effort: kill whatever is LISTENING on it. (On Ctrl+C the shared
rem console usually signals the backend too, so this often finds nothing -- fine.)
echo.
echo Stopping backend on port 9910 ...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":9910" ^| findstr LISTENING') do taskkill /F /PID %%a >nul 2>&1
endlocal
