"""
AutoTrader Pro — Risk & Portfolio Protection Router
===================================================
GET  /api/risk                      →  current risk settings
GET  /api/risk/settings             →  current risk settings (alias)
PUT  /api/risk                      →  update risk settings
PUT  /api/risk/settings             →  update risk settings (alias)
GET  /api/risk/portfolio-state      →  HWM, drawdowns, streaks, cooldown status
GET  /api/risk/correlation-matrix   →  cross-asset correlation matrix
GET  /api/risk/limits               →  risk limits status & utilization percentages
POST /api/risk/emergency-shutdown   →  trigger emergency circuit-breaker
POST /api/risk/resume-trading       →  resume trading after shutdown/pause
"""

from __future__ import annotations

from typing import Any, Optional
from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.schemas import RiskSettings
from backend.models import Trade
from backend.utils.auth import require_api_key

router = APIRouter(prefix="/api/risk", tags=["risk"])


class EmergencyShutdownRequest(BaseModel):
    reason: Optional[str] = "Manual operator emergency shutdown"


class ResumeTradingRequest(BaseModel):
    reason: Optional[str] = "Manual operator clearance"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Settings Endpoints
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("", summary="Get current risk settings")
@router.get("/settings", summary="Get current risk settings (alias)")
async def get_risk_settings(request: Request) -> dict[str, Any]:
    """Returns the current risk-manager configuration."""
    engine = getattr(request.app.state, "engine", None)
    if engine and hasattr(engine, "risk_manager"):
        risk_mgr = engine.risk_manager
    else:
        from backend.risk.risk_manager import risk_manager as risk_mgr

    try:
        settings_data = risk_mgr.get_settings()
        return settings_data
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load risk settings: {exc}") from exc


@router.put("", summary="Update risk settings", dependencies=[Depends(require_api_key)])
@router.put("/settings", summary="Update risk settings (alias)", dependencies=[Depends(require_api_key)])
async def update_risk_settings(
    body: RiskSettings,
    request: Request,
) -> dict[str, Any]:
    """
    Replaces risk-manager settings with the supplied values.
    """
    engine = getattr(request.app.state, "engine", None)
    if engine and hasattr(engine, "risk_manager"):
        risk_mgr = engine.risk_manager
    else:
        from backend.risk.risk_manager import risk_manager as risk_mgr

    try:
        body_dict = body.model_dump() if hasattr(body, "model_dump") else body.dict()
        risk_mgr.update_settings(body_dict)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to update risk settings: {exc}") from exc

    return {
        "message": "Risk settings updated successfully.",
        "risk_settings": risk_mgr.get_settings(),
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Portfolio State & Risk Analytics
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/portfolio-state", summary="Current portfolio risk state")
async def get_portfolio_state(
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """
    Returns high-water mark, current drawdown from peak, win/loss streaks,
    and loss-streak cooldown status.
    """
    engine = getattr(request.app.state, "engine", None)
    portfolio_value = 10000.0

    if engine:
        if hasattr(engine, "exchange_manager") and hasattr(engine, "paper_trader"):
            prices = engine.exchange_manager.get_current_prices()
            portfolio_value = engine.paper_trader.get_portfolio_value(prices)
        risk_mgr = engine.risk_manager
    else:
        from backend.risk.risk_manager import risk_manager as risk_mgr

    # Update monitor with current equity
    risk_mgr.portfolio_monitor.update_portfolio_value(portfolio_value, engine=engine)
    state = risk_mgr.portfolio_monitor.get_state(portfolio_value=portfolio_value, db_session=db)
    return state


@router.get("/correlation-matrix", summary="Cross-asset price correlation matrix")
async def get_correlation_matrix(request: Request) -> dict[str, Any]:
    """
    Returns rolling Pearson correlation matrix for all monitored cryptocurrency pairs.
    """
    engine = getattr(request.app.state, "engine", None)
    if engine and hasattr(engine, "risk_manager"):
        risk_mgr = engine.risk_manager
    else:
        from backend.risk.risk_manager import risk_manager as risk_mgr

    matrix = risk_mgr.correlation_manager.get_matrix_dict()
    return {
        "matrix": matrix,
        "correlation_threshold": risk_mgr.correlation_threshold,
        "max_correlated_positions": risk_mgr.max_correlated_positions,
    }


@router.get("/limits", summary="Risk limits and utilization tracking")
async def get_limits(
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """
    Provides all active risk limits alongside current metric values and percentage utilized.
    """
    engine = getattr(request.app.state, "engine", None)
    portfolio_value = 10000.0
    open_positions = []

    if engine:
        if hasattr(engine, "exchange_manager") and hasattr(engine, "paper_trader"):
            prices = engine.exchange_manager.get_current_prices()
            portfolio_value = engine.paper_trader.get_portfolio_value(prices)
        if hasattr(engine, "position_tracker"):
            open_positions = [p.to_dict() for p in engine.position_tracker.get_all_positions()]
        risk_mgr = engine.risk_manager
    else:
        from backend.risk.risk_manager import risk_manager as risk_mgr

    if not open_positions:
        # Fallback to database OPEN trades
        trades = db.query(Trade).filter(Trade.status == "OPEN").all()
        open_positions = [
            {
                "pair": t.pair,
                "side": t.side,
                "quantity": t.quantity,
                "entry_price": t.entry_price,
            }
            for t in trades
        ]

    limits_status = risk_mgr.get_limits_status(
        portfolio_value=portfolio_value,
        open_positions=open_positions,
        db_session=db,
    )
    return limits_status


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Circuit Breaker & Emergency Actions
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.post("/emergency-shutdown", summary="Execute emergency shutdown", dependencies=[Depends(require_api_key)])
async def trigger_emergency_shutdown(
    request: Request,
    body: Optional[EmergencyShutdownRequest] = None,
) -> dict[str, Any]:
    """
    Nuclear option: Halts trading, cancels active orders, and liquidates open positions.
    """
    engine = getattr(request.app.state, "engine", None)
    reason = body.reason if body and body.reason else "Manual emergency shutdown requested via API"

    if engine and hasattr(engine, "risk_manager"):
        res = engine.risk_manager.emergency_shutdown.execute(reason=reason, engine=engine)
    else:
        from backend.risk.emergency import emergency_shutdown
        res = emergency_shutdown.execute(reason=reason, engine=engine)

    return res


@router.post("/resume-trading", summary="Resume trading operations", dependencies=[Depends(require_api_key)])
async def resume_trading(
    request: Request,
    body: Optional[ResumeTradingRequest] = None,
) -> dict[str, Any]:
    """
    Re-enables trading after emergency shutdown or operator pause.
    """
    engine = getattr(request.app.state, "engine", None)
    reason = body.reason if body and body.reason else "Manual operator clearance"

    if engine and hasattr(engine, "risk_manager"):
        res = engine.risk_manager.emergency_shutdown.resume_trading(reason=reason)
    else:
        from backend.risk.emergency import emergency_shutdown
        res = emergency_shutdown.resume_trading(reason=reason)

    return res
