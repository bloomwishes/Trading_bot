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
    BACKEND_HOST: str = os.getenv("BACKEND_HOST", "0.0.0.0")
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

    # ── Watched Pairs (INR denominated) ────────────────────────────────
    WATCHED_PAIRS: list[str] = [
        "BTC/INR",
        "ETH/INR",
        "SOL/INR",
        "XRP/INR",
        "BNB/INR",
    ]

    # ── Paths ──────────────────────────────────────────────────────────
    PROJECT_ROOT: Path = PROJECT_ROOT
    DB_PATH: str = str(PROJECT_ROOT / "autotrader.db")
    LOG_DIR: Path = PROJECT_ROOT / "logs"

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
