@echo off
setlocal
title Install Sales AI Auto Uploader
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_sales_ai_auto_uploader.ps1"
if errorlevel 1 (
  echo.
  echo Failed to install Sales AI auto uploader.
  pause
  exit /b 1
)
echo.
echo Sales AI auto uploader has been installed.
pause
