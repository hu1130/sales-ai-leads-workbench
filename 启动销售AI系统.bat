@echo off
setlocal

set "ROOT=%~dp0"
set "BACKEND=%ROOT%work\sales_ai_backend"
set "FRONTEND=%ROOT%outputs\sales_ai_frontend\index.html"

echo ========================================
echo Sales AI System
echo ========================================
echo.

if not exist "%BACKEND%" (
  echo Backend folder not found: %BACKEND%
  pause
  exit /b 1
)

if not exist "%FRONTEND%" (
  echo Frontend file not found: %FRONTEND%
  pause
  exit /b 1
)

if not exist "%BACKEND%\.venv\Scripts\python.exe" (
  echo Creating backend virtual environment...
  python -m venv "%BACKEND%\.venv"
  if errorlevel 1 (
    echo Failed to create virtual environment.
    echo Run the Python installer batch file first, then try again.
    pause
    exit /b 1
  )
)

echo Installing backend dependencies...
"%BACKEND%\.venv\Scripts\python.exe" -m pip install -r "%BACKEND%\requirements.txt"
if errorlevel 1 (
  echo Failed to install backend dependencies.
  pause
  exit /b 1
)

if not exist "%BACKEND%\.env" (
  copy "%BACKEND%\.env.example" "%BACKEND%\.env" >nul
  echo Created backend .env from .env.example.
)

echo.
echo Starting backend at http://127.0.0.1:8000
powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%BACKEND%\.venv\Scripts\python.exe' -WorkingDirectory '%BACKEND%' -ArgumentList '-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8000'"
if errorlevel 1 (
  echo Failed to launch the backend process.
  pause
  exit /b 1
)

echo Waiting for backend health check...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ok=$false; foreach($i in 1..20){ try { $r=Invoke-RestMethod -Uri 'http://127.0.0.1:8000/health' -TimeoutSec 2; if($r.status -eq 'ok'){$ok=$true; break} } catch {}; Start-Sleep -Milliseconds 500 }; if(-not $ok){exit 1}"
if errorlevel 1 (
  echo Backend did not become ready at http://127.0.0.1:8000.
  pause
  exit /b 1
)

echo Backend is ready.

echo Opening frontend...
start "" "%FRONTEND%"

echo.
echo Login:
echo   username: admin
echo   password: admin123
echo   backend:  http://127.0.0.1:8000
echo.
echo Keep the backend window open while using the system.
pause
