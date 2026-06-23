@echo off
setlocal

set "PYTHON_URL=https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe"
set "INSTALLER=%~dp0python-3.11.9-amd64.exe"

echo ========================================
echo Install Python 3.11 for Sales AI System
echo ========================================
echo.

python --version >nul 2>nul
if not errorlevel 1 (
  echo Python is already installed:
  python --version
  echo You can now run the Sales AI launcher.
  pause
  exit /b 0
)

echo Python is not installed. Downloading official Python installer...
echo %PYTHON_URL%
powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-WebRequest -Uri '%PYTHON_URL%' -OutFile '%INSTALLER%'"
if errorlevel 1 (
  echo Download failed. Open this link in a browser:
  echo %PYTHON_URL%
  pause
  exit /b 1
)

echo Starting Python installer...
echo Check Add python.exe to PATH in the installer.
start /wait "" "%INSTALLER%"

echo Python installer closed. Open a new command window if needed.
echo Then run the Sales AI launcher.
pause
