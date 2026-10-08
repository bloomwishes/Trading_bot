"""
AutoTrader Pro - System Diagnostics API
=======================================
Runs real-time health checks on all critical dependencies.
"""

from __future__ import annotations

import time
import requests
from typing import Any, Dict

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from sqlalchemy import text

from backend.database import get_db
from backend.config import settings

router = APIRouter(prefix="/api/diagnostics", tags=["diagnostics"])

@router.get("", summary="Run real-time system diagnostics")
def run_diagnostics(request: Request, db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    Runs health checks across:
    - Database
    - Local AI (Ollama)
    - Market Data (CoinDCX)
    - Risk Limits
    - Strategy Configuration
    - Bot Engine Status
    """
    engine = request.app.state.engine
    scheduler = request.app.state.scheduler
    exchange = engine.exchange_manager

    results = {}

    # 1. Database Check
    try:
        db.execute(text("SELECT 1"))
        results["database"] = {"status": "ok", "message": "Database connected and responsive."}
    except Exception as e:
        results["database"] = {"status": "error", "message": f"Database error: {str(e)}"}

    # 2. Local AI Check
    try:
        res = requests.get(f"{settings.OLLAMA_HOST}/api/tags", timeout=3)
        res.raise_for_status()
        models = res.json().get("models", [])
        if any(m.get("name", "").startswith(settings.OLLAMA_MODEL) for m in models):
            results["local_ai"] = {"status": "ok", "message": f"Ollama is running with model '{settings.OLLAMA_MODEL}' available."}
        else:
            results["local_ai"] = {"status": "warning", "message": f"Ollama is running, but model '{settings.OLLAMA_MODEL}' was not found. Using fallback."}
    except requests.RequestException:
        results["local_ai"] = {"status": "error", "message": f"Could not connect to local AI at {settings.OLLAMA_HOST}. Ensure Ollama is running."}

    # 3. Market Data Check (Exchange)
    try:
        # Just test fetch 1 candle for a major pair to prove the API is working
        candles = exchange.get_candles("BTC/INR", interval="15m", limit=1)
        if not candles.empty:
            results["market_data"] = {"status": "ok", "message": "Successfully streaming live data from CoinDCX."}
        else:
            results["market_data"] = {"status": "error", "message": "Connected to CoinDCX, but no candle data returned."}
    except Exception as e:
        results["market_data"] = {"status": "error", "message": f"Market Data Error: {str(e)}"}

    # 4. Watchlist Configuration
    if len(settings.WATCHED_PAIRS) > 0:
        results["watchlist"] = {"status": "ok", "message": f"Tracking {len(settings.WATCHED_PAIRS)} pairs: {', '.join(settings.WATCHED_PAIRS)}"}
    else:
        results["watchlist"] = {"status": "error", "message": "Watchlist is empty. Bot has no coins to trade."}

    # 5. Strategies Check
    enabled_strats = [s.name for s in engine.strategies if getattr(s, "enabled", True)]
    if len(enabled_strats) > 0:
        results["strategies"] = {"status": "ok", "message": f"Active strategies: {', '.join(enabled_strats)}"}
    else:
        results["strategies"] = {"status": "warning", "message": "No trading strategies are currently enabled. Bot will not take trades."}

    # 6. Risk Limits (Daily Loss Check)
    try:
        is_breached = engine.risk_manager.check_daily_loss_limit(db)
        if is_breached:
            results["risk"] = {"status": "error", "message": "Daily Loss Limit breached! Trading is halted for today."}
        else:
            results["risk"] = {"status": "ok", "message": "Risk parameters nominal. Daily limits are intact."}
    except Exception as e:
         results["risk"] = {"status": "error", "message": f"Failed to calculate risk limits: {str(e)}"}

    # 7. Bot Core Engine
    if engine.running and scheduler.is_running:
        results["engine"] = {"status": "ok", "message": "AutoTrader core is actively scanning and managing trades."}
    elif not engine.running:
        results["engine"] = {"status": "warning", "message": "Bot is currently STOPPED. Turn it on from the dashboard."}
    else:
        results["engine"] = {"status": "warning", "message": "Engine is running but scheduler is stalled."}

    # Determine overall health
    is_ready = all(v["status"] == "ok" for k, v in results.items() if k not in ["strategies", "engine"])
    if not is_ready:
        overall = "CRITICAL: System cannot trade. Fix the errors below."
    elif results["strategies"]["status"] != "ok" or results["engine"]["status"] != "ok":
        overall = "STANDBY: System is healthy, but bot is stopped or lacks strategies."
    else:
        overall = "READY: All systems operational. Bot is actively trading."

    return {
        "timestamp": time.time(),
        "overall_status": overall,
        "is_ready": is_ready,
        "checks": results
    }
