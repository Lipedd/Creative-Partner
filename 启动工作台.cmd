@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    python -m venv .venv
    if errorlevel 1 goto failed
)
".venv\Scripts\python.exe" -c "import fastapi, uvicorn, langchain, langgraph.checkpoint.sqlite" >nul 2>&1
if errorlevel 1 (
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 goto failed
)
pushd frontend
if not exist "node_modules" (
    call npm.cmd ci
    if errorlevel 1 goto failed
)
call npm.cmd run build
if errorlevel 1 goto failed
popd
echo Agent Desk: http://127.0.0.1:8501
start "" "http://127.0.0.1:8501"
".venv\Scripts\python.exe" -m uvicorn app:app --host 127.0.0.1 --port 8501
if errorlevel 1 goto failed
exit /b 0
:failed
echo Startup failed. Check the error above and your Python/network settings.
pause
exit /b 1
