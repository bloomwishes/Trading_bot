@echo off
REM ============================================================
REM AutoTrader Pro — 1-Click Launcher (Windows)
REM ============================================================
setlocal enabledelayedexpansion

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

echo ======================================================
echo      AutoTrader Pro 1-Click Launcher
echo ======================================================
echo.

REM Check if first-time setup is needed
if not exist "%SCRIPT_DIR%venv" (
    echo [INFO] First time run detected. Running setup automatically...
    call "%SCRIPT_DIR%setup.bat"
) else if not exist "%SCRIPT_DIR%.env" (
    echo [INFO] Environment file missing. Running setup...
    call "%SCRIPT_DIR%setup.bat"
)

echo [INFO] Launching AutoTrader Pro servers...
REM Start the start.bat in a new window so this script can continue
start "AutoTrader Server Manager" cmd /c "%SCRIPT_DIR%start.bat"

echo [INFO] Waiting for servers to initialize (10 seconds)...
timeout /t 10 /nobreak >nul

echo [INFO] Opening the Dashboard in your default web browser...
start http://localhost:3000

echo [INFO] Done! You can close this small window now. The servers will keep running in the background windows.
timeout /t 5 >nul
exit
