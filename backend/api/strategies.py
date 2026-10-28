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


@router.get("/performance", summary="Get strategy performance metrics")
async def get_strategy_performance(request: Request, db: Session = Depends(get_db)) -> dict[str, Any]:
    """
    Returns historical trade performance metrics (win rate, total trades, avg PnL, profit factor)
    for each registered trading strategy.
    """
    engine = getattr(request.app.state, "engine", None)
    if engine and hasattr(engine, "strategy_performance") and engine.strategy_performance:
        return {"performance": engine.strategy_performance}

    # Fallback to computing directly from closed trades in DB if engine is not running/empty
    from backend.models import Trade
    closed_trades = db.query(Trade).filter(Trade.status == "CLOSED").all()
    by_strategy: dict[str, list] = {}
    for t in closed_trades:
        strat = t.strategy or "Unknown"
        by_strategy.setdefault(strat, []).append(t)

    perf: dict[str, dict[str, Any]] = {}
    for strat, trades in by_strategy.items():
        total = len(trades)
        wins = sum(1 for t in trades if (t.pnl or 0) > 0)
        losses = sum(1 for t in trades if (t.pnl or 0) <= 0)
        win_rate = round(wins / total, 4) if total > 0 else 0.50
        avg_pnl = round(sum(float(t.pnl or 0) for t in trades) / total, 2) if total > 0 else 0.0

        gross_profit = sum(float(t.pnl or 0) for t in trades if (t.pnl or 0) > 0)
        gross_loss = abs(sum(float(t.pnl or 0) for t in trades if (t.pnl or 0) < 0))
        profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else (round(gross_profit, 2) if gross_profit > 0 else 1.0)

        perf[strat] = {
            "total_trades": total,
            "wins": wins,
            "losses": losses,
            "win_rate": win_rate,
            "avg_pnl": avg_pnl,
            "profit_factor": profit_factor,
        }

    return {"performance": perf}


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
    neural_strategies = [s for s in engine.strategies if s.name.startswith("Neural_Network")]
    stats = {}
    for s in neural_strategies:
        stats[s.name] = s.get_shadow_stats() if hasattr(s, "get_shadow_stats") else {}

    db = SessionLocal()
    try:
        rows = (
            db.query(Signal)
            .filter(Signal.strategy.like("Neural_Network%"))
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
    pair = body.pair if body else "BTC/INR"
    nn_strategy = _get_neural_strategy(engine, pair=pair)
    if nn_strategy is None:
        raise HTTPException(status_code=404, detail=f"No Neural Network strategy registered for {pair}")

    df = engine.exchange_manager.get_candles(pair=pair, interval="15m", limit=120)
    if df is None or df.empty:
        raise HTTPException(status_code=400, detail=f"No candle data available for {pair}")

    metrics = nn_strategy.train_on_candles(df, pair=pair)
    return {
        "message": f"Neural network ({nn_strategy.name}) calibrated on {pair}",
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


@router.post("/neural_network/train_experimental", summary="Manually train experimental neural network on 24 months CoinDCX data")
async def train_neural_network_experimental(
    request: Request,
    days: int = Query(730, ge=30, le=1000, description="Number of daily candles (730 = 24 months)"),
    epochs: int = Query(40, ge=1, le=200, description="Training epochs"),
    horizon_bars: int = Query(5, ge=1, le=30, description="Forward return horizon bars"),
    return_threshold_pct: float = Query(2.0, ge=0.1, le=15.0, description="Return threshold % for BUY/SELL labels"),
    learning_rate: float = Query(0.005, ge=0.0001, le=0.1, description="Learning rate"),
) -> dict[str, Any]:
    """
    Manually triggered training on CoinDCX 24 months historical BTC/INR data.
    Generates 16 features, creates explicit HOLD/BUY/SELL labels, and saves
    to nn_weights_experimental.json without touching live model or live thresholds.
    """
    engine = request.app.state.engine
    nn_strategy = next(
        (s for s in engine.strategies if s.name == "Neural_Network"), None
    )
    if nn_strategy is None:
        raise HTTPException(status_code=404, detail="Neural_Network strategy not registered")

    # Fetch 24 months daily candles from CoinDCX
    df = engine.exchange_manager.get_candles(pair="BTC/INR", interval="1d", limit=days)
    if df is None or len(df) < 30:
        raise HTTPException(status_code=400, detail="Failed to fetch sufficient historical candle data from CoinDCX")

    result = nn_strategy.train_experimental_dataset(
        df=df,
        horizon_bars=horizon_bars,
        return_threshold_pct=return_threshold_pct,
        epochs=epochs,
        lr=learning_rate,
    )
    return {
        "message": "Manual experimental training complete on 24 months CoinDCX BTC/INR data. Live weights preserved.",
        "result": result,
    }


@router.post("/neural_network/combine_models", summary="Combine historical macro data and closed-trade experience into unified model")
async def combine_neural_models(
    request: Request,
    days: int = Query(730, ge=30, le=1000, description="Number of daily candles (730 = 24 months)"),
    epochs: int = Query(100, ge=1, le=300, description="Training epochs"),
    horizon_bars: int = Query(5, ge=1, le=30, description="Forward return horizon bars"),
    return_threshold_pct: float = Query(2.0, ge=0.1, le=15.0, description="Return threshold % for BUY/SELL labels"),
    learning_rate: float = Query(0.005, ge=0.0001, le=0.1, description="Learning rate"),
    model: Optional[str] = Query(None, description="Model to train: BTC, ETH, or ALTS"),
    pair: Optional[str] = Query(None, description="Specific pair to train"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """
    Combines macro market structure with all recorded closed-trade
    outcomes in SQLite into a single unified high-performing model and persists it to live weights.
    """
    engine = request.app.state.engine
    nn_strategy = _get_neural_strategy(engine, pair=pair, model_name=model)
    if nn_strategy is None:
        raise HTTPException(status_code=404, detail="No matching Neural Network strategy registered")

    result = nn_strategy.combine_and_train_unified_model(
        db=db,
        exchange_manager=getattr(engine, "exchange_manager", None),
        days=days,
        epochs=epochs,
        lr=learning_rate,
        horizon_bars=horizon_bars,
        return_threshold_pct=return_threshold_pct,
    )
    if result.get("status") == "failed":
        raise HTTPException(status_code=400, detail=result.get("reason", "Failed to combine and train model"))

    return {
        "message": (
            f"Unified model trained on {result.get('total_samples', 0)} total samples "
            f"({result.get('macro_samples', 0)} macro candles, {result.get('trade_samples', 0)} trade experiences). "
            f"Overall Accuracy: {result.get('overall_accuracy', 0)*100:.1f}%, "
            f"Macro Acc: {result.get('macro_accuracy', 0)*100:.1f}%, "
            f"Trade Acc: {result.get('trade_accuracy', 0)*100:.1f}%."
        ),
        "result": result,
    }


def _get_neural_strategy(engine, pair: Optional[str] = None, model_name: Optional[str] = None):
    """
    Finds the appropriate Neural Network strategy instance in the engine.
    1. If model_name is given, matches s.name.
    2. If pair is given, matches by pair_filter (e.g. ETH/INR -> Neural_Network_ETH, SOL/INR -> Neural_Network_ALTS).
    3. Fallback to any strategy starting with Neural_Network.
    """
    neural_strategies = [s for s in engine.strategies if s.name.startswith("Neural_Network")]
    if not neural_strategies:
        return None

    if model_name:
        for s in neural_strategies:
            if s.name.lower() == model_name.lower():
                return s

    if pair:
        pair_upper = pair.upper()
        for s in neural_strategies:
            if getattr(s, "pair_filter", None) and pair_upper in s.pair_filter:
                return s

    # Fallback to BTC model or first neural model
    for s in neural_strategies:
        if "BTC" in s.name:
            return s
    return neural_strategies[0]


@router.get("/neural_network/models", summary="List all active Neural Network models and their status")
async def list_neural_models(request: Request) -> dict[str, Any]:
    engine = request.app.state.engine
    neural_strategies = [s for s in engine.strategies if s.name.startswith("Neural_Network")]
    models_info = []
    for s in neural_strategies:
        models_info.append({
            "name": s.name,
            "enabled": s.enabled,
            "pairs": getattr(s, "pair_filter", []),
            "weights_path": str(getattr(s, "weights_path", "")),
            "train_steps": s.model.train_steps,
            "last_loss": s.model.last_loss,
        })
    return {"models": models_info}


@router.get("/neural_network/live_brain", summary="Get real-time layer activations and firing synapses")
async def get_neural_live_brain(
    request: Request,
    pair: str = "BTC/INR",
    model: Optional[str] = None,
) -> dict[str, Any]:
    """
    Returns full neural network state for the requested pair and corresponding model:
      - 16 Input feature values
      - Layer 1 (64) and Layer 2 (32) neuron firing activations
      - Top active synaptic weight connections
      - Output class probabilities and expected forward return
      - Capital preservation and closed trade learning telemetry
    """
    engine = request.app.state.engine
    nn_strategy = _get_neural_strategy(engine, pair=pair, model_name=model)
    if nn_strategy is None:
        raise HTTPException(status_code=404, detail="No matching Neural_Network strategy registered")

    # Fetch latest candles to guarantee real-time synaptic firing
    try:
        if hasattr(engine.exchange_manager, "get_candles_with_meta"):
            df, meta = engine.exchange_manager.get_candles_with_meta(pair=pair, interval="15m", limit=100)
        else:
            df = engine.exchange_manager.get_candles(pair=pair, interval="15m", limit=100)
            meta = {}
        if df is not None and not df.empty:
            nn_strategy._latest_candles_by_pair[pair] = df
            if hasattr(nn_strategy, "_latest_candle_meta"):
                nn_strategy._latest_candle_meta[pair] = meta
    except Exception:
        pass

    brain_state = nn_strategy.get_live_brain_state(pair=pair)
    brain_state["model_name"] = nn_strategy.name
    brain_state["pair_filter"] = getattr(nn_strategy, "pair_filter", [])

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


@router.get("/neural_network/live_brains", summary="Get simultaneous real-time state for all 3 neural models")
async def get_all_neural_live_brains(request: Request) -> dict[str, Any]:
    """
    Returns real-time simultaneous telemetry, status, probabilities, and signals
    for all 3 Neural Network models operating in tandem.
    """
    engine = request.app.state.engine
    neural_strategies = [s for s in engine.strategies if s.name.startswith("Neural_Network")]
    
    current_prices = engine.exchange_manager.get_current_prices()
    portfolio_val = engine.paper_trader.get_portfolio_value(current_prices)
    cash_bal = engine.paper_trader.balance
    open_count = len(engine.paper_trader.positions)

    brains = {}
    for s in neural_strategies:
        pair_to_query = (s.pair_filter[0] if getattr(s, "pair_filter", None) else "BTC/INR")
        # Ensure fresh candles
        try:
            df = engine.exchange_manager.get_candles(pair=pair_to_query, interval="15m", limit=100)
            if df is not None and not df.empty:
                s._latest_candles_by_pair[pair_to_query] = df
        except Exception:
            pass
        b_state = s.get_live_brain_state(pair=pair_to_query)
        b_state["model_name"] = s.name
        b_state["pair_filter"] = getattr(s, "pair_filter", [])
        brains[s.name] = b_state

    return {
        "models": brains,
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


