"""
AutoTrader Pro — WebSocket Endpoints
=====================================
WS /ws/logs    →  real-time log stream (broadcast from bot_logger)
WS /ws/prices  →  live price ticker updates every 5 seconds
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.utils.logger import ws_connections

logger = logging.getLogger("autotrader.ws")

router = APIRouter(tags=["websockets"])

# ── Default watched pairs (also used when engine has no explicit list) ──────
DEFAULT_WATCHED_PAIRS: list[str] = [
    "BTC/INR",
    "ETH/INR",
    "XRP/INR",
    "SOL/INR",
    "DOGE/INR",
    "ADA/INR",
    "MATIC/INR",
    "DOT/INR",
    "AVAX/INR",
    "LINK/INR",
]

PRICE_UPDATE_INTERVAL: float = 5.0  # seconds


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# WS /ws/logs — Real-time log broadcast
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.websocket("/ws/logs")
async def ws_logs(websocket: WebSocket) -> None:
    """
    Accepts a WebSocket connection and registers it in the global
    ``ws_connections`` list so that ``bot_logger`` can broadcast log
    entries to all connected clients.

    Message format sent to client::

        {"level": "INFO", "message": "…", "timestamp": "2026-06-15T…"}

    The client may optionally send messages (ignored — the socket is
    used for server→client push only).  The connection is removed on
    disconnect.
    """
    await websocket.accept()
    ws_connections.append(websocket)
    logger.info("Log WebSocket connected. Total connections: %d", len(ws_connections))

    try:
        # Keep the connection alive by waiting for (and ignoring) client msgs
        while True:
            # This will raise WebSocketDisconnect when the client disconnects
            _ = await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.debug("Log WS error: %s", exc)
    finally:
        if websocket in ws_connections:
            ws_connections.remove(websocket)
        logger.info("Log WebSocket disconnected. Remaining: %d", len(ws_connections))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# WS /ws/prices — Live price ticker feed
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _resolve_watched_pairs(websocket: WebSocket) -> list[str]:
    """
    Try to read the watched-pair list from the engine stored on app state;
    fall back to the default list.
    """
    try:
        engine = websocket.app.state.engine
        pairs = getattr(engine, "watched_pairs", None)
        if pairs:
            return list(pairs)
    except Exception:
        pass
    return DEFAULT_WATCHED_PAIRS


async def _fetch_ticker_safe(engine: Any, pair: str) -> dict[str, Any]:
    """
    Fetch ticker data for *pair* from the exchange manager.
    Returns a normalised dict even if the call fails.
    """
    try:
        exchange = engine.exchange_manager
        ticker = exchange.get_ticker(pair)
        if isinstance(ticker, dict):
            return {
                "price": float(ticker.get("last_price", 0)),
                "change_24h": float(ticker.get("change_24h", 0)),
                "volume": float(ticker.get("volume", 0)),
            }
        return {"price": float(ticker), "change_24h": 0.0, "volume": 0.0}
    except Exception:
        return {"price": 0.0, "change_24h": 0.0, "volume": 0.0}


@router.websocket("/ws/prices")
async def ws_prices(websocket: WebSocket) -> None:
    """
    Accepts a WebSocket connection and pushes live price updates for all
    watched pairs every ``PRICE_UPDATE_INTERVAL`` seconds.

    Message format::

        {
          "BTC/INR": {"price": 5500000.0, "change_24h": 2.3, "volume": 12345678.0},
          "ETH/INR": { … },
          …,
          "timestamp": "2026-06-15T12:00:05Z"
        }
    """
    await websocket.accept()
    logger.info("Price WebSocket connected.")

    try:
        engine = websocket.app.state.engine
    except Exception:
        await websocket.send_json({"error": "Engine not initialised"})
        await websocket.close(code=1011)
        return

    watched = _resolve_watched_pairs(websocket)

    try:
        while True:
            payload: dict[str, Any] = {}

            for pair in watched:
                payload[pair] = await asyncio.to_thread(_fetch_ticker_safe, engine, pair)

            payload["timestamp"] = datetime.now(timezone.utc).isoformat()

            await websocket.send_text(json.dumps(payload))
            await asyncio.sleep(PRICE_UPDATE_INTERVAL)

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.debug("Price WS error: %s", exc)
    finally:
        logger.info("Price WebSocket disconnected.")
