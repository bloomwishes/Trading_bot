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

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


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

    # ── Cash balance ─────────────────────────────────────────────────────
    cash_balance: float = 0.0
    try:
        if engine.mode == "paper":
            paper = engine.paper_trader
            cash_balance = float(getattr(paper, "balance", 0))
        else:
            exchange = engine.exchange_manager
            balance = exchange.fetch_balance() if hasattr(exchange, "fetch_balance") else {}
            cash_balance = float(balance.get("INR", {}).get("free", 0)) if isinstance(balance, dict) else 0.0
    except Exception:
        pass

    # ── Open positions ───────────────────────────────────────────────────
    open_trades = db.query(Trade).filter(Trade.status == "OPEN").all()

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

    total_value = cash_balance + positions_value

    return {
        "total_value_inr": round(total_value, 2),
        "cash_balance_inr": round(cash_balance, 2),
        "positions_value_inr": round(positions_value, 2),
        "active_positions": len(positions),
        "positions": positions,
    }
