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
from backend.monitoring.health_monitor import health_monitor
from backend.monitoring.alert_manager import alert_manager
from backend.monitoring.strategy_tracker import strategy_tracker

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


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# WS /ws/updates — Comprehensive real-time state broadcast
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.websocket("/ws/updates")
async def ws_updates(websocket: WebSocket) -> None:
    """
    Broadcasts real-time trading bot status, portfolio balance, system health,
    strategy status, and active alerts to connected UI dashboards every 2 seconds.
    """
    await websocket.accept()
    logger.info("Updates WebSocket connected.")

    try:
        engine = websocket.app.state.engine
    except Exception:
        await websocket.send_json({"error": "Engine not initialised"})
        await websocket.close(code=1011)
        return

    try:
        while True:
            # 1. Portfolio & Trades
            total_value = 0.0
            cash = 0.0
            open_count = 0
            try:
                if engine.mode == "paper":
                    paper = engine.paper_trader
                    cash = float(getattr(paper, "balance", 0.0))
                    total_value = cash
                    if hasattr(paper, "positions"):
                        open_count = len(paper.positions)
                        for pos in paper.positions.values():
                            total_value += pos.get("entry_price", 0) * pos.get("quantity", 0)
                else:
                    exchange = engine.exchange_manager
                    balance = exchange.fetch_balance() if hasattr(exchange, "fetch_balance") else {}
                    cash = float(balance.get("INR", {}).get("free", 0)) if isinstance(balance, dict) else 0.0
                    total_value = float(balance.get("INR", {}).get("total", cash)) if isinstance(balance, dict) else cash
            except Exception:
                pass

            # 2. Health & Alerts
            health_stat = health_monitor.get_health_status()
            recent_alerts = alert_manager.get_recent_alerts(limit=5)

            # 3. Strategy health & weights
            strategies_state = strategy_tracker.get_strategy_report()

            # 4. Signals
            signals_data = []
            if hasattr(engine, "signal_aggregator") and hasattr(engine.signal_aggregator, "history"):
                signals_data = [
                    {
                        "pair": s.pair,
                        "action": s.action,
                        "strategy": s.strategy_name,
                        "strength": s.strength,
                        "reason": s.reason,
                    }
                    for s in engine.signal_aggregator.history[-5:]
                ]

            payload = {
                "type": "updates",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "bot_status": {
                    "running": engine.running,
                    "mode": engine.mode,
                },
                "portfolio": {
                    "total_value": round(total_value, 2),
                    "cash": round(cash, 2),
                    "active_trades": open_count,
                },
                "health": {
                    "status": health_stat.get("overall_status", "healthy"),
                    "healthy": health_stat.get("healthy", True),
                    "checks": health_stat.get("checks", {}),
                },
                "strategies": strategies_state,
                "recent_alerts": recent_alerts,
                "signals": signals_data,
            }

            await websocket.send_text(json.dumps(payload))
            await asyncio.sleep(2.0)

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.debug("Updates WS error: %s", exc)
    finally:
        logger.info("Updates WebSocket disconnected.")

