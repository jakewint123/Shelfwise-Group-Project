@echo off
title ShelfWise - reset demo data
cd /d "%~dp0"
where python >nul 2>nul
if %errorlevel%==0 (set PY=python) else (set PY=py)
echo.
echo This puts back the demo data and the two demo accounts:
echo    Manager: manager@shelfwise.test / Manager123!
echo    Staff:   staff@shelfwise.test   / Staff123!
echo.
echo WARNING: products, sales and users you added yourself will be deleted.
echo Close the other black ShelfWise window first.
echo.
set /p OK=Type Y and press Enter to continue: 
if /i not "%OK%"=="Y" (echo Nothing changed. & pause & exit /b)
%PY% seed.py
echo.
echo Now double-click START_SHELFWISE_Windows.bat and sign in.
pause
