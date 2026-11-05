@echo off
title ShelfWise - reset a password
cd /d "%~dp0"
where python >nul 2>nul
if %errorlevel%==0 (set PY=python) else (set PY=py)
%PY% reset_password.py
