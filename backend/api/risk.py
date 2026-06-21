"""
AutoTrader Pro — Risk Settings Router
======================================
GET /api/risk  →  current risk settings
PUT /api/risk  →  update risk settings
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from backend.schemas import RiskSettings

router = APIRouter(prefix="/api/risk", tags=["risk"])


@router.get("", summary="Get current risk settings")
async def get_risk_settings(request: Request) -> dict[str, Any]:
    """Returns the current risk-manager configuration."""
    engine = request.app.state.engine
    risk_mgr = engine.risk_manager

    try:
        settings = risk_mgr.get_settings()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load risk settings: {exc}") from exc

    # Accept either a dict or a Pydantic / dataclass object
    if isinstance(settings, dict):
        return {"risk_settings": settings}

    if hasattr(settings, "dict"):
        return {"risk_settings": settings.dict()}

    if hasattr(settings, "model_dump"):
        return {"risk_settings": settings.model_dump()}

    return {"risk_settings": settings.__dict__}


@router.put("", summary="Update risk settings")
async def update_risk_settings(
    body: RiskSettings,
    request: Request,
) -> dict[str, Any]:
    """
    Replaces risk-manager settings with the supplied values.
    The body must conform to the ``RiskSettings`` schema.
    """
    engine = request.app.state.engine
    risk_mgr = engine.risk_manager

    try:
        risk_mgr.update_settings(body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to update risk settings: {exc}") from exc

    # Return the freshly-applied settings
    updated = risk_mgr.get_settings()

    if isinstance(updated, dict):
        payload = updated
    elif hasattr(updated, "model_dump"):
        payload = updated.model_dump()
    elif hasattr(updated, "dict"):
        payload = updated.dict()
    else:
        payload = updated.__dict__

    return {
        "message": "Risk settings updated.",
        "risk_settings": payload,
    }
