# 🤖 AutoTrader Pro — Autonomous Crypto Trading System

A full-stack, production-ready autonomous cryptocurrency trading bot with 5 strategies, real-time dashboard, LLM-powered sentiment analysis, paper trading, and market opportunity scanning.

![AutoTrader Pro](https://img.shields.io/badge/AutoTrader-Pro-00f0ff?style=for-the-badge&logo=bitcoin&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white)
![React](https://img.shields.io/badge/React-18-61DAFB?style=flat-square&logo=react&logoColor=black)
![FastAPI](https://img.shields.io/badge/FastAPI-0.104-009688?style=flat-square&logo=fastapi&logoColor=white)

---

## ✨ Features

### 📊 5 Trading Strategies
| Strategy | Description |
|----------|-------------|
| **MA Pullback** | EMA 9/21/50 with StochRSI confirmation |
| **Breakout Hunter** | Bollinger Band squeeze breakout with volume confirmation |
| **RSI Divergence** | Bullish/bearish divergence detection on 15m/1h candles |
| **Sentiment LLM** | Ollama AI-powered analysis with confidence scoring |
| **Grid Trading** | Automated grid orders with auto-rebalancing |

### 🛡️ Risk Management
- Configurable position sizing (default 5% max per trade)
- Daily loss circuit breaker
- Per-trade stop loss & take profit
- Trailing stop loss (activates after 1.5% profit)
- Max open trades limit

### 📡 Opportunity Scanner
- Scans ALL CoinDCX INR pairs every 60 seconds
- Detects: RSI signals, volume spikes, price momentum, BB squeezes
- Composite scoring with auto-trade option

### 🖥️ Real-Time Dashboard
- Dark cyberpunk UI with 8 pages
- Live portfolio tracking with animated values
- Paper/Live mode toggle with confirmation
- WebSocket-powered real-time logs and prices

---

## 🚀 Quick Start

### Prerequisites
- **Python 3.10+** — [Download](https://www.python.org/downloads/)
- **Node.js 18+** — [Download](https://nodejs.org/)
- **Ollama** (optional, for AI strategy) — [Download](https://ollama.com/download)

### Step 1: Clone & Setup
```bash
# Navigate to the project
cd BOT

# Run setup (installs all dependencies)
# Linux/Mac:
chmod +x setup.sh && ./setup.sh

# Windows:
setup.bat
```

### Step 2: Configure API Keys

Edit the `.env` file with your exchange API keys:

```env
# CoinDCX API (Required for live trading)
COINDCX_API_KEY=your_api_key_here
COINDCX_API_SECRET=your_api_secret_here
```

#### Getting CoinDCX API Keys
1. Go to [CoinDCX](https://coindcx.com)
2. Log in → Navigate to **API Dashboard**
3. Click **Create New API Key**
4. Enable **Trade** permission
5. Copy the API Key and Secret to your `.env` file

> ⚠️ **Keep your API keys secret!** Never commit `.env` to version control.

### Step 3: Launch
```bash
# Linux/Mac:
./start.sh

# Windows:
start.bat
```

### Step 4: Open Dashboard
Navigate to **http://localhost:3000** in your browser.

---

## 📁 Project Structure

```
BOT/
├── backend/              # Python FastAPI backend
│   ├── main.py           # App entry point
│   ├── config.py         # Configuration
│   ├── database.py       # SQLite + SQLAlchemy
│   ├── models.py         # Database models
│   ├── schemas.py        # Pydantic schemas
│   ├── api/              # REST API routes
│   ├── engine/           # Trading strategies
│   ├── exchange/         # CoinDCX + Binance
│   ├── scanner/          # Opportunity scanner
│   ├── risk/             # Risk management
│   ├── paper/            # Paper trading
│   ├── scheduler/        # Task scheduler
│   └── utils/            # Utilities
├── frontend/             # React dashboard
│   └── src/
│       ├── pages/        # 8 dashboard pages
│       ├── components/   # Reusable components
│       └── hooks/        # Custom hooks
├── setup.sh / setup.bat  # Auto-installer
├── start.sh / start.bat  # One-click launcher
└── .env                  # API keys (create from .env.example)
```

---

## 🔌 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/status` | Bot status & portfolio summary |
| POST | `/api/bot/start` | Start the trading bot |
| POST | `/api/bot/stop` | Stop the trading bot |
| POST | `/api/bot/mode` | Toggle paper/live mode |
| GET | `/api/trades/open` | Open positions |
| GET | `/api/trades/history` | Trade history with filters |
| POST | `/api/trade/manual` | Place a manual trade |
| POST | `/api/trade/close/{id}` | Close a specific trade |
| GET | `/api/opportunities` | Scanner results |
| GET | `/api/strategies` | Strategy configurations |
| PUT | `/api/strategies/{name}` | Update strategy config |
| GET | `/api/risk` | Risk settings |
| PUT | `/api/risk` | Update risk settings |
| GET | `/api/portfolio/snapshots` | Portfolio history |
| GET | `/api/llm/decisions` | AI decision log |
| WS | `/ws/logs` | Real-time log streaming |
| WS | `/ws/prices` | Real-time price updates |

Full API docs: **http://localhost:8000/docs** (Swagger UI)

---

## 🧪 Paper Trading

The bot starts in **Paper Trading** mode by default:
- Uses live market prices but simulates trades
- Virtual balance: ₹10,000 (configurable)
- All strategies work identically
- Tracks P&L, win rate, and drawdown
- Switch to Live mode from the dashboard (requires confirmation)

---

## 🤖 LLM Strategy (Ollama)

Strategy 4 uses a local LLM for sentiment analysis:

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull the model
ollama pull llama3

# Start Ollama server
ollama serve
```

The bot queries Ollama with market data and only acts on high-confidence (>75%) signals. If Ollama is unavailable, Strategy 4 automatically disables itself.

---

## ⚙️ Configuration

All settings are editable from the dashboard or via the `.env` file:

| Setting | Default | Description |
|---------|---------|-------------|
| `PAPER_MODE` | `true` | Start in paper trading mode |
| `PAPER_BALANCE` | `10000` | Virtual balance (₹) |
| `MAX_POSITION_PCT` | `5` | Max position size (% of portfolio) |
| `MAX_OPEN_TRADES` | `5` | Max concurrent open trades |
| `DAILY_LOSS_LIMIT_PCT` | `3` | Stop trading if daily loss exceeds this % |
| `DEFAULT_STOP_LOSS_PCT` | `1.5` | Per-trade stop loss % |
| `DEFAULT_TAKE_PROFIT_PCT` | `3.0` | Per-trade take profit % |

---

## ⚠️ Disclaimer

**This software is for educational and research purposes.** Cryptocurrency trading involves substantial risk of loss. Past performance does not guarantee future results. The authors are not responsible for any financial losses incurred through use of this software. Always start with paper trading and never invest more than you can afford to lose.

---

## 📝 License

MIT License — see [LICENSE](LICENSE) for details.
