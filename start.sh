#!/bin/bash
# ============================================================
# AutoTrader Pro — Start Script (Linux / macOS / WSL)
# ============================================================
set -e

BOLD='\033[1m'
CYAN='\033[0;36m'
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo -e "${CYAN}${BOLD}"
echo "╔══════════════════════════════════════════╗"
echo "║     AutoTrader Pro — Starting...         ║"
echo "╚══════════════════════════════════════════╝"
echo -e "${NC}"

# Check .env exists
if [ ! -f "$SCRIPT_DIR/.env" ]; then
    echo -e "${RED}[ERROR]${NC} .env file not found! Run setup.sh first."
    exit 1
fi

# Activate venv
if [ -d "$SCRIPT_DIR/venv" ]; then
    source "$SCRIPT_DIR/venv/bin/activate"
fi

# Function to cleanup on exit
cleanup() {
    echo -e "\n${CYAN}[INFO]${NC} Shutting down AutoTrader Pro..."
    if [ ! -z "$BACKEND_PID" ]; then
        kill $BACKEND_PID 2>/dev/null || true
        echo -e "${GREEN}[OK]${NC} Backend stopped"
    fi
    if [ ! -z "$FRONTEND_PID" ]; then
        kill $FRONTEND_PID 2>/dev/null || true
        echo -e "${GREEN}[OK]${NC} Frontend stopped"
    fi
    echo -e "${GREEN}[OK]${NC} AutoTrader Pro shut down cleanly"
    exit 0
}
trap cleanup SIGINT SIGTERM

# Create logs directory
mkdir -p "$SCRIPT_DIR/logs"

# Start Backend
echo -e "${CYAN}[1/2]${NC} Starting backend API server..."
cd "$SCRIPT_DIR"
PYTHONPATH="$SCRIPT_DIR" python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!
echo -e "${GREEN}[OK]${NC} Backend starting on http://localhost:8000 (PID: $BACKEND_PID)"

# Wait for backend to be ready
echo "Waiting for backend to initialize..."
sleep 3

# Start Frontend
echo -e "${CYAN}[2/2]${NC} Starting frontend dashboard..."
cd "$SCRIPT_DIR/frontend"
npm run dev -- --host &
FRONTEND_PID=$!
echo -e "${GREEN}[OK]${NC} Frontend starting on http://localhost:3000 (PID: $FRONTEND_PID)"

echo -e "\n${GREEN}${BOLD}"
echo "╔══════════════════════════════════════════╗"
echo "║     AutoTrader Pro is RUNNING! ✓         ║"
echo "╠══════════════════════════════════════════╣"
echo "║  Dashboard: http://localhost:3000        ║"
echo "║  API Docs:  http://localhost:8000/docs   ║"
echo "║  Press Ctrl+C to stop                    ║"
echo "╚══════════════════════════════════════════╝"
echo -e "${NC}"

# Wait for both processes
wait
