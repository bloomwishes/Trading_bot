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
from backend.config import settings
from backend.monitoring.health_monitor import health_monitor
from backend.monitoring.alert_manager import alert_manager
from backend.monitoring.performance_analytics import PerformanceAnalytics
from backend.api.portfolio import _get_live_holdings

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

    # ── Portfolio value & Mark-to-Market PnL ─────────────────────────────
    total_value: float = 0.0
    cash_balance: float = 0.0
    positions_value: float = 0.0
    unrealized_pnl: float = 0.0
    holdings: list[dict[str, Any]] = []
    try:
        if engine.mode == "paper":
            paper = engine.paper_trader
            cash_balance = float(getattr(paper, "balance", 0))
            if hasattr(paper, "positions"):
                for pos in paper.positions.values():
                    pair = pos.get("pair")
                    entry_p = float(pos.get("entry_price", 0))
                    qty = float(pos.get("quantity", 0))
                    cur_p = entry_p
                    if hasattr(engine, "exchange_manager"):
                        try:
                            ticker = engine.exchange_manager.get_ticker(pair)
                            cur_p = float(ticker.get("last_price", entry_p)) if isinstance(ticker, dict) else float(ticker)
                        except Exception:
                            cur_p = entry_p
                    side = str(pos.get("side", "BUY")).upper()
                    pos_val = cur_p * qty
                    positions_value += pos_val
                    mult = 1.0 if side == "BUY" else -1.0
                    unrealized_pnl += (cur_p - entry_p) * qty * mult
                    curr = pair.replace("/INR", "").replace("INR", "")
                    holdings.append({
                        "currency": curr,
                        "available": qty,
                        "locked": 0.0,
                        "total": qty,
                        "price_inr": round(cur_p, 4),
                        "value_inr": round(pos_val, 2),
                    })
            total_value = cash_balance + positions_value
        else:
            cash_balance, crypto_value, holdings = _get_live_holdings(getattr(engine, "exchange_manager", None))
            positions_value = crypto_value
            total_value = cash_balance + positions_value
    except Exception:
        pass

    # ── Active trades ────────────────────────────────────────────────────
    open_trades = db.query(Trade).filter(Trade.status == "OPEN").count()

    # ── Win rate & PnL ───────────────────────────────────────────────────
    win_rate = _calc_win_rate(db)

    # Today's realized and total PnL
    from datetime import datetime, timezone
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    today_closed = (
        db.query(Trade)
        .filter(Trade.status == "CLOSED", Trade.closed_at >= today_start)
        .all()
    )
    today_realized_pnl = sum(float(t.pnl or 0.0) for t in today_closed)
    today_pnl = round(today_realized_pnl + unrealized_pnl, 2)
    today_base = max(total_value - today_pnl, 1.0)
    today_pnl_pct = round((today_pnl / today_base) * 100.0, 2)

    all_closed = db.query(Trade).filter(Trade.status == "CLOSED").all()
    total_realized_pnl = sum(float(t.pnl or 0.0) for t in all_closed)
    total_pnl = round(total_realized_pnl + unrealized_pnl, 2)

    # ── Uptime ───────────────────────────────────────────────────────────
    uptime_secs = time.time() - start_time

    from backend.utils.tunnel_manager import tunnel_manager
    tunnel_info = tunnel_manager.get_info()

    # ── Health, Analytics & Alerts Summaries (Agent 5) ───────────────────
    health_stat = health_monitor.get_health_status()

    closed_trades = all_closed
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
            "positions_value_inr": round(positions_value, 2),
            "active_trades": open_trades,
            "win_rate_pct": win_rate,
            "today_pnl": today_pnl,
            "today_pnl_pct": today_pnl_pct,
            "total_pnl": total_pnl,
            "unrealized_pnl": round(unrealized_pnl, 2),
            "holdings": holdings,
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
        "prime_directive": {
            "mandate": getattr(
                settings,
                "PRIME_DIRECTIVE_MANDATE",
                "Autonomous A-to-Z Agency: Capital preservation is existential. If capital is depleted, the bot is dead. Operate end-to-end to run successfully without losing capital.",
            ),
            "min_survival_capital_inr": getattr(settings, "MIN_SURVIVAL_CAPITAL_INR", 500.0),
            "capital_healthy": total_value >= getattr(settings, "MIN_SURVIVAL_CAPITAL_INR", 500.0),
            "autonomous_mode": "FULL_A_TO_Z",
            "zero_ruin_enforced": True,
        },
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

