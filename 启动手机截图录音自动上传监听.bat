@echo off
setlocal
cd /d "%~dp0work\Automatic-Phone-Recording-main"
"%~dp0.venv\Scripts\python.exe" -m app.watcher
pause
