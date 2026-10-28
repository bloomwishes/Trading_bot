"""
AutoTrader Pro — Bot Control Router
====================================
POST /api/bot/start   →  start scheduler + engine (requires auth)
POST /api/bot/stop    →  stop scheduler + engine (requires auth)
POST /api/bot/mode    →  toggle paper / live mode (requires auth & live credential check)
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from backend.config import settings
from backend.utils.auth import require_api_key
from backend.utils.logger import bot_logger

router = APIRouter(prefix="/api/bot", tags=["bot"])


# ── Request bodies ───────────────────────────────────────────────────────────

class ModeChangeRequest(BaseModel):
    mode: str = Field(..., pattern="^(paper|live)$", description="Target mode: 'paper' or 'live'")
    confirm: bool = Field(..., description="Must be true to apply mode change")


# ── Helpers ──────────────────────────────────────────────────────────────────

def _status_payload(engine: Any, scheduler: Any) -> dict[str, Any]:
    return {
        "running": engine.running,
        "scheduler_running": scheduler.is_running,
        "mode": engine.mode,
    }


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/start", summary="Start the trading bot", dependencies=[Depends(require_api_key)])
async def start_bot(request: Request) -> dict[str, Any]:
    """
    Starts the bot scheduler and trading engine.
    Returns 409 if the bot is already running.
    """
    engine = request.app.state.engine
    scheduler = request.app.state.scheduler

    if engine.running:
        raise HTTPException(status_code=409, detail="Bot is already running.")

    try:
        engine.start()
        scheduler.start()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to start bot: {exc}") from exc

    return {
        "message": "Bot started successfully.",
        **_status_payload(engine, scheduler),
    }


@router.post("/stop", summary="Stop the trading bot", dependencies=[Depends(require_api_key)])
async def stop_bot(request: Request) -> dict[str, Any]:
    """
    Gracefully stops the scheduler and trading engine.
    Returns 409 if the bot is not currently running.
    """
    engine = request.app.state.engine
    scheduler = request.app.state.scheduler

    if not engine.running and not scheduler.is_running:
        raise HTTPException(status_code=409, detail="Bot is not running.")

    try:
        if scheduler.is_running:
            scheduler.stop()
        if engine.running:
            engine.stop()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to stop bot: {exc}") from exc

    return {
        "message": "Bot stopped successfully.",
        **_status_payload(engine, scheduler),
    }


@router.post("/mode", summary="Switch paper / live mode", dependencies=[Depends(require_api_key)])
async def change_mode(body: ModeChangeRequest, request: Request) -> dict[str, Any]:
    """
    Toggles the bot between **paper** and **live** trading mode.

    Safety rules:
    - Requires valid API Key authentication.
    - ``confirm`` must be ``true``.
    - Bot must be stopped before switching to **live** mode.
    - If switching to **live** mode, CoinDCX credentials must be configured and tested.
    - If mode is already set, returns 409.
    """
    engine = request.app.state.engine
    scheduler = request.app.state.scheduler

    if not body.confirm:
        raise HTTPException(status_code=400, detail="Confirmation required. Send confirm=true.")

    if engine.mode == body.mode:
        raise HTTPException(
            status_code=409,
            detail=f"Bot is already in '{body.mode}' mode.",
        )

    # Switching to live requires the bot to be stopped first
    if body.mode == "live" and engine.running:
        raise HTTPException(
            status_code=400,
            detail="Stop the bot before switching to live mode.",
        )

    # If switching to LIVE mode, enforce strict pre-flight checks
    if body.mode == "live":
        key = (settings.COINDCX_API_KEY or "").strip()
        secret = (settings.COINDCX_API_SECRET or "").strip()

        if not key or not secret or "your_coindcx_api_key" in key:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Cannot switch to LIVE mode: CoinDCX API credentials are missing or "
                    "configured as placeholder values in .env. Please provide valid "
                    "COINDCX_API_KEY and COINDCX_API_SECRET."
                ),
            )

        # Test live connectivity
        try:
            balances = engine.exchange_manager.get_balances()
            if not isinstance(balances, dict):
                raise ValueError("Unexpected response from exchange when querying balance.")
            bot_logger.info(f"[Security] Live mode pre-flight check succeeded. Balances accessible: {list(balances.keys())}")
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot switch to LIVE mode: CoinDCX connectivity check failed: {exc}",
            )

    try:
        engine.mode = body.mode
        bot_logger.info(f"[Mode] Trading mode switched to {body.mode.upper()}")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Mode switch failed: {exc}") from exc

    return {
        "message": f"Mode changed to '{body.mode}'.",
        **_status_payload(engine, scheduler),
    }
