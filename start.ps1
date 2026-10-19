$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$pythonPath = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Unable to create Python virtual environment.' }
}
& $pythonPath -c "import fastapi, uvicorn, langchain, langgraph.checkpoint.sqlite"
if ($LASTEXITCODE -ne 0) {
    & $pythonPath -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed. Check network/proxy configuration.' }
}
if (-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'frontend\node_modules'))) {
    Push-Location (Join-Path $PSScriptRoot 'frontend')
    try { npm.cmd ci; if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' } }
    finally { Pop-Location }
}
Push-Location (Join-Path $PSScriptRoot 'frontend')
try { npm.cmd run build; if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' } }
finally { Pop-Location }
Write-Host 'Agent Desk: http://127.0.0.1:8501'
& $pythonPath -m uvicorn app:app --host 127.0.0.1 --port 8501
