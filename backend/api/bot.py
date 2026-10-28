"""
AutoTrader Pro — Bot Control Router
====================================
POST /api/bot/start   →  start scheduler + engine (requires auth)
POST /api/bot/stop    →  stop scheduler + engine (requires auth)
POST /api/bot/mode    →  toggle paper / live mode (requires auth & live credential check)
"""

from __future__ import annotations

import time
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
    - Requires valid API Key authentication (if API_KEY configured).
    - ``confirm`` must be ``true``.
    - If switching to **live** mode, CoinDCX credentials must be configured and tested.
    """
    engine = request.app.state.engine
    scheduler = request.app.state.scheduler

    if not body.confirm:
        raise HTTPException(status_code=400, detail="Confirmation required. Send confirm=true.")

    # Idempotent: if already in the target mode, return success
    if engine.mode == body.mode:
        return {
            "message": f"Bot is already in '{body.mode}' mode.",
            **_status_payload(engine, scheduler),
        }

    # If switching to LIVE mode, enforce strict pre-flight checks
    if body.mode == "live":
        import dotenv
        from pathlib import Path
        env_path = getattr(settings, "ENV_PATH", Path(__file__).resolve().parent.parent.parent / ".env")
        env_vals = dotenv.dotenv_values(env_path) if Path(env_path).exists() else {}

        key = (env_vals.get("COINDCX_API_KEY") or getattr(settings, "COINDCX_API_KEY", "") or os.getenv("COINDCX_API_KEY", "")).strip()
        secret = (env_vals.get("COINDCX_API_SECRET") or getattr(settings, "COINDCX_API_SECRET", "") or os.getenv("COINDCX_API_SECRET", "")).strip()

        # Update in-memory settings
        settings.COINDCX_API_KEY = key
        settings.COINDCX_API_SECRET = secret

        if not key or not secret or "your_coindcx_api_key" in key or "your_api_key_here" in key:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Cannot switch to LIVE mode: CoinDCX API credentials are missing or "
                    "configured as placeholder values in .env. Please provide your actual "
                    "COINDCX_API_KEY and COINDCX_API_SECRET in the .env file."
                ),
            )

        # Synchronize refreshed credentials to the exchange manager
        if hasattr(engine, "exchange_manager") and hasattr(engine.exchange_manager, "_coindcx"):
            engine.exchange_manager._coindcx.api_key = key
            engine.exchange_manager._coindcx.api_secret = secret

        # Test live connectivity & signature validation with CoinDCX
        try:
            test_body = {"timestamp": int(time.time() * 1000)}
            data = engine.exchange_manager._coindcx._private_post("/exchange/v1/users/balances", test_body)
            bot_logger.info(f"[Security] CoinDCX live mode pre-flight check succeeded. Account authenticated.")
        except Exception as exc:
            err_str = str(exc)
            bot_logger.error(f"[Security] CoinDCX live mode pre-flight check failed: {err_str}")
            if "401" in err_str or "Unauthorized" in err_str or "Invalid credentials" in err_str:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "CoinDCX authentication failed (401 Invalid Credentials). "
                        "Please verify that COINDCX_API_KEY and COINDCX_API_SECRET in your .env are correct, "
                        "and ensure Trade permissions and IP whitelist settings on CoinDCX match this device."
                    ),
                )
            raise HTTPException(
                status_code=400,
                detail=f"Cannot switch to LIVE mode: CoinDCX connection test failed: {exc}",
            )

    try:
        engine.mode = body.mode
        bot_logger.info(f"[Mode] Trading mode switched to {body.mode.upper()} (running={engine.running})")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Mode switch failed: {exc}") from exc

    return {
        "message": f"Mode changed to '{body.mode}'.",
        **_status_payload(engine, scheduler),
    }
