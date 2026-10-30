"""
AutoTrader Pro — Portfolio Router
==================================
GET /api/portfolio/snapshots  →  historical portfolio snapshots for charting
GET /api/portfolio/current    →  current portfolio value breakdown
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import desc
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import Trade, PortfolioSnapshot
from backend.schemas import PortfolioSnapshotResponse
from backend.monitoring.performance_analytics import PerformanceAnalytics
from backend.utils.auth import require_api_key
from backend.config import settings
from backend.utils.logger import bot_logger

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


def _get_live_holdings(exchange_manager: Any) -> tuple[float, float, list[dict[str, Any]]]:
    """
    Query real-time exchange balances from CoinDCX and convert each asset to INR.
    Returns: (cash_balance_inr, total_crypto_value_inr, holdings_list)
    """
    if not exchange_manager:
        return 0.0, 0.0, []

    cash_inr: float = 0.0
    crypto_val: float = 0.0
    holdings: list[dict[str, Any]] = []

    try:
        balances = exchange_manager.get_balances() if hasattr(exchange_manager, "get_balances") else {}
        for curr, data in balances.items():
            avail = float(data.get("available", 0) or 0)
            locked = float(data.get("locked", 0) or 0)
            total_qty = avail + locked
            if total_qty <= 0:
                continue

            if curr == "INR":
                cash_inr = round(avail, 2)
                price_inr = 1.0
                val_inr = round(total_qty, 2)
            else:
                price_inr = 0.0
                try:
                    ticker = exchange_manager.get_ticker(f"{curr}/INR")
                    price_inr = float(ticker.get("last_price", 0)) if isinstance(ticker, dict) else float(ticker or 0)
                except Exception:
                    price_inr = 0.0
                val_inr = round(total_qty * price_inr, 2)
                crypto_val += val_inr

            holdings.append({
                "currency": curr,
                "available": round(avail, 6),
                "locked": round(locked, 6),
                "total": round(total_qty, 6),
                "price_inr": round(price_inr, 4),
                "value_inr": val_inr,
            })

        holdings.sort(key=lambda x: x["value_inr"], reverse=True)
    except Exception as exc:
        bot_logger.warning(f"Failed to fetch live exchange holdings: {exc}")

    return cash_inr, round(crypto_val, 2), holdings


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GET /api/portfolio/snapshots
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/snapshots", summary="Portfolio history", response_model=list[PortfolioSnapshotResponse])
async def get_portfolio_snapshots(
    date_from: Optional[datetime] = Query(None, description="Start date (ISO-8601)"),
    date_to: Optional[datetime] = Query(None, description="End date (ISO-8601)"),
    limit: int = Query(500, ge=1, le=5000, description="Max records to return"),
    db: Session = Depends(get_db),
) -> list[PortfolioSnapshot]:
    """
    Returns historical portfolio-value snapshots, ideal for rendering
    equity curves and balance charts.  Sorted oldest → newest.
    """
    query = db.query(PortfolioSnapshot)

    if date_from is not None:
        query = query.filter(PortfolioSnapshot.created_at >= date_from)
    if date_to is not None:
        query = query.filter(PortfolioSnapshot.created_at <= date_to)

    # Latest *limit* records, but return in chronological order
    snapshots = query.order_by(desc(PortfolioSnapshot.created_at)).limit(limit).all()
    snapshots.reverse()

    return snapshots


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GET /api/portfolio/current
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/current", summary="Current portfolio breakdown")
async def get_current_portfolio(
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """
    Returns the live portfolio breakdown:
    - total value (₹)
    - cash balance (₹)
    - each open position with current market price and unrealised PnL
    """
    engine = request.app.state.engine

    # ── Cash balance & holdings ──────────────────────────────────────────
    cash_balance: float = 0.0
    holdings: list[dict[str, Any]] = []
    live_crypto_val: float = 0.0
    try:
        if engine.mode == "paper":
            paper = engine.paper_trader
            cash_balance = float(getattr(paper, "balance", 0))
        else:
            cash_balance, live_crypto_val, holdings = _get_live_holdings(getattr(engine, "exchange_manager", None))
    except Exception as exc:
        bot_logger.warning(f"Error reading portfolio balances: {exc}")

    # ── Open positions (filtered by current active mode) ────────────────
    is_paper = (engine.mode == "paper")
    open_trades = db.query(Trade).filter(Trade.status == "OPEN", Trade.paper_mode == is_paper).all()

    positions: list[dict[str, Any]] = []
    positions_value: float = 0.0

    for trade in open_trades:
        current_price: float = trade.entry_price  # fallback
        try:
            ticker = engine.exchange_manager.get_ticker(trade.pair)
            current_price = float(ticker.get("last_price", trade.entry_price)) if isinstance(ticker, dict) else float(ticker)
        except Exception:
            pass

        position_value = current_price * trade.quantity
        if trade.side == "BUY":
            unrealised_pnl = (current_price - trade.entry_price) * trade.quantity
        else:
            unrealised_pnl = (trade.entry_price - current_price) * trade.quantity

        unrealised_pnl_pct = (
            ((current_price - trade.entry_price) / trade.entry_price * 100)
            if trade.entry_price
            else 0.0
        )
        if trade.side == "SELL":
            unrealised_pnl_pct = -unrealised_pnl_pct

        positions.append({
            "trade_id": trade.id,
            "pair": trade.pair,
            "side": trade.side,
            "entry_price": round(trade.entry_price, 2),
            "current_price": round(current_price, 2),
            "quantity": trade.quantity,
            "position_value_inr": round(position_value, 2),
            "unrealised_pnl_inr": round(unrealised_pnl, 2),
            "unrealised_pnl_pct": round(unrealised_pnl_pct, 2),
            "strategy": trade.strategy,
            "paper_mode": trade.paper_mode,
            "opened_at": trade.created_at.isoformat() if trade.created_at else None,
        })

        positions_value += position_value

    if engine.mode == "live":
        total_value = cash_balance + live_crypto_val + positions_value
        reported_positions_value = live_crypto_val + positions_value
    else:
        total_value = cash_balance + positions_value
        reported_positions_value = positions_value
        # Simulated holdings in paper trading mode
        holdings = [
            {
                "currency": "INR",
                "available": round(cash_balance, 2),
                "locked": 0.0,
                "total": round(cash_balance, 2),
                "price_inr": 1.0,
                "value_inr": round(cash_balance, 2),
            }
        ]
        for pos in positions:
            base_curr = pos["pair"].split("/")[0] if "/" in pos["pair"] else pos["pair"].replace("INR", "")
            holdings.append({
                "currency": base_curr,
                "available": pos["quantity"],
                "locked": 0.0,
                "total": pos["quantity"],
                "price_inr": pos["current_price"],
                "value_inr": pos["position_value_inr"],
            })

    return {
        "mode": engine.mode,
        "total_value_inr": round(total_value, 2),
        "cash_balance_inr": round(cash_balance, 2),
        "positions_value_inr": round(reported_positions_value, 2),
        "active_positions": len(positions),
        "positions": positions,
        "holdings": holdings,
    }


@router.get("/holdings", summary="Live exchange wallet holdings")
async def get_holdings(
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """
    Returns real-time exchange wallet balances and INR value breakdown.
    """
    engine = request.app.state.engine
    if engine.mode == "paper":
        cash = float(getattr(engine.paper_trader, "balance", 0)) if hasattr(engine, "paper_trader") else 0.0
        holdings = [
            {
                "currency": "INR",
                "available": round(cash, 2),
                "locked": 0.0,
                "total": round(cash, 2),
                "price_inr": 1.0,
                "value_inr": round(cash, 2),
            }
        ]
        crypto_val = 0.0
        try:
            open_trades = db.query(Trade).filter(Trade.status == "OPEN").all()
            for trade in open_trades:
                current_price = trade.entry_price
                try:
                    ticker = engine.exchange_manager.get_ticker(trade.pair)
                    current_price = float(ticker.get("last_price", trade.entry_price)) if isinstance(ticker, dict) else float(ticker)
                except Exception:
                    pass
                val = round(current_price * trade.quantity, 2)
                crypto_val += val
                base_curr = trade.pair.split("/")[0] if "/" in trade.pair else trade.pair.replace("INR", "")
                holdings.append({
                    "currency": base_curr,
                    "available": round(trade.quantity, 6),
                    "locked": 0.0,
                    "total": round(trade.quantity, 6),
                    "price_inr": round(current_price, 4),
                    "value_inr": val,
                })
        except Exception:
            pass

        return {
            "mode": "paper",
            "total_value_inr": round(cash + crypto_val, 2),
            "cash_balance_inr": round(cash, 2),
            "crypto_value_inr": round(crypto_val, 2),
            "holdings": holdings,
        }

    cash, crypto, holdings = _get_live_holdings(getattr(engine, "exchange_manager", None))
    return {
        "mode": "live",
        "total_value_inr": round(cash + crypto, 2),
        "cash_balance_inr": round(cash, 2),
        "crypto_value_inr": round(crypto, 2),
        "holdings": holdings,
    }


@router.post("/adopt-holdings", summary="Adopt spot wallet holdings as active managed trades")
async def adopt_holdings(
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """
    Manually trigger auto-adoption of CoinDCX spot crypto holdings into
    managed open trades with protective stop-losses and trailing take-profits.
    """
    engine = request.app.state.engine
    if engine.mode != "live":
        raise HTTPException(status_code=400, detail="Auto-adoption is only available in Live trading mode.")

    adopted = engine.adopt_live_holdings(db)
    return {
        "message": f"Successfully adopted {len(adopted)} spot holding(s) as managed trades.",
        "adopted_positions": adopted,
    }


@router.post("/rebalance-to-cash", summary="Convert spot crypto holdings into liquid INR cash")
async def rebalance_to_cash(
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """
    Sell all spot crypto holdings at market price on CoinDCX to convert
    total account balance into 100% liquid INR cash for active multi-pair trading.
    """
    engine = request.app.state.engine
    if engine.mode != "live":
        raise HTTPException(status_code=400, detail="Rebalancing to cash is only available in Live trading mode.")

    sold = engine.rebalance_holdings_to_cash(db)
    cash, crypto, holdings = _get_live_holdings(getattr(engine, "exchange_manager", None))
    return {
        "message": f"Successfully rebalanced {len(sold)} spot asset(s) to INR cash.",
        "sold_assets": sold,
        "new_cash_balance_inr": cash,
        "new_total_equity_inr": round(cash + crypto, 2),
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GET /api/portfolio/analytics
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/analytics", summary="Comprehensive performance and risk analytics")
async def get_portfolio_analytics(
    request: Request,
    period: str = Query("all", description="Period: today | week | month | all"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """
    Returns complete quantitative metrics:
    - Core metrics (win rate, total PnL, profit factor, expectancy)
    - Risk-adjusted ratios (Sharpe, Sortino, Calmar)
    - Drawdown analytics (max drawdown %, duration, current drawdown)
    - Win/loss streaks
    - Multi-dimensional breakdowns (strategy, pair, hour, weekday)
    - Execution quality (slippage, fill time, hold time)
    """
    closed_trades = db.query(Trade).filter(Trade.status == "CLOSED").all()
    snapshots = db.query(PortfolioSnapshot).order_by(PortfolioSnapshot.created_at.asc()).all()

    # Determine initial capital
    engine = getattr(request.app.state, "engine", None)
    initial_capital = 100000.0
    if engine and hasattr(engine, "paper_trader"):
        initial_capital = float(getattr(engine.paper_trader, "initial_balance", 100000.0))

    analytics = PerformanceAnalytics.calculate_full_report(
        trades=closed_trades,
        portfolio_snapshots=snapshots,
        period=period,
        initial_capital=initial_capital,
    )
    return analytics


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GET /api/portfolio/equity-curve
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/equity-curve", summary="Equity curve data points and drawdowns")
async def get_equity_curve(
    request: Request,
    limit: int = Query(500, ge=10, le=5000, description="Max points to return"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """
    Returns time-series equity curve points with mark-to-market portfolio value
    and peak-to-trough drawdowns for charting.
    """
    snapshots = (
        db.query(PortfolioSnapshot)
        .order_by(desc(PortfolioSnapshot.created_at))
        .limit(limit)
        .all()
    )
    snapshots.reverse()

    engine = getattr(request.app.state, "engine", None)
    initial_capital = float(getattr(settings, "PAPER_BALANCE", 10000.0))
    if engine and hasattr(engine, "paper_trader"):
        initial_capital = float(getattr(engine.paper_trader, "initial_balance", initial_capital))

    curve_points = []
    peak = initial_capital
    max_dd = 0.0

    if snapshots:
        peak = snapshots[0].total_value
        for s in snapshots:
            val = float(s.total_value)
            if val > peak:
                peak = val
            dd_pct = ((peak - val) / peak) * 100.0 if peak > 0 else 0.0
            max_dd = max(max_dd, dd_pct)
            curve_points.append({
                "timestamp": s.created_at.isoformat() if s.created_at else None,
                "equity": round(val, 2),
                "cash": round(float(s.cash), 2),
                "drawdown_pct": round(dd_pct, 2),
            })
    else:
        # Construct synthetic curve from closed trades if no snapshots yet
        closed_trades = db.query(Trade).filter(Trade.status == "CLOSED").order_by(Trade.closed_at.asc()).all()
        current_eq = initial_capital
        peak = initial_capital
        for t in closed_trades:
            current_eq += float(t.pnl or 0.0)
            if current_eq > peak:
                peak = current_eq
            dd_pct = ((peak - current_eq) / peak) * 100.0 if peak > 0 else 0.0
            max_dd = max(max_dd, dd_pct)
            dt = t.closed_at or t.created_at
            curve_points.append({
                "timestamp": dt.isoformat() if dt else None,
                "equity": round(current_eq, 2),
                "cash": round(current_eq, 2),
                "drawdown_pct": round(dd_pct, 2),
            })

    current_val = curve_points[-1]["equity"] if curve_points else initial_capital
    current_dd = curve_points[-1]["drawdown_pct"] if curve_points else 0.0

    return {
        "initial_capital": initial_capital,
        "current_value": current_val,
        "high_water_mark": round(peak, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "current_drawdown_pct": round(current_dd, 2),
        "total_points": len(curve_points),
        "points": curve_points,
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# POST /api/portfolio/reset-paper
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.post("/reset-paper", summary="Reset paper trading account, train neural network, and restore initial capital", dependencies=[Depends(require_api_key)])
async def reset_paper_account(
    request: Request,
    initial_balance: Optional[float] = None,
) -> dict[str, Any]:
    """
    Paper Trading Reset Workflow:
    1. Validates paper mode (strictly rejected in live mode).
    2. Closes all active open positions at current market prices.
    3. Trains neural networks on complete trade history.
    4. Purges all paper trades & snapshots from SQLite.
    5. Restores portfolio capital to initial settings (₹10,000).
    """
    engine = getattr(request.app.state, "engine", None)
    if not engine:
        raise HTTPException(status_code=500, detail="Trading engine not active")

    if engine.mode != "paper":
        raise HTTPException(
            status_code=400,
            detail="Reset is ONLY allowed in Paper Trading mode. Live trading accounts cannot be reset.",
        )

    try:
        res = engine.reset_paper_account(new_balance=initial_balance)
        return res
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to reset paper account: {exc}") from exc

