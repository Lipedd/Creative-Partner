param([switch]$NoBrowser)

$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

$appUrl = 'http://127.0.0.1:8501'
$healthUrl = "$appUrl/api/health"
$pythonPath = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$frontendPath = Join-Path $PSScriptRoot 'frontend'
$frontendEntry = Join-Path $frontendPath 'dist\index.html'
$dataPath = Join-Path $PSScriptRoot '.agentdesk'
$sourceStampPath = Join-Path $dataPath 'server-source.stamp'

function Get-SourceStamp {
    $files = @(
        Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot 'agentdesk') -Recurse -File | Where-Object { $_.Extension -in '.py', '.md' }
        Get-ChildItem -LiteralPath (Join-Path $frontendPath 'src') -Recurse -File
        Get-Item -LiteralPath (Join-Path $PSScriptRoot 'app.py'), (Join-Path $PSScriptRoot 'requirements.txt'), (Join-Path $frontendPath 'index.html'), (Join-Path $frontendPath 'package.json'), (Join-Path $frontendPath 'package-lock.json')
    )
    return (($files | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1).LastWriteTimeUtc.Ticks).ToString()
}

function Test-FrontendBuildNeeded {
    if (-not (Test-Path -LiteralPath $frontendEntry)) { return $true }
    $latestSource = Get-ChildItem -Path (Join-Path $frontendPath 'src'), (Join-Path $frontendPath 'index.html'), (Join-Path $frontendPath 'package.json'), (Join-Path $frontendPath 'package-lock.json') -Recurse -File |
        Sort-Object LastWriteTimeUtc -Descending |
        Select-Object -First 1
    return $latestSource.LastWriteTimeUtc -gt (Get-Item -LiteralPath $frontendEntry).LastWriteTimeUtc
}

function Test-CreativePartner {
    try {
        $response = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 2
        return $response.status -eq 'ok'
    }
    catch { return $false }
}

function Open-CreativePartner {
    try {
        $listener = Get-NetTCPConnection -LocalPort 8501 -State Listen -ErrorAction Stop | Select-Object -First 1
        if ($listener) {
            New-Item -ItemType Directory -Force -Path $dataPath | Out-Null
            Set-Content -LiteralPath (Join-Path $dataPath 'server.pid') -Value $listener.OwningProcess
            Set-Content -LiteralPath $sourceStampPath -Value $sourceStamp
        }
    }
    catch { }
    if (-not $NoBrowser) { Start-Process $appUrl }
    Write-Host "Creative Partner is ready: $appUrl" -ForegroundColor Green
}

try {
    $sourceStamp = Get-SourceStamp
    $needsBuild = Test-FrontendBuildNeeded

    if (Test-CreativePartner) {
        $savedStamp = if (Test-Path -LiteralPath $sourceStampPath) { (Get-Content -LiteralPath $sourceStampPath -Raw).Trim() } else { '' }
        if ($savedStamp -eq $sourceStamp -and -not $needsBuild) {
            Open-CreativePartner
            exit 0
        }
        $listener = Get-NetTCPConnection -LocalPort 8501 -State Listen -ErrorAction Stop | Select-Object -First 1
        $runningProcess = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)"
        $command = [string]$runningProcess.CommandLine
        if ($command.IndexOf($pythonPath, [StringComparison]::OrdinalIgnoreCase) -lt 0 -or $command.IndexOf('uvicorn app:app', [StringComparison]::OrdinalIgnoreCase) -lt 0) {
            throw 'Port 8501 is already used by another program. Close that program and try again.'
        }
        Stop-Process -Id $listener.OwningProcess
    }

    Write-Host 'Preparing Creative Partner. Please wait...' -ForegroundColor Yellow

    if (-not (Test-Path -LiteralPath $pythonPath)) {
        if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
            throw 'Python is missing. Install Python 3.11 or newer, then try again.'
        }
        python -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'Could not prepare the Python environment.' }
    }

    & $pythonPath -c "import fastapi, uvicorn, langchain, langgraph.checkpoint.sqlite" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host 'First start: installing required packages...' -ForegroundColor Yellow
        & $pythonPath -m pip install -r requirements.txt
        if ($LASTEXITCODE -ne 0) { throw 'Package installation failed. Check the network and try again.' }
    }

    if ($needsBuild) {
        if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
            throw 'Node.js is missing. Install Node.js 20 or newer, then try again.'
        }
        Push-Location $frontendPath
        try {
            if (-not (Test-Path -LiteralPath 'node_modules')) {
                Write-Host 'First start: preparing the web interface...' -ForegroundColor Yellow
                npm.cmd ci
                if ($LASTEXITCODE -ne 0) { throw 'Web dependencies failed to install. Check the network and try again.' }
            }
            npm.cmd run build
            if ($LASTEXITCODE -ne 0) { throw 'The web interface failed to build.' }
        }
        finally { Pop-Location }
    }

    New-Item -ItemType Directory -Force -Path $dataPath | Out-Null
    $stdoutLog = Join-Path $dataPath 'server-output.log'
    $stderrLog = Join-Path $dataPath 'server-error.log'
    $process = Start-Process -FilePath $pythonPath `
        -ArgumentList @('-m', 'uvicorn', 'app:app', '--host', '127.0.0.1', '--port', '8501') `
        -WorkingDirectory $PSScriptRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput $stdoutLog `
        -RedirectStandardError $stderrLog `
        -PassThru
    Set-Content -LiteralPath (Join-Path $dataPath 'server.pid') -Value $process.Id

    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        if (Test-CreativePartner) {
            Open-CreativePartner
            exit 0
        }
        if ($process.HasExited) { break }
        Start-Sleep -Milliseconds 250
    }

    $detail = if (Test-Path -LiteralPath $stderrLog) { (Get-Content -LiteralPath $stderrLog -Tail 8) -join "`n" } else { '' }
    throw "Creative Partner did not start successfully.`n$detail"
}
catch {
    Write-Host ''
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
