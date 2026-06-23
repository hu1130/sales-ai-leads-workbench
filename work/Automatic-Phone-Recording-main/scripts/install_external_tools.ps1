$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$ToolsDir = Join-Path $ProjectRoot "tools"
$AdbZip = Join-Path $ToolsDir "platform-tools-latest-windows.zip"
$OllamaInstaller = Join-Path $ToolsDir "OllamaSetup.exe"

New-Item -ItemType Directory -Force $ToolsDir | Out-Null

if (-not (Test-Path $VenvPython)) {
    & "C:\Users\dorat\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m venv (Join-Path $ProjectRoot ".venv")
}

Write-Host "Installing optional Python speech dependency: funasr"
& $VenvPython -m pip install --upgrade pip
& $VenvPython -m pip install funasr

Write-Host "Downloading Android Platform Tools / ADB"
Invoke-WebRequest `
    -Uri "https://dl.google.com/android/repository/platform-tools-latest-windows.zip" `
    -OutFile $AdbZip
Expand-Archive -Force $AdbZip $ToolsDir

Write-Host "Downloading Ollama Windows installer"
Invoke-WebRequest `
    -Uri "https://ollama.com/download/OllamaSetup.exe" `
    -OutFile $OllamaInstaller

Write-Host "Starting Ollama installer"
Start-Process -FilePath $OllamaInstaller -Wait

Write-Host "Pulling default summary model"
ollama pull qwen2.5:7b

Write-Host "Done. Run: .venv\Scripts\python.exe -m app.doctor"
