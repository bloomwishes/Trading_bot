"""
AutoTrader Pro - Structured Logger
Console + file logging with database persistence and WebSocket broadcast.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import WebSocket

from backend.config import settings

# Real-time AI agent status tracking
ai_status: dict[str, Any] = {
    "status": "idle",
    "current_task": "Idle",
    "last_active": None,
    "model": settings.OLLAMA_MODEL,
    "fallback_model": settings.OLLAMA_FALLBACK_MODEL,
    "prime_directive": "AUTONOMOUS ZERO-RUIN: Capital preservation is existential. If capital is depleted, the bot is dead. Operate A-to-Z to keep the bot running successfully without losing capital.",
}

# ---------------------------------------------------------------------------
# WebSocket connections pool (populated by the API layer)
# ---------------------------------------------------------------------------
ws_connections: List[WebSocket] = []

# ---------------------------------------------------------------------------
# Ensure log directory exists
# ---------------------------------------------------------------------------
LOG_DIR: Path = settings.LOG_DIR
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE: Path = LOG_DIR / "autotrader.log"

# ---------------------------------------------------------------------------
# Standard Python logger
# ---------------------------------------------------------------------------
_formatter = logging.Formatter(
    fmt="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# Console handler
_console_handler = logging.StreamHandler()
_console_handler.setLevel(logging.DEBUG)
_console_handler.setFormatter(_formatter)

# File handler (append mode, UTF-8 for ₹ symbol)
_file_handler = logging.FileHandler(str(LOG_FILE), encoding="utf-8")
_file_handler.setLevel(logging.DEBUG)
_file_handler.setFormatter(_formatter)

_logger = logging.getLogger("autotrader")
_logger.setLevel(logging.DEBUG)
_logger.addHandler(_console_handler)
_logger.addHandler(_file_handler)
_logger.propagate = False


class BotLogger:
    """
    High-level logger that:
      1. Writes to the Python logger (console + file).
      2. Persists every entry to the BotLog database table.
      3. Broadcasts the entry to all connected WebSocket clients.
    """

    def __init__(self) -> None:
        self._logger = _logger

    # ── Public helpers ─────────────────────────────────────────────────
    def info(self, message: str) -> None:
        self._log("INFO", message)

    def warning(self, message: str) -> None:
        self._log("WARNING", message)

    def error(self, message: str) -> None:
        self._log("ERROR", message)

    def critical(self, message: str) -> None:
        self._log("CRITICAL", message)

    def debug(self, message: str) -> None:
        self._log("DEBUG", message)

    # ── Internal ───────────────────────────────────────────────────────
    def _log(self, level: str, message: str) -> None:
        """Central dispatch: console/file → DB → WebSocket."""
        # 1. Python logger
        log_fn = getattr(self._logger, level.lower(), self._logger.info)
        log_fn(message)

        # 2. Database persistence (lazy import to break circular deps)
        self._save_to_db(level, message)

        # 3. WebSocket broadcast (fire-and-forget)
        self._broadcast(level, message)

    def _save_to_db(self, level: str, message: str) -> None:
        """Write a BotLog row inside its own short-lived session."""
        try:
            from backend.database import SessionLocal
            from backend.models import BotLog

            session = SessionLocal()
            try:
                entry = BotLog(
                    level=level,
                    message=message,
                    created_at=datetime.now(timezone.utc),
                )
                session.add(entry)
                session.commit()
            except Exception:
                session.rollback()
            finally:
                session.close()
        except Exception:
            # During early startup the DB may not be initialised yet – silently skip
            pass

    def _broadcast(self, level: str, message: str) -> None:
        """Send a JSON-encoded log entry to every connected WebSocket."""
        if not ws_connections:
            return

        payload = json.dumps(
            {
                "type": "log",
                "level": level,
                "message": message,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

        stale: list[WebSocket] = []

        for ws in ws_connections:
            try:
                # Schedule the coroutine on the running event loop (if any)
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.ensure_future(ws.send_text(payload))
                else:
                    loop.run_until_complete(ws.send_text(payload))
            except Exception:
                stale.append(ws)

        # Prune dead connections
        for ws in stale:
            try:
                ws_connections.remove(ws)
            except ValueError:
                pass


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------
bot_logger = BotLogger()


# ---------------------------------------------------------------------------
# Structured Event Logging Helpers (Agent 5)
# ---------------------------------------------------------------------------
def _format_event_entry(
    event_type: str,
    data: Dict[str, Any],
    trace_id: Optional[str] = None,
    category: str = "GENERAL",
) -> Dict[str, Any]:
    """Build a uniform structured event dict."""
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": event_type,
        "trace_id": trace_id or str(uuid.uuid4()),
        "agent": "AutoTrader",
        "category": category,
        "data": data,
    }


def log_trade_event(
    event_type: str,
    trade_data: Dict[str, Any],
    trace_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Log a structured trade lifecycle event (ORDER_PLACED, TRADE_OPENED, TRADE_CLOSED, etc.).
    Emits formatted string to bot_logger.info and returns the event payload.
    """
    payload = _format_event_entry(event_type, trade_data, trace_id, category="TRADE")
    msg = f"[EVENT:TRADE] {event_type} | trace={payload['trace_id'][:8]} | {json.dumps(trade_data, default=str)}"
    bot_logger.info(msg)
    return payload


def log_signal_event(
    event_type: str,
    signal_data: Dict[str, Any],
    trace_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Log a structured signal generation/aggregation event (SIGNAL_GENERATED, SIGNAL_AGGREGATED, etc.).
    Emits formatted string to bot_logger.info and returns the event payload.
    """
    payload = _format_event_entry(event_type, signal_data, trace_id, category="SIGNAL")
    msg = f"[EVENT:SIGNAL] {event_type} | trace={payload['trace_id'][:8]} | {json.dumps(signal_data, default=str)}"
    bot_logger.info(msg)
    return payload


def log_risk_event(
    event_type: str,
    risk_data: Dict[str, Any],
    trace_id: Optional[str] = None,
    level: str = "WARNING",
) -> Dict[str, Any]:
    """
    Log a structured risk management event (RISK_GATE_REJECT, DRAWDOWN_BREACH, EMERGENCY_SHUTDOWN, etc.).
    Emits formatted string to bot_logger with appropriate level and returns the event payload.
    """
    payload = _format_event_entry(event_type, risk_data, trace_id, category="RISK")
    msg = f"[EVENT:RISK] {event_type} | trace={payload['trace_id'][:8]} | {json.dumps(risk_data, default=str)}"
    if level.upper() == "CRITICAL":
        bot_logger.critical(msg)
    elif level.upper() == "ERROR":
        bot_logger.error(msg)
    elif level.upper() == "INFO":
        bot_logger.info(msg)
    else:
        bot_logger.warning(msg)
    return payload

