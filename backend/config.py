"""
AutoTrader Pro - Configuration Module
Loads environment variables with sensible defaults for all bot settings.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Resolve project root (BOT/) and load .env from there
# ---------------------------------------------------------------------------
_THIS_DIR = Path(__file__).resolve().parent          # backend/
PROJECT_ROOT = _THIS_DIR.parent                       # BOT/
ENV_PATH = PROJECT_ROOT / ".env"

load_dotenv(dotenv_path=ENV_PATH)


class Settings:
    """Centralised settings populated from environment variables."""

    # ── Security & Authentication ──────────────────────────────────────
    API_KEY: str = os.getenv("API_KEY", "")
    ALLOWED_ORIGINS: list[str] = [
        origin.strip()
        for origin in os.getenv(
            "ALLOWED_ORIGINS",
            "http://localhost:3000,http://127.0.0.1:3000,http://localhost:8000,http://127.0.0.1:8000,http://localhost:5173,http://127.0.0.1:5173",
        ).split(",")
        if origin.strip()
    ]

    # ── Exchange: CoinDCX ──────────────────────────────────────────────
    COINDCX_API_KEY: str = os.getenv("COINDCX_API_KEY", "")
    COINDCX_API_SECRET: str = os.getenv("COINDCX_API_SECRET", "")

    # ── Exchange: Binance (fallback) ───────────────────────────────────
    BINANCE_API_KEY: str = os.getenv("BINANCE_API_KEY", "")
    BINANCE_API_SECRET: str = os.getenv("BINANCE_API_SECRET", "")

    # ── Ollama LLM ─────────────────────────────────────────────────────
    OLLAMA_HOST: str = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3")
    OLLAMA_FALLBACK_MODEL: str = os.getenv("OLLAMA_FALLBACK_MODEL", "mistral")

    # ── Trading Mode ───────────────────────────────────────────────────
    PAPER_MODE: bool = os.getenv("PAPER_MODE", "true").lower() in ("true", "1", "yes")
    PAPER_BALANCE: float = float(os.getenv("PAPER_BALANCE", "10000"))

    # ── Server ─────────────────────────────────────────────────────────
    BACKEND_HOST: str = os.getenv("BACKEND_HOST", "127.0.0.1")
    BACKEND_PORT: int = int(os.getenv("BACKEND_PORT", "8000"))
    FRONTEND_PORT: int = int(os.getenv("FRONTEND_PORT", "3000"))

    # ── Risk Defaults ──────────────────────────────────────────────────
    MAX_POSITION_PCT: float = float(os.getenv("MAX_POSITION_PCT", "5"))
    MAX_OPEN_TRADES: int = int(os.getenv("MAX_OPEN_TRADES", "5"))
    DAILY_LOSS_LIMIT_PCT: float = float(os.getenv("DAILY_LOSS_LIMIT_PCT", "3"))
    DEFAULT_STOP_LOSS_PCT: float = float(os.getenv("DEFAULT_STOP_LOSS_PCT", "1.5"))
    DEFAULT_TAKE_PROFIT_PCT: float = float(os.getenv("DEFAULT_TAKE_PROFIT_PCT", "3.0"))
    TRAILING_STOP_ACTIVATE_PCT: float = float(os.getenv("TRAILING_STOP_ACTIVATE_PCT", "1.5"))
    TRAILING_STOP_TRAIL_PCT: float = float(os.getenv("TRAILING_STOP_TRAIL_PCT", "0.5"))
    WEEKLY_LOSS_LIMIT_PCT: float = float(os.getenv("WEEKLY_LOSS_LIMIT_PCT", "7.0"))
    TOTAL_DRAWDOWN_LIMIT_PCT: float = float(os.getenv("TOTAL_DRAWDOWN_LIMIT_PCT", "15.0"))
    MAX_TOTAL_EXPOSURE_PCT: float = float(os.getenv("MAX_TOTAL_EXPOSURE_PCT", "50.0"))
    MAX_SINGLE_DIRECTION_EXPOSURE_PCT: float = float(os.getenv("MAX_SINGLE_DIRECTION_EXPOSURE_PCT", "35.0"))
    MIN_RISK_REWARD_RATIO: float = float(os.getenv("MIN_RISK_REWARD_RATIO", "1.5"))
    MAX_CORRELATED_POSITIONS: int = int(os.getenv("MAX_CORRELATED_POSITIONS", "2"))
    CORRELATION_THRESHOLD: float = float(os.getenv("CORRELATION_THRESHOLD", "0.7"))
    COOLDOWN_AFTER_CONSECUTIVE_LOSSES: int = int(os.getenv("COOLDOWN_AFTER_CONSECUTIVE_LOSSES", "3"))
    COOLDOWN_DURATION_MINUTES: int = int(os.getenv("COOLDOWN_DURATION_MINUTES", "60"))
    REDUCE_SIZE_HIGH_VOLATILITY: bool = os.getenv("REDUCE_SIZE_HIGH_VOLATILITY", "True").lower() in ("true", "1")

    # ── Watched Pairs (INR denominated) ────────────────────────────────
    WATCHED_PAIRS: list[str] = [
        "BTC/INR",
        "ETH/INR",
        "SOL/INR",
        "XRP/INR",
        "BNB/INR",
    ]

    # ── Alerting & Notifications ───────────────────────────────────────
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")
    ALERT_WEBHOOK_URL: str = os.getenv("ALERT_WEBHOOK_URL", "")
    ALERTS_ENABLED: bool = os.getenv("ALERTS_ENABLED", "true").lower() in ("true", "1", "yes")

    # ── Market Data Cache & Stream Settings ────────────────────
    CANDLE_CACHE_TTL_SEC: int = int(os.getenv("CANDLE_CACHE_TTL_SEC", "15"))
    MARKET_DATA_CACHE_TTL_SEC: int = int(os.getenv("MARKET_DATA_CACHE_TTL_SEC", "15"))
    ORDERBOOK_CACHE_TTL_SEC: int = int(os.getenv("ORDERBOOK_CACHE_TTL_SEC", "5"))
    SENTIMENT_CACHE_TTL_SEC: int = int(os.getenv("SENTIMENT_CACHE_TTL_SEC", "300"))
    COINDCX_WS_STREAM_URL: str = os.getenv(
        "COINDCX_WS_STREAM_URL",
        "wss://stream.coindcx.com/socket.io/?EIO=4&transport=websocket",
    )

    # ── Paths ──────────────────────────────────────────────────────────
    PROJECT_ROOT: Path = PROJECT_ROOT
    DB_PATH: str = str(PROJECT_ROOT / "autotrader.db")
    LOG_DIR: Path = PROJECT_ROOT / "logs"

    def reload_env(self) -> None:
        """Reload configuration from .env dynamically."""
        load_dotenv(dotenv_path=ENV_PATH, override=True)
        self.API_KEY = os.getenv("API_KEY", "")
        self.COINDCX_API_KEY = os.getenv("COINDCX_API_KEY", "")
        self.COINDCX_API_SECRET = os.getenv("COINDCX_API_SECRET", "")
        self.BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "")
        self.BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET", "")

    def __repr__(self) -> str:
        mode = "PAPER" if self.PAPER_MODE else "LIVE"
        return (
            f"<Settings mode={mode} pairs={self.WATCHED_PAIRS} "
            f"backend={self.BACKEND_HOST}:{self.BACKEND_PORT}>"
        )


# ---------------------------------------------------------------------------
# Global singleton – import as  `from backend.config import settings`
# ---------------------------------------------------------------------------
settings = Settings()
