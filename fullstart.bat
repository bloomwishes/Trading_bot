@echo off
REM ============================================================
REM AutoTrader Pro — Start Script (Windows)
REM ============================================================
setlocal enabledelayedexpansion

echo.
echo ======================================================
echo      AutoTrader Pro — Starting...
echo ======================================================
echo.

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

REM Check .env
if not exist "%SCRIPT_DIR%.env" (
    echo [ERROR] .env file not found! Run setup.bat first.
    pause
    exit /b 1
)

REM Activate venv
if exist "%SCRIPT_DIR%venv\Scripts\activate.bat" (
    call "%SCRIPT_DIR%venv\Scripts\activate.bat"
)

REM Create logs directory
if not exist "%SCRIPT_DIR%logs" mkdir "%SCRIPT_DIR%logs"

REM Show what python/node resolve to right now, for debugging double-click vs
REM manual-terminal PATH mismatches. This gets written to logs\launch_debug.log
echo ---- LAUNCH DEBUG %DATE% %TIME% ---- > "%SCRIPT_DIR%logs\launch_debug.log"
echo PATH=%PATH% >> "%SCRIPT_DIR%logs\launch_debug.log"
where python >> "%SCRIPT_DIR%logs\launch_debug.log" 2>&1
where node >> "%SCRIPT_DIR%logs\launch_debug.log" 2>&1
where npm >> "%SCRIPT_DIR%logs\launch_debug.log" 2>&1

REM Start Backend
echo [1/3] Starting backend API server...
set "PYTHONPATH=%SCRIPT_DIR%"
start "AutoTrader-Backend" cmd /k "cd /d %SCRIPT_DIR% && set PYTHONPATH=%SCRIPT_DIR% && python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload || (echo. & echo [BACKEND CRASHED - see error above] & pause)"
echo [OK] Backend starting on http://localhost:8000

REM Wait for backend
echo Waiting for backend to initialize...
timeout /t 4 /nobreak >nul

REM Start Frontend
echo [2/3] Starting frontend dashboard...
start "AutoTrader-Frontend" cmd /k "cd /d %SCRIPT_DIR%frontend && npm run dev -- --host || (echo. & echo [FRONTEND CRASHED - see error above] & pause)"
echo [OK] Frontend starting on http://localhost:3000

REM Wait for frontend
echo Waiting for frontend to initialize...
timeout /t 3 /nobreak >nul

REM Start Mobile Cloudflare Tunnel
echo [3/3] Starting mobile Cloudflare tunnel...
start "AutoTrader-Mobile-Tunnel" cmd /k "cd /d %SCRIPT_DIR% && call mobile_tunnel.bat"
echo [OK] Mobile tunnel launching...

echo.
echo ======================================================
echo      AutoTrader Pro is RUNNING!
echo ======================================================
echo.
echo   Local Dashboard:   http://localhost:3000
echo   Local Wi-Fi Link:  http://192.168.1.102:3000
echo   Remote Mobile URL: Check the "AutoTrader-Mobile-Tunnel" window
echo   API Docs:          http://localhost:8000/docs
echo.
echo   Close this window or press Ctrl+C to stop.
echo.
pause
