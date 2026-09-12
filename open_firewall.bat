@echo off
rem ---------------------------------------------------------------------------
rem Open (or close) the Windows Firewall for the dev servers:
rem   9911  frontend (Vite dev server)
rem   9910  backend  (FastAPI / uvicorn)
rem
rem Why this exists: both servers already listen on 0.0.0.0, so nothing in the
rem code stops a phone on the LAN or a port-forwarded client on the WAN --
rem Windows does, silently. The symptom is a plain connection timeout with not
rem one line in either server console, which looks nothing like a firewall
rem problem and sends people editing config files that were already correct.
rem
rem Usage (right-click -> Run as administrator):
rem   open_firewall.bat          add the inbound rules
rem   open_firewall.bat off      remove them again
rem
rem This only opens this machine. Reaching it from the internet still needs the
rem router to forward those ports (or a tunnel).
rem ---------------------------------------------------------------------------
setlocal

rem Rule names are also probed by start.bat to warn when they are missing.
rem Change them here and there, or the warning starts lying.
set "RULE_WEB=PC Reselling dev frontend 9911"
set "RULE_API=PC Reselling dev backend 9910"

net session >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Administrator rights required.
    echo         Right-click this file and choose "Run as administrator".
    echo.
    pause
    exit /b 1
)

if /i "%~1"=="off" goto :remove

echo Adding inbound rules ...
rem Delete first so re-running does not stack up duplicates under one name.
netsh advfirewall firewall delete rule name="%RULE_WEB%" >nul 2>&1
netsh advfirewall firewall delete rule name="%RULE_API%" >nul 2>&1

netsh advfirewall firewall add rule name="%RULE_WEB%" dir=in action=allow protocol=TCP localport=9911 profile=any
if errorlevel 1 goto :failed
netsh advfirewall firewall add rule name="%RULE_API%" dir=in action=allow protocol=TCP localport=9910 profile=any
if errorlevel 1 goto :failed

echo.
echo Done. 9910 and 9911 now accept inbound TCP on every network profile.
echo Undo with: open_firewall.bat off
echo.
pause
exit /b 0

:remove
echo Removing inbound rules ...
netsh advfirewall firewall delete rule name="%RULE_WEB%" >nul 2>&1
netsh advfirewall firewall delete rule name="%RULE_API%" >nul 2>&1
echo Done. The ports are blocked from outside again.
echo.
pause
exit /b 0

:failed
echo.
echo [ERROR] netsh failed -- the rules were NOT created.
echo.
pause
exit /b 1
