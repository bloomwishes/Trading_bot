"""
AutoTrader Pro — Bot Control Router
====================================
POST /api/bot/start   →  start scheduler + engine
POST /api/bot/stop    →  stop scheduler + engine
POST /api/bot/mode    →  toggle paper / live mode
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

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

@router.post("/start", summary="Start the trading bot")
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


@router.post("/stop", summary="Stop the trading bot")
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


@router.post("/mode", summary="Switch paper / live mode")
async def change_mode(body: ModeChangeRequest, request: Request) -> dict[str, Any]:
    """
    Toggles the bot between **paper** and **live** trading mode.

    Safety rules:
    - ``confirm`` must be ``true``.
    - Bot must be stopped before switching to **live** mode.
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

    try:
        engine.mode = body.mode
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Mode switch failed: {exc}") from exc

    return {
        "message": f"Mode changed to '{body.mode}'.",
        **_status_payload(engine, scheduler),
    }
