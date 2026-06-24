@echo off
REM ============================================================
REM AutoTrader Pro — Launcher for Prerequisites Installer
REM ============================================================

echo.
echo ======================================================
echo      AutoTrader Pro — Dependency Installer Launcher
echo ======================================================
echo.

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

echo Requesting Administrator privileges to install software...
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%install_prerequisites.ps1"

echo.
echo If the setup script didn't run, please close this terminal and run: setup.bat
pause
