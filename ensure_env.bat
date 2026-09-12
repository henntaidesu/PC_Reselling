@echo off
rem ---------------------------------------------------------------------------
rem Make sure the PC_Reselling conda env exists and has the backend deps, then
rem hand its python.exe back to the caller in PCRPY.
rem
rem Shared by start.bat and pyinstaller.bat: both need exactly the same env, and
rem two copies of this would drift apart the first time one of them is touched.
rem The env name, Python version and requirements path therefore live here only.
rem
rem Usage:
rem   call "%~dp0ensure_env.bat"
rem   if errorlevel 1 ( pause & exit /b 1 )
rem   ... !PCRPY! is the full path to python.exe ...
rem
rem No pause / no exit of the caller: this script only reports, the caller
rem decides how to abort (start.bat and pyinstaller.bat both want their own).
rem ---------------------------------------------------------------------------
setlocal enabledelayedexpansion

set "ENV_NAME=PC_Reselling"
set "PY_VERSION=3.12"
set "REQ=%~dp0requirements.txt"
rem Cleared explicitly: setlocal inherits the parent environment, so a stray
rem NEED_DEPS out there would re-run pip on every single start.
set "NEED_DEPS="

call :locate_py

rem Env missing: create it right here instead of telling the user to go do it.
rem conda itself is the one thing we can't bootstrap -- it's a system-wide
rem install with its own installer -- so that's the only case we give up on.
if not defined PCRPY (
  echo [^^!] conda env "%ENV_NAME%" not found.
  where conda >nul 2>&1
  if errorlevel 1 (
    echo [ERROR] conda is not on PATH either, so the env cannot be created.
    echo         Install Miniconda first: https://www.anaconda.com/download/success
    echo         Then re-run -- the env will be created for you.
    exit /b 1
  )
  echo [*] Creating it: conda create -y -n %ENV_NAME% python=%PY_VERSION%
  echo     First run downloads the interpreter, so give it a few minutes.
  rem "call" is required: conda on Windows is conda.bat, and without call the
  rem batch interpreter hands control over and never comes back here.
  call conda create -y -n %ENV_NAME% python=%PY_VERSION%
  if errorlevel 1 (
    echo [ERROR] conda create failed. Fix the error above and re-run.
    exit /b 1
  )
  call :locate_py
  if not defined PCRPY (
    echo [ERROR] Env created but its python.exe was not found in any known location.
    echo         Check "conda env list" and re-run.
    exit /b 1
  )
  rem Brand new env: deps are definitely missing, no point probing for them.
  set "NEED_DEPS=1"
)

rem An existing env can still be empty -- created earlier with the pip step
rem aborted halfway. Probing here turns that into one clear message; otherwise it
rem surfaces later as a bare ModuleNotFoundError from main.py (or as a PyInstaller
rem build that quietly bundles nothing), neither of which says "run pip".
if not defined NEED_DEPS (
  "!PCRPY!" -c "import fastapi, uvicorn, pymysql, jwt, bcrypt" >nul 2>&1
  if errorlevel 1 (
    echo [^^!] Backend deps missing or incomplete in the env.
    set "NEED_DEPS=1"
  )
)

if defined NEED_DEPS (
  echo [*] Installing backend deps: pip install -r requirements.txt
  "!PCRPY!" -m pip install -r "%REQ%"
  if errorlevel 1 (
    echo [ERROR] pip install failed. Fix the error above and re-run.
    exit /b 1
  )
)

rem Carry PCRPY past endlocal: the right-hand side is expanded while the inner
rem scope is still alive, so the value survives into the caller. Everything else
rem set above stays local and does not leak.
endlocal & set "PCRPY=%PCRPY%"
exit /b 0


rem ---------------------------------------------------------------------------
rem :locate_py -- set PCRPY to the env's python.exe, or leave it empty.
rem A subroutine because it runs twice: once up front, once after creating the
rem env. The usual install locations are checked first because they cover almost
rem every machine without spawning anything; "conda info --base" is the fallback
rem for a conda installed somewhere else (it only needs conda on PATH).
rem
rem We deliberately do NOT use "conda activate": it only works after "conda init"
rem has set up cmd shell integration, which fails in a plain double-clicked
rem terminal. Running the env's python.exe by full path needs no activation.
rem ---------------------------------------------------------------------------
:locate_py
set "PCRPY="
for %%P in (
  "%USERPROFILE%\miniconda3\envs\%ENV_NAME%\python.exe"
  "%USERPROFILE%\anaconda3\envs\%ENV_NAME%\python.exe"
  "%LOCALAPPDATA%\miniconda3\envs\%ENV_NAME%\python.exe"
  "%LOCALAPPDATA%\anaconda3\envs\%ENV_NAME%\python.exe"
  "C:\ProgramData\miniconda3\envs\%ENV_NAME%\python.exe"
  "C:\ProgramData\Anaconda3\envs\%ENV_NAME%\python.exe"
) do (
  if exist "%%~P" set "PCRPY=%%~P"
)
if not defined PCRPY (
  for /f "delims=" %%i in ('conda info --base 2^>nul') do set "CONDA_BASE=%%i"
  if defined CONDA_BASE if exist "!CONDA_BASE!\envs\%ENV_NAME%\python.exe" set "PCRPY=!CONDA_BASE!\envs\%ENV_NAME%\python.exe"
)
goto :eof
