param(
    [string]$CloudUrl = "http://127.0.0.1:8100",
    [string]$AdminUsername = "admin",
    [string]$AdminPassword = "admin123",
    [string]$SalesUsername = "",
    [string]$TaskName = "SalesAICloudUploader"
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$recorder = Join-Path $root "work\Automatic-Phone-Recording-main"
$python = Join-Path $root ".venv\Scripts\python.exe"
$runner = Join-Path $recorder "run_watcher_autostart.ps1"

if (-not (Test-Path -LiteralPath $python)) {
    throw "Python not found: $python"
}

if (-not (Test-Path -LiteralPath $recorder)) {
    throw "Recorder project not found: $recorder"
}

if (-not $CloudUrl) {
    $CloudUrl = Read-Host "Sales AI backend URL, for example http://127.0.0.1:8100 or https://your-domain.com"
}
if (-not $AdminUsername) {
    $AdminUsername = Read-Host "Admin username"
}
if (-not $AdminPassword) {
    $AdminPassword = Read-Host "Admin password"
}
if (-not $SalesUsername) {
    $SalesUsername = Read-Host "Sales username for this computer, leave empty for admin"
}

$runnerContent = @"
`$ErrorActionPreference = "Stop"
Set-Location "$recorder"
`$env:SYNC_MODE = "local"
`$env:LOCAL_INBOX_DIR = "$recorder\data\inbox"
`$env:ENABLE_SALES_AI_UPLOAD = "1"
`$env:ENABLE_WAV_CONVERT = "0"
`$env:ENABLE_TRANSCRIBE = "0"
`$env:ENABLE_SUMMARY = "0"
`$env:SALES_AI_BASE_URL = "$($CloudUrl.TrimEnd('/'))"
`$env:SALES_AI_USERNAME = "$AdminUsername"
`$env:SALES_AI_PASSWORD = "$AdminPassword"
`$env:SALES_AI_SALES_USERNAME = "$SalesUsername"
`$env:PIPELINE_POLL_SECONDS = "15"
& "$python" -m app.watcher
"@

Set-Content -LiteralPath $runner -Value $runnerContent -Encoding UTF8

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$runner`"" `
    -WorkingDirectory $recorder

$trigger = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Sales AI watcher: upload synced phone screenshots and recordings to Sales AI backend." `
    -Force | Out-Null

Start-ScheduledTask -TaskName $TaskName

Write-Host "Installed and started scheduled task: $TaskName"
Write-Host "Backend URL: $CloudUrl"
Write-Host "Sales username: $SalesUsername"
Write-Host "Inbox: $recorder\data\inbox"
