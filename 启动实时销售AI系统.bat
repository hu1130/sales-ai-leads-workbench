@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_sales_ai_realtime.ps1"
if errorlevel 1 (
  echo.
  echo Failed to start Sales AI realtime services.
  pause
  exit /b 1
)
echo.
echo Sales AI realtime services started successfully.
pause
