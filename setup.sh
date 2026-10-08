#!/bin/bash
# ============================================================
# AutoTrader Pro — Setup Script (Linux / macOS / WSL)
# ============================================================
set -e

BOLD='\033[1m'
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${CYAN}${BOLD}"
echo "╔══════════════════════════════════════════╗"
echo "║     AutoTrader Pro — Setup Installer     ║"
echo "║     Autonomous Crypto Trading System     ║"
echo "╚══════════════════════════════════════════╝"
echo -e "${NC}"

# Detect OS
OS="unknown"
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    OS="linux"
elif [[ "$OSTYPE" == "darwin"* ]]; then
    OS="macos"
elif [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" ]]; then
    OS="windows"
fi
echo -e "${CYAN}[INFO]${NC} Detected OS: ${BOLD}$OS${NC}"

# ─── Step 1: Check Python ───────────────────────────────────
echo -e "\n${CYAN}[1/5]${NC} Checking Python installation..."

PYTHON_CMD=""
if command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
elif command -v python &> /dev/null; then
    PYTHON_CMD="python"
fi

if [ -z "$PYTHON_CMD" ]; then
    echo -e "${YELLOW}[WARN]${NC} Python not found. Installing..."
    if [ "$OS" == "linux" ]; then
        sudo apt-get update && sudo apt-get install -y python3 python3-pip python3-venv
        PYTHON_CMD="python3"
    elif [ "$OS" == "macos" ]; then
        if command -v brew &> /dev/null; then
            brew install python@3.11
        else
            echo -e "${RED}[ERROR]${NC} Homebrew not found. Install Python 3.11+ manually: https://www.python.org/downloads/"
            exit 1
        fi
        PYTHON_CMD="python3"
    fi
else
    PY_VERSION=$($PYTHON_CMD --version 2>&1 | awk '{print $2}')
    PY_MAJOR=$(echo $PY_VERSION | cut -d. -f1)
    PY_MINOR=$(echo $PY_VERSION | cut -d. -f2)
    echo -e "${GREEN}[OK]${NC} Python $PY_VERSION found"
    if [ "$PY_MAJOR" -lt 3 ] || ([ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]); then
        echo -e "${RED}[ERROR]${NC} Python 3.10+ required. Found $PY_VERSION"
        exit 1
    fi
fi

# ─── Step 2: Create virtual environment ─────────────────────
echo -e "\n${CYAN}[2/5]${NC} Setting up Python virtual environment..."

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/venv"

if [ ! -d "$VENV_DIR" ]; then
    $PYTHON_CMD -m venv "$VENV_DIR"
    echo -e "${GREEN}[OK]${NC} Virtual environment created at $VENV_DIR"
else
    echo -e "${GREEN}[OK]${NC} Virtual environment already exists"
fi

# Activate venv
source "$VENV_DIR/bin/activate"

# Upgrade pip
pip install --upgrade pip --quiet

# Install backend dependencies
echo -e "\n${CYAN}[3/5]${NC} Installing Python packages..."
if [ -f "$SCRIPT_DIR/backend/requirements.txt" ]; then
    pip install -r "$SCRIPT_DIR/backend/requirements.txt" --quiet
    echo -e "${GREEN}[OK]${NC} Python packages installed"
else
    echo -e "${YELLOW}[WARN]${NC} requirements.txt not found, installing core packages..."
    pip install fastapi uvicorn[standard] ccxt pandas numpy ta websockets httpx sqlalchemy python-dotenv apscheduler requests ollama pydantic aiofiles --quiet
    echo -e "${GREEN}[OK]${NC} Core packages installed"
fi

# ─── Step 3: Check Node.js & npm ────────────────────────────
echo -e "\n${CYAN}[4/5]${NC} Checking Node.js installation..."

if command -v node &> /dev/null; then
    NODE_VERSION=$(node --version)
    echo -e "${GREEN}[OK]${NC} Node.js $NODE_VERSION found"
else
    echo -e "${YELLOW}[WARN]${NC} Node.js not found. Installing..."
    if [ "$OS" == "linux" ]; then
        curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
        sudo apt-get install -y nodejs
    elif [ "$OS" == "macos" ]; then
        if command -v brew &> /dev/null; then
            brew install node
        else
            echo -e "${RED}[ERROR]${NC} Install Node.js manually: https://nodejs.org/"
            exit 1
        fi
    fi
fi

# Install frontend dependencies
if [ -f "$SCRIPT_DIR/frontend/package.json" ]; then
    echo "Installing frontend dependencies..."
    cd "$SCRIPT_DIR/frontend"
    npm install --silent 2>/dev/null || npm install
    cd "$SCRIPT_DIR"
    echo -e "${GREEN}[OK]${NC} Frontend dependencies installed"
fi

# ─── Step 4: Check Ollama ────────────────────────────────────
echo -e "\n${CYAN}[5/5]${NC} Checking Ollama LLM..."

if command -v ollama &> /dev/null; then
    echo -e "${GREEN}[OK]${NC} Ollama is installed"
else
    echo -e "${YELLOW}[WARN]${NC} Ollama not found. Installing..."
    if [ "$OS" == "linux" ]; then
        curl -fsSL https://ollama.com/install.sh | sh
    elif [ "$OS" == "macos" ]; then
        if command -v brew &> /dev/null; then
            brew install ollama
        else
            curl -fsSL https://ollama.com/install.sh | sh
        fi
    fi
fi

# Check if Ollama is running and pull model
if command -v ollama &> /dev/null; then
    # Try to pull the model (starts ollama serve if needed)
    echo "Pulling llama3 model (this may take a few minutes on first run)..."
    ollama pull llama3 2>/dev/null && echo -e "${GREEN}[OK]${NC} llama3 model ready" || {
        echo -e "${YELLOW}[WARN]${NC} Could not pull llama3. Trying mistral..."
        ollama pull mistral 2>/dev/null && echo -e "${GREEN}[OK]${NC} mistral model ready" || {
            echo -e "${YELLOW}[WARN]${NC} Could not pull LLM model. Strategy 4 (Sentiment LLM) will be disabled."
            echo -e "${YELLOW}[WARN]${NC} Start Ollama manually: 'ollama serve' then 'ollama pull llama3'"
        }
    }
else
    echo -e "${YELLOW}[WARN]${NC} Ollama not available. Strategy 4 (Sentiment LLM) will be disabled."
    echo -e "${YELLOW}[WARN]${NC} Install manually: https://ollama.com/download"
fi

# ─── Step 5: Create .env if not exists ──────────────────────
if [ ! -f "$SCRIPT_DIR/.env" ]; then
    cp "$SCRIPT_DIR/.env.example" "$SCRIPT_DIR/.env" 2>/dev/null || true
    echo -e "${GREEN}[OK]${NC} Created .env file from template"
    echo -e "${YELLOW}[ACTION]${NC} Edit .env with your CoinDCX API keys before trading live"
else
    echo -e "${GREEN}[OK]${NC} .env file already exists"
fi

# ─── Done ────────────────────────────────────────────────────
echo -e "\n${GREEN}${BOLD}"
echo "╔══════════════════════════════════════════╗"
echo "║         Setup Complete! ✓                ║"
echo "╠══════════════════════════════════════════╣"
echo "║  Next steps:                             ║"
echo "║  1. Edit .env with your API keys         ║"
echo "║  2. Run: ./start.sh                      ║"
echo "║  3. Open: http://localhost:3000           ║"
echo "╚══════════════════════════════════════════╝"
echo -e "${NC}"
