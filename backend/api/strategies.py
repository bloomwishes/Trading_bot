"""
AutoTrader Pro — Strategies Router
===================================
GET /api/strategies              →  list all strategies & their config
PUT /api/strategies/{name}       →  update a strategy's enabled/params
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/strategies", tags=["strategies"])


# ── Request body ─────────────────────────────────────────────────────────────

class StrategyUpdateRequest(BaseModel):
    enabled: Optional[bool] = Field(None, description="Enable or disable the strategy")
    params: Optional[dict[str, Any]] = Field(None, description="Strategy-specific parameters")


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("", summary="List all strategies")
async def list_strategies(request: Request) -> dict[str, Any]:
    """
    Returns configuration for every registered strategy.

    Response shape::

        {
          "strategies": {
            "rsi_oversold": {"enabled": true, "params": {"period": 14, …}},
            …
          }
        }
    """
    engine = request.app.state.engine

    try:
        configs = engine.get_strategies_config()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not load strategies: {exc}") from exc

    return {"strategies": configs}


@router.put("/{name}", summary="Update a strategy")
async def update_strategy(
    name: str,
    body: StrategyUpdateRequest,
    request: Request,
) -> dict[str, Any]:
    """
    Updates the **enabled** flag and/or **params** of a single strategy.
    Returns the updated config for that strategy.
    """
    engine = request.app.state.engine

    # Validate strategy exists
    try:
        all_configs = engine.get_strategies_config()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not load strategies: {exc}") from exc

    if name not in all_configs:
        available = ", ".join(sorted(all_configs.keys()))
        raise HTTPException(
            status_code=404,
            detail=f"Strategy '{name}' not found. Available: {available}",
        )

    # Build update payload (only include fields that were actually sent)
    update_payload: dict[str, Any] = {}
    if body.enabled is not None:
        update_payload["enabled"] = body.enabled
    if body.params is not None:
        update_payload["params"] = body.params

    if not update_payload:
        raise HTTPException(status_code=400, detail="No fields to update. Send 'enabled' and/or 'params'.")

    try:
        engine.update_strategy_config(name, update_payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to update strategy: {exc}") from exc

    # Return refreshed config
    updated_configs = engine.get_strategies_config()
    return {
        "message": f"Strategy '{name}' updated.",
        "strategy": {name: updated_configs.get(name)},
    }
