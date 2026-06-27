param(
    [string]$CloudUrl,
    [string]$AdminUsername = "admin",
    [string]$SalesUsername,
    [string]$InboxDir
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$recorder = Join-Path $root "work\Automatic-Phone-Recording-main"
$python = Join-Path $recorder ".venv\Scripts\python.exe"

function Read-Required([string]$Prompt, [string]$CurrentValue = "") {
    if ($CurrentValue) { return $CurrentValue }
    do {
        $value = Read-Host $Prompt
    } while (-not $value)
    return $value
}

function Convert-SecureStringToPlainText([securestring]$SecureValue) {
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureValue)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
    }
}

if (-not (Test-Path -LiteralPath $recorder)) {
    throw "Recorder project not found: $recorder"
}

if (-not (Test-Path -LiteralPath $python)) {
    $systemPython = Get-Command python -ErrorAction SilentlyContinue
    if (-not $systemPython) {
        throw "Python is not installed or not available on PATH."
    }
    Write-Host "Creating watcher virtual environment..."
    & $systemPython.Source -m venv (Join-Path $recorder ".venv")
}

$requirements = Join-Path $recorder "requirements.txt"
if (Test-Path -LiteralPath $requirements) {
    Write-Host "Installing watcher dependencies..."
    & $python -m pip install -r $requirements
}

$CloudUrl = (Read-Required "Cloud site URL, for example https://sales.example.com" $CloudUrl).TrimEnd("/")
$AdminUsername = Read-Required "Admin username used for upload" $AdminUsername
$SalesUsername = Read-Required "Sales username for this computer, for example sales01" $SalesUsername
$password = Convert-SecureStringToPlainText (Read-Host "Admin password" -AsSecureString)

if (-not $InboxDir) {
    $InboxDir = Join-Path $recorder "data\inbox"
}
New-Item -ItemType Directory -Force -Path $InboxDir | Out-Null

$env:SYNC_MODE = "local"
$env:LOCAL_INBOX_DIR = $InboxDir
$env:ENABLE_SALES_AI_UPLOAD = "1"
$env:ENABLE_WAV_CONVERT = "0"
$env:ENABLE_TRANSCRIBE = "0"
$env:ENABLE_SUMMARY = "0"
$env:SALES_AI_BASE_URL = $CloudUrl
$env:SALES_AI_USERNAME = $AdminUsername
$env:SALES_AI_PASSWORD = $password
$env:SALES_AI_SALES_USERNAME = $SalesUsername
$env:PIPELINE_POLL_SECONDS = "15"

Write-Host ""
Write-Host "Sales AI cloud uploader is starting."
Write-Host "Cloud:   $CloudUrl"
Write-Host "Sales:   $SalesUsername"
Write-Host "Inbox:   $InboxDir"
Write-Host ""
Write-Host "Keep this window open. Syncthing should sync phone screenshots/recordings into the Inbox folder."
Write-Host ""

Set-Location $recorder
& $python -m app.watcher
