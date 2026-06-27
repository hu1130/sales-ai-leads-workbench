param(
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $root ".venv\Scripts\python.exe"
$backend = Join-Path $root "work\sales_ai_backend"
$frontend = Join-Path $root "outputs\sales_ai_frontend_vue"
$backendUrl = "http://127.0.0.1:8100"
$frontendUrl = "http://127.0.0.1:5173/"

function Get-NpmCommand {
    $npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
    if (-not $npm) {
        $npm = Get-Command npm -ErrorAction SilentlyContinue
    }
    if (-not $npm) {
        throw "Node.js/npm not found. Install Node.js before starting the Vue frontend."
    }
    return $npm.Source
}

function Test-Backend {
    try {
        $result = Invoke-RestMethod "${backendUrl}/health" -TimeoutSec 2
        return $result.status -eq "ok"
    } catch {
        return $false
    }
}

function Test-Frontend {
    try {
        $result = Invoke-WebRequest $frontendUrl -UseBasicParsing -TimeoutSec 2
        return $result.StatusCode -eq 200
    } catch {
        return $false
    }
}

function Get-PortOwner([int]$Port) {
    try {
        $connection = Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    } catch {
        $connection = $null
    }
    if (-not $connection) { return "" }
    try {
        $process = Get-Process -Id $connection.OwningProcess -ErrorAction SilentlyContinue
    } catch {
        $process = $null
    }
    if ($process) {
        return "PID $($connection.OwningProcess) ($($process.ProcessName))"
    }
    return "PID $($connection.OwningProcess)"
}

function Assert-PortFree([int]$Port, [string]$Name) {
    $owner = Get-PortOwner $Port
    if ($owner) {
        throw "$Name fixed port $Port is already occupied by $owner. Close that program first; this project will not auto-switch ports."
    }
}

function Wait-ForService([scriptblock]$Test, [string]$Name, [int]$Seconds) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    do {
        if (& $Test) {
            Write-Host "$Name is ready."
            return
        }
        Start-Sleep -Milliseconds 700
    } while ((Get-Date) -lt $deadline)
    throw "$Name did not become ready."
}

function Start-CmdService([string]$Title, [string]$WorkingDirectory, [string]$Command) {
    $args = "/k title $Title && cd /d `"$WorkingDirectory`" && $Command"
    Start-Process -FilePath $env:ComSpec -ArgumentList $args -WindowStyle Minimized
}

Write-Host "========================================"
Write-Host "Sales AI Leads Workbench"
Write-Host "========================================"
Write-Host ""

if (-not (Test-Path -LiteralPath $python)) {
    throw "Python venv not found: $python"
}
if (-not (Test-Path -LiteralPath (Join-Path $backend "run_server.py"))) {
    throw "Backend launcher not found: $(Join-Path $backend "run_server.py")"
}
if (-not (Test-Path -LiteralPath (Join-Path $frontend "package.json"))) {
    throw "Vue frontend not found: $(Join-Path $frontend "package.json")"
}
$npm = Get-NpmCommand

if (Test-Backend) {
    Write-Host "Backend is already running."
} else {
    Assert-PortFree 8100 "Backend"
    Write-Host "Starting backend..."
    Start-CmdService "Sales AI Backend" $backend "`"$python`" run_server.py"
}

if (Test-Frontend) {
    Write-Host "Frontend is already running."
} else {
    Assert-PortFree 5173 "Frontend"
    Write-Host "Starting frontend..."
    Start-CmdService "Sales AI Frontend" $frontend "`"$npm`" run dev"
}

Wait-ForService ${function:Test-Backend} "Backend" 45
Wait-ForService ${function:Test-Frontend} "Frontend" 45

Write-Host ""
Write-Host "Ready."
Write-Host "Frontend: $frontendUrl"
Write-Host "Backend:  $backendUrl"
Write-Host ""

if (-not $NoBrowser) {
    Start-Process $frontendUrl
}
