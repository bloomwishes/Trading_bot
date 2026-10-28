@echo off
REM ============================================================
REM AutoTrader Pro — 1-Click Mobile Cloudflare Tunnel
REM ============================================================
setlocal enabledelayedexpansion

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

echo ======================================================
echo   AutoTrader Pro — Mobile Cloudflare Tunnel Launcher
echo ======================================================
echo.

REM Check if cloudflared exists, if not download it
if not exist "%SCRIPT_DIR%cloudflared.exe" (
    echo [INFO] cloudflared.exe not found. Downloading official binary from Cloudflare...
    curl.exe -Lo "%SCRIPT_DIR%cloudflared.exe" "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
    if errorlevel 1 (
        echo [ERROR] Failed to download cloudflared.exe. Please check your internet connection.
        pause
        exit /b 1
    )
    echo [OK] cloudflared.exe downloaded successfully.
    echo.
)

echo [INFO] Starting secure tunnel to your dashboard (http://localhost:3000)...
echo [SECURITY] NOTE: Ensure you have configured API_KEY in .env before sharing the tunnel publicly!
echo [INFO] Look for the line starting with "https://....trycloudflare.com" below.
echo [INFO] Open that URL on your mobile phone to view and control your bot!
echo.
if not exist "%SCRIPT_DIR%logs" mkdir "%SCRIPT_DIR%logs"
del /f /q "%SCRIPT_DIR%logs\tunnel.log" 2>nul

echo [INFO] Tunnel logging to %SCRIPT_DIR%logs\tunnel.log
"%SCRIPT_DIR%cloudflared.exe" tunnel --url http://localhost:3000 --logfile "%SCRIPT_DIR%logs\tunnel.log"
pause
