@echo off
setlocal

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_sales_ai.ps1"
if errorlevel 1 (
  echo.
  echo Failed to start Sales AI system.
  echo Please send Codex a screenshot of this window.
  pause
  exit /b 1
)

echo.
echo Sales AI system started.
pause
