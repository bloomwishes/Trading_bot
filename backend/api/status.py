"""
AutoTrader Pro — Status Router
==============================
GET /api/status  →  bot running status, mode, portfolio summary, win rate, uptime.
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import Trade
from backend.monitoring.health_monitor import health_monitor
from backend.monitoring.alert_manager import alert_manager
from backend.monitoring.performance_analytics import PerformanceAnalytics

router = APIRouter(prefix="/api", tags=["status"])


def _calc_win_rate(db: Session) -> float:
    """Return win-rate (0.0–100.0) across all closed trades."""
    closed = db.query(Trade).filter(Trade.status == "CLOSED").all()
    if not closed:
        return 0.0
    winners = sum(1 for t in closed if (t.pnl or 0) > 0)
    return round(winners / len(closed) * 100, 2)


def _seconds_to_human(secs: float) -> str:
    """Convert seconds elapsed to a human-friendly string."""
    secs = int(secs)
    days, rem = divmod(secs, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds = divmod(rem, 60)
    parts: list[str] = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    parts.append(f"{seconds}s")
    return " ".join(parts)


@router.get("/status", summary="Bot status overview")
async def get_status(request: Request, db: Session = Depends(get_db)) -> dict[str, Any]:
    """
    Returns a comprehensive snapshot of the bot's current state:
    - running / mode / uptime
    - portfolio value, cash balance, active-trade count
    - historical win rate
    """
    engine = request.app.state.engine
    scheduler = request.app.state.scheduler
    start_time: float = getattr(request.app.state, "start_time", time.time())

    # ── Portfolio value ──────────────────────────────────────────────────
    total_value: float = 0.0
    cash_balance: float = 0.0
    try:
        if engine.mode == "paper":
            paper = engine.paper_trader
            cash_balance = float(getattr(paper, "balance", 0))
            total_value = cash_balance
            # Add value of open positions
            if hasattr(paper, "positions"):
                for pos in paper.positions.values():
                    total_value += pos.get("entry_price", 0) * pos.get("quantity", 0)
        else:
            exchange = engine.exchange_manager
            balance = exchange.fetch_balance() if hasattr(exchange, "fetch_balance") else {}
            cash_balance = float(balance.get("INR", {}).get("free", 0)) if isinstance(balance, dict) else 0.0
            total_value = float(balance.get("INR", {}).get("total", cash_balance)) if isinstance(balance, dict) else cash_balance
    except Exception:
        pass

    # ── Active trades ────────────────────────────────────────────────────
    open_trades = db.query(Trade).filter(Trade.status == "OPEN").count()

    # ── Win rate ─────────────────────────────────────────────────────────
    win_rate = _calc_win_rate(db)

    # ── Uptime ───────────────────────────────────────────────────────────
    uptime_secs = time.time() - start_time

    from backend.utils.tunnel_manager import tunnel_manager
    tunnel_info = tunnel_manager.get_info()

    # ── Health, Analytics & Alerts Summaries (Agent 5) ───────────────────
    health_stat = health_monitor.get_health_status()

    closed_trades = db.query(Trade).filter(Trade.status == "CLOSED").all()
    analytics = PerformanceAnalytics.calculate_full_report(closed_trades, period="all")

    active_alerts = alert_manager.get_recent_alerts(limit=5)

    # Market regimes per pair
    regimes = {}
    if hasattr(engine, "regime_detector") and engine.regime_detector:
        for pair in getattr(engine, "watched_pairs", ["BTC/INR", "ETH/INR"]):
            reg = engine.regime_detector.get_last_regime(pair)
            regimes[pair] = reg or "NEUTRAL"

    return {
        "running": engine.running,
        "scheduler_running": scheduler.is_running,
        "mode": engine.mode,
        "uptime_seconds": round(uptime_secs, 1),
        "uptime_human": _seconds_to_human(uptime_secs),
        "portfolio": {
            "total_value_inr": round(total_value, 2),
            "cash_balance_inr": round(cash_balance, 2),
            "active_trades": open_trades,
            "win_rate_pct": win_rate,
        },
        "health_summary": {
            "status": health_stat.get("overall_status", "healthy"),
            "healthy": health_stat.get("healthy", True),
            "max_consecutive_failures": health_stat.get("max_consecutive_failures", 0),
        },
        "analytics_summary": {
            "total_trades": analytics["summary"]["total_trades"],
            "win_rate": analytics["summary"]["win_rate"],
            "total_pnl": analytics["summary"]["total_pnl"],
            "profit_factor": analytics["summary"]["profit_factor"],
            "expectancy": analytics["summary"]["expectancy"],
        },
        "active_alerts": active_alerts,
        "regimes": regimes,
        "tunnel": tunnel_info,
    }


@router.get("/status/health", summary="Detailed system health checks")
async def get_health() -> dict[str, Any]:
    """
    Returns granular health checks across all components:
    - CoinDCX API responsiveness & latency
    - SQLite Database connection
    - APScheduler heartbeat
    - WebSocket streaming connectivity
    - Market candle data freshness
    - Escalation ladder failure counts
    """
    return health_monitor.get_health_status()


@router.get("/tunnel", summary="Cloudflare mobile tunnel and QR code metadata")
async def get_tunnel() -> dict[str, Any]:
    """Return active Cloudflare tunnel URL and local Wi-Fi dashboard access link."""
    from backend.utils.tunnel_manager import tunnel_manager
    return tunnel_manager.get_info()

