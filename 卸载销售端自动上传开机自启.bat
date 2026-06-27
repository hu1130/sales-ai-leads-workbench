@echo off
setlocal
title Uninstall Sales AI Auto Uploader
powershell -NoProfile -ExecutionPolicy Bypass -Command "Unregister-ScheduledTask -TaskName 'SalesAICloudUploader' -Confirm:$false -ErrorAction SilentlyContinue; Write-Host 'Sales AI auto uploader scheduled task removed.'"
pause
