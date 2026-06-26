"""
AutoTrader Pro — Trades Router
===============================
GET  /api/trades/open          →  open trades
GET  /api/trades/history       →  closed trades (paginated, filtered)
POST /api/trade/manual         →  create a manual trade
POST /api/trade/close/{id}     →  close a specific trade
GET  /api/trades/export        →  CSV export of trade history
"""

from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import desc
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import Trade
from backend.schemas import TradeCreate, TradeResponse

router = APIRouter(tags=["trades"])


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GET /api/trades/open
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/api/trades/open", summary="List open trades", response_model=list[TradeResponse])
async def get_open_trades(
    request: Request,
    paper_mode: Optional[bool] = Query(None, description="Filter by paper_mode flag"),
    db: Session = Depends(get_db),
) -> list[Trade]:
    query = db.query(Trade).filter(Trade.status == "OPEN")
    if paper_mode is not None:
        query = query.filter(Trade.paper_mode == paper_mode)
    trades = query.order_by(desc(Trade.created_at)).all()
    
    engine = request.app.state.engine
    for t in trades:
        current_price = t.entry_price
        try:
            ticker = engine.exchange_manager.get_ticker(t.pair)
            current_price = float(ticker.get("last_price", t.entry_price)) if isinstance(ticker, dict) else float(ticker)
        except Exception:
            pass
        t.current_price = current_price
        
    return trades


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GET /api/trades/history
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/api/trades/history", summary="Closed trade history", response_model=list[TradeResponse])
async def get_trade_history(
    date_from: Optional[datetime] = Query(None, description="Start date (ISO-8601)"),
    date_to: Optional[datetime] = Query(None, description="End date (ISO-8601)"),
    pair: Optional[str] = Query(None, description="Trading pair, e.g. BTC/INR"),
    strategy: Optional[str] = Query(None, description="Strategy name filter"),
    paper_mode: Optional[bool] = Query(None, description="Filter by paper_mode flag"),
    limit: int = Query(500, ge=1, le=5000, description="Page size"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    db: Session = Depends(get_db),
) -> list[Trade]:
    query = db.query(Trade).filter(Trade.status == "CLOSED")

    if date_from is not None:
        query = query.filter(Trade.created_at >= date_from)
    if date_to is not None:
        query = query.filter(Trade.created_at <= date_to)
    if pair is not None:
        query = query.filter(Trade.pair == pair.upper())
    if strategy is not None:
        query = query.filter(Trade.strategy == strategy)
    if paper_mode is not None:
        query = query.filter(Trade.paper_mode == paper_mode)

    return query.order_by(desc(Trade.closed_at), desc(Trade.id)).offset(offset).limit(limit).all()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# POST /api/trade/manual
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.post("/api/trade/manual", summary="Place a manual trade", response_model=TradeResponse, status_code=201)
async def create_manual_trade(
    body: TradeCreate,
    request: Request,
    db: Session = Depends(get_db),
) -> Trade:
    """
    Validates the trade against the risk manager, then executes it
    via the trading engine (paper or live depending on current mode).
    """
    engine = request.app.state.engine
    risk_mgr = engine.risk_manager

    # ── Fetch current price ──────────────────────────────────────────────
    try:
        exchange = engine.exchange_manager
        ticker = exchange.get_ticker(body.pair)
        current_price = float(ticker.get("last_price", 0)) if isinstance(ticker, dict) else float(ticker)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Could not fetch price for {body.pair}: {exc}") from exc

    if current_price <= 0:
        raise HTTPException(status_code=502, detail=f"Invalid price received for {body.pair}.")

    # ── Quantity and Amount INR calculations ──────────────────────────────
    if body.amount_inr is not None:
        amount_inr = body.amount_inr
        quantity = amount_inr / current_price
    elif body.quantity is not None:
        quantity = body.quantity
        amount_inr = quantity * current_price
    else:
        raise HTTPException(status_code=400, detail="Must provide either quantity or amount_inr.")

    # ── Risk validation ──────────────────────────────────────────────────
    # Check max position size pct of portfolio
    current_prices = engine.exchange_manager.get_current_prices()
    portfolio_value = engine.paper_trader.get_portfolio_value(current_prices) if engine.mode == "paper" else 10000.0
    max_pos = portfolio_value * (risk_mgr.max_position_pct / 100.0)
    if amount_inr > max_pos:
        raise HTTPException(
            status_code=400,
            detail=f"Amount ₹{amount_inr:,.2f} exceeds max position size ₹{max_pos:,.2f} ({risk_mgr.max_position_pct}% of portfolio).",
        )

    # Check max open trades
    if risk_mgr.max_open_trades:
        open_count = db.query(Trade).filter(Trade.status == "OPEN").count()
        if open_count >= risk_mgr.max_open_trades:
            raise HTTPException(
                status_code=400,
                detail=f"Max open trades ({risk_mgr.max_open_trades}) reached. Close a trade first.",
            )

    # ── Execute the trade ────────────────────────────────────────────────
    try:
        strategy_name = body.strategy.upper() if body.strategy else "MANUAL"
        if engine.mode == "paper":
            result = engine.paper_trader.execute_trade(
                pair=body.pair.upper(),
                side=body.side.upper(),
                quantity=quantity,
                price=current_price,
                strategy=strategy_name,
                stop_loss=body.stop_loss,
                take_profit=body.take_profit,
                entry_reason="Manual trade placed by user",
            )
            if isinstance(result, dict) and "error" in result:
                raise HTTPException(status_code=400, detail=result["error"])
            trade = db.query(Trade).filter(Trade.id == result["id"]).first()
        else:
            # Live Mode
            result = engine.exchange_manager.place_order(
                pair=body.pair.upper(),
                side=body.side.upper(),
                quantity=quantity,
                price=current_price,
                order_type="LIMIT",
            )
            trade = Trade(
                pair=body.pair.upper(),
                strategy=strategy_name,
                side=body.side.upper(),
                entry_price=current_price,
                quantity=quantity,
                status="OPEN",
                paper_mode=False,
                stop_loss=body.stop_loss,
                take_profit=body.take_profit,
                entry_reason="Manual trade placed by user",
                created_at=datetime.utcnow(),
            )
            db.add(trade)
            db.commit()
            db.refresh(trade)
    except Exception as exc:
        if isinstance(exc, HTTPException):
            raise exc
        raise HTTPException(status_code=500, detail=f"Trade execution failed: {exc}") from exc

    return trade


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# POST /api/trade/close/{trade_id}
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.post("/api/trade/close/{trade_id}", summary="Close a trade", response_model=TradeResponse)
async def close_trade(
    trade_id: int,
    request: Request,
    db: Session = Depends(get_db),
) -> Trade:
    """
    Closes a trade at the current market price and calculates realised PnL.
    """
    trade = db.query(Trade).filter(Trade.id == trade_id).first()
    if trade is None:
        raise HTTPException(status_code=404, detail=f"Trade {trade_id} not found.")
    if trade.status != "OPEN":
        raise HTTPException(status_code=400, detail=f"Trade {trade_id} is already {trade.status}.")

    engine = request.app.state.engine
    try:
        # Close via engine which handles paper trader and exchanges properly
        engine.close_trade(trade_id, "MANUAL")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to close trade: {exc}") from exc

    db.refresh(trade)
    return trade


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# POST /api/trades/close-all
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.post("/api/trades/close-all", summary="Emergency exit: Close all open trades")
async def close_all_trades(
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """
    Emergency exit: Closes all open trades immediately.
    """
    open_trades = db.query(Trade).filter(Trade.status == "OPEN").all()
    if not open_trades:
        return {"message": "No open trades to close.", "closed_count": 0}

    engine = request.app.state.engine
    closed_ids = []
    errors = []

    for trade in open_trades:
        try:
            engine.close_trade(trade.id, "EMERGENCY_EXIT")
            closed_ids.append(trade.id)
        except Exception as e:
            errors.append(f"Trade {trade.id}: {e}")

    if errors:
        raise HTTPException(
            status_code=500,
            detail={"message": f"Closed {len(closed_ids)} trades, but failed on some.", "errors": errors}
        )

    return {
        "message": f"Successfully closed all {len(closed_ids)} open trades.",
        "closed_count": len(closed_ids),
        "closed_ids": closed_ids
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GET /api/trades/export
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CSV_COLUMNS = [
    "id",
    "pair",
    "side",
    "strategy",
    "entry_price",
    "exit_price",
    "quantity",
    "amount_inr",
    "pnl",
    "pnl_pct",
    "status",
    "paper_mode",
    "created_at",
    "closed_at",
]


@router.get("/api/trades/export", summary="Export trade history as CSV")
async def export_trades(db: Session = Depends(get_db)) -> StreamingResponse:
    """Stream all trades as a downloadable CSV file."""
    trades = db.query(Trade).order_by(desc(Trade.created_at)).all()

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CSV_COLUMNS, extrasaction="ignore")
    writer.writeheader()

    for t in trades:
        row: dict[str, Any] = {}
        for col in CSV_COLUMNS:
            val = getattr(t, col, "")
            if isinstance(val, datetime):
                val = val.isoformat()
            row[col] = val if val is not None else ""
        writer.writerow(row)

    buffer.seek(0)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"autotrader_trades_{timestamp}.csv"

    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
