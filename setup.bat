@echo off
REM ============================================================
REM AutoTrader Pro — Setup Script (Windows)
REM ============================================================
setlocal enabledelayedexpansion

echo.
echo ======================================================
echo      AutoTrader Pro — Setup Installer (Windows)
echo      Autonomous Crypto Trading System
echo ======================================================
echo.

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

REM ─── Step 1: Check Python ───────────────────────────────────
echo [1/5] Checking Python installation...

where python >nul 2>&1
if %ERRORLEVEL% equ 0 (
    for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PY_VERSION=%%i
    echo [OK] Python !PY_VERSION! found
    set PYTHON_CMD=python
) else (
    where python3 >nul 2>&1
    if %ERRORLEVEL% equ 0 (
        for /f "tokens=2" %%i in ('python3 --version 2^>^&1') do set PY_VERSION=%%i
        echo [OK] Python !PY_VERSION! found
        set PYTHON_CMD=python3
    ) else (
        echo [ERROR] Python not found!
        echo Please install Python 3.10+ from https://www.python.org/downloads/
        echo Make sure to check "Add Python to PATH" during installation.
        pause
        exit /b 1
    )
)

REM ─── Step 2: Create virtual environment ─────────────────────
echo.
echo [2/5] Setting up Python virtual environment...

if not exist "%SCRIPT_DIR%venv" (
    %PYTHON_CMD% -m venv "%SCRIPT_DIR%venv"
    echo [OK] Virtual environment created
) else (
    echo [OK] Virtual environment already exists
)

REM Activate venv
call "%SCRIPT_DIR%venv\Scripts\activate.bat"

REM Upgrade pip
python -m pip install --upgrade pip --quiet 2>nul

REM ─── Step 3: Install Python packages ───────────────────────
echo.
echo [3/5] Installing Python packages...

if exist "%SCRIPT_DIR%backend\requirements.txt" (
    pip install -r "%SCRIPT_DIR%backend\requirements.txt" --quiet 2>nul
    echo [OK] Python packages installed
) else (
    echo [WARN] requirements.txt not found, installing core packages...
    pip install fastapi uvicorn[standard] ccxt pandas numpy ta websockets httpx sqlalchemy python-dotenv apscheduler requests ollama pydantic aiofiles --quiet 2>nul
    echo [OK] Core packages installed
)

REM ─── Step 4: Check Node.js ────────────────────────────────
echo.
echo [4/5] Checking Node.js installation...

where node >nul 2>&1
if %ERRORLEVEL% equ 0 (
    for /f "tokens=1" %%i in ('node --version 2^>^&1') do echo [OK] Node.js %%i found
) else (
    echo [ERROR] Node.js not found!
    echo Please install Node.js from https://nodejs.org/
    echo Download the LTS version and run the installer.
    pause
    exit /b 1
)

REM Install frontend dependencies
if exist "%SCRIPT_DIR%frontend\package.json" (
    echo Installing frontend dependencies...
    cd /d "%SCRIPT_DIR%frontend"
    call npm install --silent 2>nul || call npm install
    cd /d "%SCRIPT_DIR%"
    echo [OK] Frontend dependencies installed
)

REM ─── Step 5: Check Ollama ──────────────────────────────────
echo.
echo [5/5] Checking Ollama LLM...

where ollama >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo [OK] Ollama is installed
    echo Pulling llama3 model (this may take a few minutes on first run)...
    ollama pull llama3 2>nul && (
        echo [OK] llama3 model ready
    ) || (
        echo [WARN] Could not pull llama3. Trying mistral...
        ollama pull mistral 2>nul && (
            echo [OK] mistral model ready
        ) || (
            echo [WARN] Could not pull LLM model. Strategy 4 will be disabled.
            echo [WARN] Start Ollama manually and run: ollama pull llama3
        )
    )
) else (
    echo [WARN] Ollama not found.
    echo [WARN] Install from: https://ollama.com/download
    echo [WARN] Strategy 4 (Sentiment LLM) will be disabled until Ollama is installed.
)

REM ─── Create .env if not exists ──────────────────────────────
if not exist "%SCRIPT_DIR%.env" (
    if exist "%SCRIPT_DIR%.env.example" (
        copy "%SCRIPT_DIR%.env.example" "%SCRIPT_DIR%.env" >nul
        echo [OK] Created .env file from template
    )
    echo [ACTION] Edit .env with your CoinDCX API keys before trading live
) else (
    echo [OK] .env file already exists
)

REM ─── Done ──────────────────────────────────────────────────
echo.
echo ======================================================
echo         Setup Complete!
echo ======================================================
echo.
echo   Next steps:
echo   1. Edit .env with your API keys
echo   2. Run: start.bat
echo   3. Open: http://localhost:3000
echo.
pause
