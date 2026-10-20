@echo off
cd /d "%~dp0"
title Creative Partner
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" %*
if errorlevel 1 (
    echo.
    echo Startup failed. Read the message above and try again.
    pause
)
