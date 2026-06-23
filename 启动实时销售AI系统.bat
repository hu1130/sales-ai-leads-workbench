@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0??????AI??.ps1"
if errorlevel 1 (
  echo.
  echo Failed to start Sales AI realtime services.
  pause
  exit /b 1
)
echo.
echo Sales AI realtime services started successfully.
pause
