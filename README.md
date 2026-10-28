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
├── ci/
│   └── github-actions-ci.yml # GitHub Actions CI workflow template (pytest + Vite build)
├── backend/                  # Python FastAPI backend
│   ├── main.py               # App entry point with async lifespan
│   ├── config.py             # Configuration & security settings
│   ├── database.py           # SQLite + SQLAlchemy
│   ├── models.py             # Database models
│   ├── schemas.py            # Pydantic schemas
│   ├── api/                  # REST API routes (auth-protected)
│   ├── engine/               # Trading strategies & neural models
│   ├── exchange/             # CoinDCX + Binance fallback client
│   ├── monitoring/           # Health watchdog, alerts & analytics
│   ├── scanner/              # Opportunity scanner
│   ├── risk/                 # Risk management, Kelly sizing & circuit breakers
│   ├── paper/                # Paper trading & slippage simulator
│   ├── scheduler/            # Background task scheduler
│   └── utils/                # Auth, logger & helpers
├── frontend/                 # React 18 + Tailwind cyberpunk dashboard
│   └── src/
│       ├── pages/            # 8 dashboard pages
│       ├── components/       # Reusable components
│       ├── hooks/            # Custom WebSocket & state hooks
│       └── utils/            # API client with X-API-Key injection
├── scripts/                  # Offline training routines & model JSONs
│   ├── optimization_results.json
│   ├── systematic_nn_optimization.py
│   ├── train_alts_model.py
│   ├── train_eth_model.py
│   ├── train_experimental_model.py
│   └── train_unified_model.py
├── tests/                    # Comprehensive Pytest suite (50 tests)
│   ├── conftest.py           # Test fixtures & auth setup
│   ├── test_agent2.py        # Strategies & regime intelligence
│   ├── test_agent3.py        # Execution & position tracking
│   ├── test_agent4.py        # Risk gates, Kelly sizing & emergency
│   ├── test_agent5.py        # Health monitor, analytics & alerts
│   ├── test_neural_net.py    # Deep MLP activations & reinforcement
│   └── test_security_and_live.py # Auth, CORS & order safety
├── LICENSE                   # MIT License
├── requirements.txt          # Root Python dependencies
├── setup.sh / setup.bat      # Auto-installer
├── start.sh / start.bat      # One-click launcher
└── .env.example              # Environment variables template
```

---

## 🔐 Security & Access Control

AutoTrader Pro implements a strict defense-in-depth security model:

1. **API Key Authentication**:
   - All state-mutating endpoints (`/api/bot/start`, `/api/bot/stop`, `/api/bot/mode`, `/api/trade/manual`, `/api/trade/close/*`, `/api/risk/*`, `/api/strategies/*`) require an API key when configured.
   - Supply the key via HTTP header `X-API-Key: <your_api_key>` or query parameter `?api_key=<your_api_key>`.
   - Set `API_KEY` in your `.env` file. Constant-time string comparison (`secrets.compare_digest`) prevents timing attacks.

2. **Localhost Binding by Default**:
   - `BACKEND_HOST` defaults to `127.0.0.1` (`BACKEND_PORT=8000`), preventing unintended exposure to the public internet or local area network.

3. **Restricted CORS Policy**:
   - Cross-Origin Resource Sharing is strictly locked to trusted local origins (`http://localhost:3000`, `http://127.0.0.1:3000`, `http://localhost:8000`, `http://127.0.0.1:8000`). Wildcard origin regexes are disabled.

4. **Live Mode Switch Safeguards**:
   - Switching from Paper to Live mode requires explicit authentication, `{"confirm": true}` in the payload, and an active pre-flight connectivity & signature test against CoinDCX.

5. **Live Order Execution Robustness**:
   - **Correct Symbol Format**: Strips public market prefixes (sends `BTCINR` instead of `B-BTCINR` to CoinDCX `/exchange/v1/orders/create`), adhering strictly to CoinDCX order specifications.
   - **Failure Verification**: If the exchange rejects an order (timeout, insufficient funds, invalid signature), the trade is **not** recorded as `OPEN` in the database.
   - **Atomic Close Orders**: If a live exit order fails on the exchange, the position remains `OPEN` and an alert is raised rather than incorrectly recording it as `CLOSED`.
   - **Exchange Precision & Step Sizing**: Quantities are automatically rounded according to exchange lot and precision limits (`BTCINR`: 6 decimals, `ETHINR`: 5, `SOLINR`: 3, `XRPINR`: 2, `BNBINR`: 4).
   - **Non-Blocking TWAP**: Delayed TWAP tranches execute in asynchronous background daemon threads, keeping the engine's main cycle responsive.

6. **Cloudflare Tunnel Caution**:
   - `mobile_tunnel.bat` is provided for mobile dashboard access via Cloudflare Quick Tunnels. **Never expose the dashboard through a public tunnel without configuring an `API_KEY` in `.env` first.**

---

## ⚠️ Strategy Credibility & Risk Disclosure

> [!WARNING]
> **Academic Integrity & Backtest Realities**
>
> The machine learning models and quantitative strategies included in AutoTrader Pro are **experimental prototypes** intended for algorithmic research and educational purposes.
>
> An honest evaluation of our systematic optimization and historical backtest data (`scripts/optimization_results.json`) reveals:
> - **Validation Accuracy**: 3-class classification (BUY / HOLD / SELL) validation accuracy hovers between **34% and 36%**, only marginally outperforming the 33.3% random baseline.
> - **Directional Accuracy**: Out-of-sample directional prediction accuracy is approximately **50%**.
> - **Drawdown Risk**: In simulated backtests across volatile cryptocurrency cycles, **6 out of 7 configurations lost capital**, with maximum drawdowns ranging from **70% to 90%** (even the highest gross-gain configuration experienced a severe ~70% drawdown).
> - **No Multi-Year Walk-Forward Guarantee**: The models have not undergone rigorous multi-year walk-forward validation across divergent macroeconomic regimes (such as multi-month liquidity droughts or systemic flash crashes).
>
> **Best Practices**:
> - **Start in Paper Trading**: Always run the bot in Paper Trading mode (`PAPER_MODE=true`) to evaluate execution speed, slippage, and signal behavior under live market conditions before risking real capital.
> - **Deploy Minimal Capital**: If you choose to enable Live trading, start with nominal capital that you can afford to lose entirely.
> - **Exchange-Side Hard Stops**: Whenever possible, ensure stop-loss orders are mirrored on the exchange side to protect against sudden software interruption or internet outages.

---

## 🧪 Automated Testing & Continuous Integration

The repository features an automated Pytest test suite covering all 5 agents and security subsystems:

```bash
# Run the complete test suite
pytest tests/ -v
```

### Test Suite Overview (50 Tests, 100% Pass Rate)

| Module | Scope |
| :--- | :--- |
| `tests/test_agent2.py` | Signal aggregation, 2x dominance conflict resolution, regime classification, and 24-feature neural representations. |
| `tests/test_agent3.py` | Smart Order Router (Market/Limit/TWAP), Unified Position Tracker (VWAP & MTM), slippage simulation, and execution exits. |
| `tests/test_agent4.py` | Half-Kelly & volatility sizing, correlation matrix limits, drawdown monitoring, and emergency circuit breakers. |
| `tests/test_agent5.py` | Health monitor watchdog, performance analytics (Sharpe, Sortino, Calmar), alerting, and daily reports. |
| `tests/test_neural_net.py` | Deep MLP activations, weight serialization, and closed-trade reinforcement learning. |
| `tests/test_security_and_live.py` | API key authentication, CORS lockdown, CoinDCX symbol formatting, step rounding, and order failure resilience. |

**Continuous Integration**: Automated test execution and frontend builds workflow template is located at `ci/github-actions-ci.yml` (can be mapped to `.github/workflows/ci.yml`).

---

## 🔌 API Endpoints

All state-modifying endpoints (`POST`, `PUT`, `DELETE`) require the `X-API-Key` header when an `API_KEY` is configured:

| Method | Endpoint | Auth Required | Description |
|--------|----------|:---:|-------------|
| GET | `/api/status` | No | Bot status & portfolio summary |
| POST | `/api/bot/start` | **Yes** | Start the trading bot |
| POST | `/api/bot/stop` | **Yes** | Stop the trading bot |
| POST | `/api/bot/mode` | **Yes** | Toggle paper/live mode (requires `confirm: true`) |
| GET | `/api/trades/open` | No | Open positions |
| GET | `/api/trades/history` | No | Trade history with filters |
| POST | `/api/trade/manual` | **Yes** | Place a manual trade |
| POST | `/api/trade/close/{id}` | **Yes** | Close a specific trade |
| GET | `/api/opportunities` | No | Scanner results |
| GET | `/api/strategies` | No | Strategy configurations |
| PUT | `/api/strategies/{name}` | **Yes** | Update strategy config |
| GET | `/api/risk` | No | Risk settings |
| PUT | `/api/risk` | **Yes** | Update risk settings |
| POST | `/api/risk/emergency-shutdown` | **Yes** | Emergency liquidations & freeze |
| POST | `/api/risk/resume-trading` | **Yes** | Resume normal trading |
| GET | `/api/portfolio/snapshots` | No | Portfolio history |
| GET | `/api/llm/decisions` | No | AI decision log |
| WS | `/ws/logs` | No | Real-time log streaming |
| WS | `/ws/prices` | No | Real-time price updates |

Full interactive API docs: **http://localhost:8000/docs** (Swagger UI)

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
| `API_KEY` | *(empty)* | Secret key for REST API authentication |
| `ALLOWED_ORIGINS` | `http://localhost:3000,...` | Comma-separated list of allowed CORS origins |
| `BACKEND_HOST` | `127.0.0.1` | Host address to bind the API server |
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

Distributed under the MIT License. See [LICENSE](LICENSE) for full terms.
