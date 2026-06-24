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
        return settings

    if hasattr(settings, "dict"):
        return settings.dict()

    if hasattr(settings, "model_dump"):
        return settings.model_dump()

    return settings.__dict__


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
        body_dict = body.model_dump() if hasattr(body, "model_dump") else body.dict()
        risk_mgr.update_settings(body_dict)
        
        # Persist to .env file so it survives restarts
        try:
            from backend.config import PROJECT_ROOT
            env_path = PROJECT_ROOT / ".env"
            if env_path.exists():
                with open(env_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                
                key_map = {
                    "max_position_pct": "MAX_POSITION_PCT",
                    "max_open_trades": "MAX_OPEN_TRADES",
                    "daily_loss_limit_pct": "DAILY_LOSS_LIMIT_PCT",
                    "default_stop_loss_pct": "DEFAULT_STOP_LOSS_PCT",
                    "default_take_profit_pct": "DEFAULT_TAKE_PROFIT_PCT",
                    "trailing_stop_activate_pct": "TRAILING_STOP_ACTIVATE_PCT",
                    "trailing_stop_trail_pct": "TRAILING_STOP_TRAIL_PCT",
                }
                
                updated_keys = {key_map[k]: v for k, v in body_dict.items() if k in key_map}
                
                new_lines = []
                for line in lines:
                    line_stripped = line.strip()
                    if "=" in line_stripped and not line_stripped.startswith("#"):
                        k, _ = line_stripped.split("=", 1)
                        k = k.strip()
                        if k in updated_keys:
                            line = f"{k}={updated_keys[k]}\n"
                    new_lines.append(line)
                    
                with open(env_path, "w", encoding="utf-8") as f:
                    f.writelines(new_lines)
        except Exception as env_exc:
            from backend.utils.logger import bot_logger
            bot_logger.error(f"Failed to persist risk settings to .env: {env_exc}")
            
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
