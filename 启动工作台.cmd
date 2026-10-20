@echo off
cd /d "%~dp0"
title Creative Partner
set "AGENTDESK_MODE=local"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" %*
if errorlevel 1 (
    echo.
    echo Startup failed. Read the message above and try again.
    pause
)
