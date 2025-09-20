@echo off
setlocal EnableExtensions
cd /d "%~dp0"

rem --- paths ---
set "VENV=.venv"
set "PY=%VENV%\Scripts\python.exe"

rem --- create venv if missing ---
if not exist "%PY%" (
  echo [SETUP] creating venv...
  where py >nul 2>nul && py -3 -m venv "%VENV%" || python -m venv "%VENV%"
)

rem --- deps (install on first run only) ---
if not exist "%VENV%\Scripts\flask.exe" (
  echo [SETUP] install deps...
  "%PY%" -m pip install -U pip
  "%PY%" -m pip install -r requirements.txt
) else (
  echo [SETUP] deps already present, skip
)

rem --- init DB on first run ---
if not exist "instance\colizeum.db" (
  echo [DB] init...
  set "PYTHONPATH=%CD%"
  "%PY%" scripts\recreate_db.py
)

rem --- run app ---
echo [RUN] starting server...
set "PYTHONIOENCODING=utf-8"
"%PY%" run.py

echo.
echo [DONE] press any key to close
pause >nul
