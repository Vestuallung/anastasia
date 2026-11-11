@echo off
setlocal
cd /d "%~dp0"
if not exist ".runtime\environment.ps1" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" -SkipModel %*
    if errorlevel 1 goto failed
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0karaoke-local.ps1" desktop --port 0 --open
if not errorlevel 1 exit /b 0
:failed
echo Karaoke Studio could not start. See the message above.
pause
exit /b 1
