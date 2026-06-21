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

REM Start Backend
echo [1/2] Starting backend API server...
set "PYTHONPATH=%SCRIPT_DIR%"
start "AutoTrader-Backend" cmd /c "cd /d %SCRIPT_DIR% && set PYTHONPATH=%SCRIPT_DIR% && python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload"
echo [OK] Backend starting on http://localhost:8000

REM Wait for backend
echo Waiting for backend to initialize...
timeout /t 4 /nobreak >nul

REM Start Frontend
echo [2/2] Starting frontend dashboard...
start "AutoTrader-Frontend" cmd /c "cd /d %SCRIPT_DIR%frontend && npm run dev -- --host"
echo [OK] Frontend starting on http://localhost:3000

echo.
echo ======================================================
echo      AutoTrader Pro is RUNNING!
echo ======================================================
echo.
echo   Dashboard: http://localhost:3000
echo   API Docs:  http://localhost:8000/docs
echo.
echo   Close this window or press Ctrl+C to stop.
echo.
pause
