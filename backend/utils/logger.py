"""
AutoTrader Pro - Structured Logger
Console + file logging with database persistence and WebSocket broadcast.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import List

from websockets.legacy.server import WebSocketServerProtocol

from backend.config import settings

# ---------------------------------------------------------------------------
# WebSocket connections pool (populated by the API layer)
# ---------------------------------------------------------------------------
ws_connections: List[WebSocketServerProtocol] = []

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
                    created_at=datetime.utcnow(),
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
                "timestamp": datetime.utcnow().isoformat(),
            }
        )

        stale: list[WebSocketServerProtocol] = []

        for ws in ws_connections:
            try:
                # Schedule the coroutine on the running event loop (if any)
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.ensure_future(ws.send(payload))
                else:
                    loop.run_until_complete(ws.send(payload))
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
