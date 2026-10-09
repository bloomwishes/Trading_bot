"""
AutoTrader Pro — Strategies Router
===================================
GET /api/strategies              →  list all strategies & their config
PUT /api/strategies/{name}       →  update a strategy's enabled/params
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.database import get_db

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


@router.get("/shadow/predictions", summary="Get Neural Network shadow mode predictions and telemetry")
async def get_shadow_predictions(request: Request, limit: int = 50) -> dict[str, Any]:
    """
    Returns shadow-mode telemetry from the Neural Network strategy along with
    persisted shadow signals from the database.
    """
    import json
    from backend.database import SessionLocal
    from backend.models import Signal

    engine = request.app.state.engine
    nn_strategy = next(
        (s for s in engine.strategies if s.name == "Neural_Network"), None
    )

    stats = nn_strategy.get_shadow_stats() if nn_strategy else {}

    db = SessionLocal()
    try:
        rows = (
            db.query(Signal)
            .filter(Signal.strategy == "Neural_Network")
            .order_by(Signal.id.desc())
            .limit(max(1, min(limit, 500)))
            .all()
        )
        db_signals = []
        for r in rows:
            try:
                meta = json.loads(r.metadata_json) if r.metadata_json else {}
            except Exception:
                meta = {}
            db_signals.append(
                {
                    "id": r.id,
                    "pair": r.pair,
                    "action": r.signal_type,
                    "strategy": r.strategy,
                    "strength": r.strength,
                    "metadata": meta,
                    "created_at": (
                        r.created_at.isoformat()
                        if hasattr(r.created_at, "isoformat")
                        else str(r.created_at)
                    ),
                }
            )
    finally:
        db.close()

    return {
        "shadow_telemetry": stats,
        "persisted_signals": db_signals,
    }


class NeuralTrainRequest(BaseModel):
    pair: str = Field("BTC/INR", description="Trading pair to fetch candles and calibrate on")


@router.post("/neural_network/train", summary="Calibrate Neural Network on historical candles")
async def train_neural_network(
    request: Request,
    body: Optional[NeuralTrainRequest] = None,
) -> dict[str, Any]:
    """
    Fetches historical candles for the specified pair and calibrates the
    Shadow Mode Neural Network weights.
    """
    engine = request.app.state.engine
    nn_strategy = next(
        (s for s in engine.strategies if s.name == "Neural_Network"), None
    )
    if nn_strategy is None:
        raise HTTPException(status_code=404, detail="Neural_Network strategy not registered")

    pair = body.pair if body else "BTC/INR"
    df = engine.exchange_manager.get_candles(pair=pair, interval="15m", limit=120)
    if df is None or df.empty:
        raise HTTPException(status_code=400, detail=f"No candle data available for {pair}")

    metrics = nn_strategy.train_on_candles(df, pair=pair)
    return {
        "message": f"Neural network calibrated on {pair} (shadow_mode={nn_strategy.params.get('shadow_mode', False)})",
        "metrics": metrics,
    }


@router.post("/neural_network/train_on_history", summary="Train neural network on database closed trade history")
async def train_neural_network_on_history(
    request: Request,
    epochs: int = Query(35, ge=1, le=200, description="Training epochs"),
    learning_rate: float = Query(0.005, ge=0.0001, le=0.1, description="Learning rate"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """
    Train and adapt the neural network using all recorded closed trade outcomes in SQLite.
    Penalizes losing trades (HOLD target + 2.5x penalty) and rewards winning setups.
    """
    engine = request.app.state.engine
    nn_strategy = next(
        (s for s in engine.strategies if s.name == "Neural_Network"), None
    )
    if nn_strategy is None:
        raise HTTPException(status_code=404, detail="Neural_Network strategy not registered")

    result = nn_strategy.train_on_closed_trades(
        db=db,
        exchange_manager=getattr(engine, "exchange_manager", None),
        epochs=epochs,
        lr=learning_rate,
    )
    return {
        "message": f"Neural network trained on {result.get('total_trades', 0)} historical trades ({result.get('wins', 0)} wins, {result.get('losses', 0)} losses)",
        "metrics": result,
    }


@router.get("/neural_network/live_brain", summary="Get real-time layer activations and firing synapses")
async def get_neural_live_brain(request: Request, pair: str = "BTC/INR") -> dict[str, Any]:
    """
    Returns full neural network state:
      - 16 Input feature values
      - Layer 1 (64) and Layer 2 (32) neuron firing activations
      - Top active synaptic weight connections
      - Output class probabilities and expected forward return
      - Capital preservation and closed trade learning telemetry
    """
    engine = request.app.state.engine
    nn_strategy = next(
        (s for s in engine.strategies if s.name == "Neural_Network"), None
    )
    if nn_strategy is None:
        raise HTTPException(status_code=404, detail="Neural_Network strategy not registered")

    # Fetch latest candles to guarantee real-time synaptic firing
    try:
        df = engine.exchange_manager.get_candles(pair=pair, interval="15m", limit=100)
        if df is not None and not df.empty:
            nn_strategy._latest_candles_by_pair[pair] = df
    except Exception:
        pass

    brain_state = nn_strategy.get_live_brain_state(pair=pair)

    # Add capital survival telemetry
    current_prices = engine.exchange_manager.get_current_prices()
    portfolio_val = engine.paper_trader.get_portfolio_value(current_prices)
    cash_bal = engine.paper_trader.balance
    open_count = len(engine.paper_trader.positions)

    return {
        "brain": brain_state,
        "capital_health": {
            "portfolio_value": round(portfolio_val, 2),
            "cash_balance": round(cash_bal, 2),
            "initial_balance": 10000.0,
            "open_positions": open_count,
            "survival_score": round(min(100.0, max(0.0, (portfolio_val / 10000.0) * 100.0)), 1),
            "mode": engine.mode,
            "risk_status": "OPTIMAL" if portfolio_val >= 9500.0 else "DEFENSIVE",
        },
    }


