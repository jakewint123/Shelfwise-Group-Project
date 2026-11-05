@echo off
title ShelfWise - Know your shelves.
cd /d "%~dp0"
echo Starting ShelfWise...
where python >nul 2>nul
if %errorlevel%==0 (set PY=python) else (set PY=py)
%PY% --version >nul 2>nul
if errorlevel 1 (
  echo.
  echo Python is not installed. Install it from https://www.python.org/downloads/
  echo and tick "Add Python to PATH". Then run this file again.
  pause
  exit /b
)
%PY% -m pip install -q --disable-pip-version-check -r requirements.txt
%PY% run.py
pause
