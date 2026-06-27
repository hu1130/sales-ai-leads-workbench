@echo off
setlocal
title Sales AI Cloud Uploader
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_sales_ai_cloud_uploader.ps1"
if errorlevel 1 (
  echo.
  echo Sales AI cloud uploader failed to start.
  pause
  exit /b 1
)
pause
