param(
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$backend = Join-Path $root "work\sales_ai_backend"
$recorder = Join-Path $root "work\Automatic-Phone-Recording-main"
$frontend = Join-Path $root "outputs\sales_ai_frontend\index.html"
$backendPython = Join-Path $backend ".venv\Scripts\python.exe"
$recorderPython = Join-Path $recorder ".venv\Scripts\python.exe"
$dockerDesktop = "C:\Program Files\Docker\Docker\Docker Desktop.exe"

function Wait-Until([scriptblock]$Test, [int]$Seconds, [string]$FailureMessage) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    do {
        try {
            if (& $Test) { return }
        } catch {}
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)
    throw $FailureMessage
}

function Initialize-PythonEnvironment([string]$ProjectDir, [string]$PythonPath) {
    if (-not (Test-Path -LiteralPath $PythonPath)) {
        $systemPython = Get-Command python -ErrorAction SilentlyContinue
        if (-not $systemPython) {
            throw "Python is not installed or is not available on PATH. Run 01_安装Python.bat first."
        }
        Write-Output "Creating Python environment: $ProjectDir"
        & $systemPython.Source -m venv (Join-Path $ProjectDir ".venv")
        if ($LASTEXITCODE -ne 0) { throw "Failed to create Python environment: $ProjectDir" }
    }

    $requirements = Join-Path $ProjectDir "requirements.txt"
    if (Test-Path -LiteralPath $requirements) {
        Write-Output "Installing Python dependencies: $ProjectDir"
        & $PythonPath -m pip install -r $requirements
        if ($LASTEXITCODE -ne 0) { throw "Failed to install Python dependencies: $ProjectDir" }
    }
}

Initialize-PythonEnvironment $backend $backendPython
Initialize-PythonEnvironment $recorder $recorderPython

$backendEnv = Join-Path $backend ".env"
if (-not (Test-Path -LiteralPath $backendEnv)) {
    Copy-Item -LiteralPath (Join-Path $backend ".env.example") -Destination $backendEnv
    Write-Output "Created backend .env from .env.example. Configure API keys there when needed."
}

$dockerReady = $false
try {
    docker --context desktop-linux info --format "{{.ServerVersion}}" 2>$null | Out-Null
    $dockerReady = $LASTEXITCODE -eq 0
} catch {}
if (-not $dockerReady) {
    if (-not (Test-Path -LiteralPath $dockerDesktop)) { throw "Docker Desktop is not installed." }
    Start-Process -FilePath $dockerDesktop
    Wait-Until {
        docker --context desktop-linux info --format "{{.ServerVersion}}" 2>$null | Out-Null
        $LASTEXITCODE -eq 0
    } 180 "Docker Desktop did not become ready."
}

if (-not (Get-Process -Name syncthing -ErrorAction SilentlyContinue)) {
    $syncthing = Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\Syncthing.Syncthing_*" -Recurse -Filter syncthing.exe -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $syncthing) { throw "Syncthing is not installed." }
    Start-Process -FilePath $syncthing.FullName -ArgumentList "serve", "--no-browser", "--no-restart" -WindowStyle Hidden
}
Wait-Until { (Invoke-WebRequest "http://127.0.0.1:8384/" -UseBasicParsing -TimeoutSec 2).StatusCode -eq 200 } 30 "Syncthing did not become ready."

$backendHealthy = $false
try {
    $backendHealthy = (Invoke-RestMethod "http://127.0.0.1:8000/health" -TimeoutSec 3).status -eq "ok"
} catch {}
if (-not $backendHealthy) {
    Start-Process -FilePath $backendPython -WorkingDirectory $backend -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000" -WindowStyle Hidden
}
Wait-Until { (Invoke-RestMethod "http://127.0.0.1:8000/health" -TimeoutSec 2).status -eq "ok" } 45 "Sales AI backend did not become ready."

$pidFile = Join-Path $recorder "logs\watcher.pid"
$watcherRunning = $false
if (Test-Path -LiteralPath $pidFile) {
    $watcherPid = 0
    if ([int]::TryParse((Get-Content -LiteralPath $pidFile -Raw).Trim(), [ref]$watcherPid)) {
        $watcherRunning = $null -ne (Get-Process -Id $watcherPid -ErrorAction SilentlyContinue)
    }
}

if (-not $watcherRunning) {
    $env:SYNC_MODE = "local"
    $env:ENABLE_SALES_AI_UPLOAD = "1"
    $env:ENABLE_WAV_CONVERT = "0"
    $env:ENABLE_TRANSCRIBE = "0"
    $env:ENABLE_SUMMARY = "0"
    $env:SALES_AI_BASE_URL = "http://127.0.0.1:8000"
    $env:SALES_AI_USERNAME = "admin"
    $env:SALES_AI_PASSWORD = "admin123"
    $env:PIPELINE_POLL_SECONDS = "15"
    Start-Process -FilePath $recorderPython -WorkingDirectory $recorder -ArgumentList "-m", "app.watcher" -WindowStyle Hidden
    Wait-Until { Test-Path -LiteralPath $pidFile } 20 "Realtime recording watcher did not start."
}

if (-not $NoBrowser) {
    Start-Process -FilePath $frontend
}

Write-Output "Sales AI realtime services are running."
Write-Output "Backend: http://127.0.0.1:8000"
Write-Output "Syncthing: http://127.0.0.1:8384"
Write-Output "Watcher PID: $((Get-Content -LiteralPath $pidFile -Raw).Trim())"
