# 🤖 AutoTrader Pro — Autonomous Multi-Agent Crypto Trading System

A full-stack, production-ready autonomous cryptocurrency trading platform engineered for **Indian Rupee (INR)** pairs on **CoinDCX** (with Binance fallback). Features a 5-agent multi-agent architecture, 12 quantitative & neural trading strategies, smart order routing (Market/Limit/TWAP), pre-trade risk gates, health watchdog monitoring, performance analytics (Sharpe/Sortino), and an interactive dark-cyberpunk React dashboard with mobile QR access.

![AutoTrader Pro](https://img.shields.io/badge/AutoTrader-Pro-00f0ff?style=for-the-badge&logo=bitcoin&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white)
![React](https://img.shields.io/badge/React-18-61DAFB?style=flat-square&logo=react&logoColor=black)
![FastAPI](https://img.shields.io/badge/FastAPI-0.104-009688?style=flat-square&logo=fastapi&logoColor=white)

---

## ✨ System Architecture: 5 Autonomous Agents

AutoTrader Pro is structured into 5 coordinated agent layers:

| Agent | Subsystem | Core Responsibilities |
| :--- | :--- | :--- |
| **Agent 1** | **Exchange Ingestion & Market Regimes** | CoinDCX REST & WebSocket streaming, Binance liquidity fallback, candle caches (15s TTL), and ADX/ATR/BB market regime detection. |
| **Agent 2** | **Strategy Engine & Signal Intelligence** | 12 active models (Triple Deep MLPs for BTC/ETH/ALTS, Mean Reversion, Scalping, Stat Arb, Breakout, etc.) with 2x dominance conflict resolution. |
| **Agent 3** | **Execution Engine & Order Routing** | Smart Order Router (`<5%` Market, `5-20%` Mid-Limit, `>20%` TWAP), Unified Position Tracker (VWAP & MTM), and square-root slippage simulation. |
| **Agent 4** | **Risk Management & Capital Guard** | Pre-Trade Risk Gate (10+ rules), multi-model position sizing (Half-Kelly, Volatility, ATR damper), correlation matrix, and circuit breaker. |
| **Agent 5** | **Monitoring, Analytics & Reporting** | System health watchdog (1-3-5-10 escalation), quantitative analytics (Sharpe, Sortino, Calmar, Expectancy), degradation detection, and Telegram alerts. |

---

## 📊 12 Quantitative & Neural Trading Strategies

| Strategy | Type | Description |
| :--- | :---: | :--- |
| **Neural Network BTC** | Machine Learning | 24-feature Deep MLP with online closed-trade reinforcement learning. |
| **Neural Network ETH** | Machine Learning | Specialized 24-feature Deep MLP optimized for Ethereum market dynamics. |
| **Neural Network ALTS**| Machine Learning | Specialized 24-feature Deep MLP for high-beta altcoins (SOL, XRP, BNB). |
| **Mean Reversion** | Statistical | Bollinger Band + RSI statistical extreme bounce engine. |
| **Scalping Engine** | Microstructure | Fast EMA ribbon momentum engine with tight stops and rapid exits. |
| **Statistical Arbitrage**| Quant / Coint | Z-score spread engine between co-integrated cryptocurrency pairs. |
| **Breakout Hunter** | Volatility | Bollinger Band squeeze detection with volume surge confirmation (1.25x+). |
| **MA Pullback** | Trend Following | Triple EMA (9/21/50) alignment entering on Stochastic RSI pullbacks. |
| **RSI Divergence** | Technical | Algorithmic swing-point detection for regular bullish/bearish divergences. |
| **Price Action** | Pattern | Algorithmic recognition of multi-candle candlestick patterns. |
| **Grid Trading** | Market Making | Geometric dynamic grid placement with automated deviation rebalancing. |
| **Sentiment LLM** | GenAI | Local Ollama LLM (`llama3` / `mistral`) market sentiment analysis. |

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
