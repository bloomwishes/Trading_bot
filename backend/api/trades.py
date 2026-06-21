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
    paper_mode: Optional[bool] = Query(None, description="Filter by paper_mode flag"),
    db: Session = Depends(get_db),
) -> list[Trade]:
    query = db.query(Trade).filter(Trade.status == "OPEN")
    if paper_mode is not None:
        query = query.filter(Trade.paper_mode == paper_mode)
    return query.order_by(desc(Trade.created_at)).all()


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
    limit: int = Query(50, ge=1, le=500, description="Page size"),
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

    return query.order_by(desc(Trade.closed_at)).offset(offset).limit(limit).all()


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

    # ── Risk validation ──────────────────────────────────────────────────
    risk_settings = risk_mgr.get_settings()

    # Check max position size
    max_pos = getattr(risk_settings, "max_position_size_inr", None) or getattr(risk_settings, "max_position_size", None)
    if max_pos and body.amount_inr > max_pos:
        raise HTTPException(
            status_code=400,
            detail=f"Amount ₹{body.amount_inr:,.2f} exceeds max position size ₹{max_pos:,.2f}.",
        )

    # Check max open trades
    max_open = getattr(risk_settings, "max_open_trades", None)
    if max_open:
        open_count = db.query(Trade).filter(Trade.status == "OPEN").count()
        if open_count >= max_open:
            raise HTTPException(
                status_code=400,
                detail=f"Max open trades ({max_open}) reached. Close a trade first.",
            )

    # ── Fetch current price ──────────────────────────────────────────────
    try:
        exchange = engine.exchange_manager
        ticker = exchange.fetch_ticker(body.pair)
        current_price = float(ticker.get("last", 0)) if isinstance(ticker, dict) else float(ticker)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Could not fetch price for {body.pair}: {exc}") from exc

    if current_price <= 0:
        raise HTTPException(status_code=502, detail=f"Invalid price received for {body.pair}.")

    # ── Create trade record ──────────────────────────────────────────────
    quantity = body.amount_inr / current_price

    trade = Trade(
        pair=body.pair.upper(),
        side=body.side.upper(),
        entry_price=current_price,
        quantity=quantity,
        amount_inr=body.amount_inr,
        strategy="MANUAL",
        status="OPEN",
        paper_mode=(engine.mode == "paper"),
        created_at=datetime.utcnow(),
    )

    # Optional stop-loss / take-profit from body
    if hasattr(body, "stop_loss") and body.stop_loss is not None:
        trade.stop_loss = body.stop_loss
    if hasattr(body, "take_profit") and body.take_profit is not None:
        trade.take_profit = body.take_profit

    db.add(trade)
    db.commit()
    db.refresh(trade)

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

    # ── Fetch exit price ─────────────────────────────────────────────────
    engine = request.app.state.engine
    try:
        ticker = engine.exchange_manager.fetch_ticker(trade.pair)
        exit_price = float(ticker.get("last", 0)) if isinstance(ticker, dict) else float(ticker)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Could not fetch exit price: {exc}") from exc

    if exit_price <= 0:
        raise HTTPException(status_code=502, detail="Invalid exit price received.")

    # ── PnL calculation ──────────────────────────────────────────────────
    if trade.side == "BUY":
        pnl = (exit_price - trade.entry_price) * trade.quantity
    else:
        pnl = (trade.entry_price - exit_price) * trade.quantity

    pnl_pct = ((exit_price - trade.entry_price) / trade.entry_price * 100) if trade.entry_price else 0.0
    if trade.side == "SELL":
        pnl_pct = -pnl_pct

    trade.exit_price = exit_price
    trade.pnl = round(pnl, 2)
    trade.pnl_pct = round(pnl_pct, 2)
    trade.status = "CLOSED"
    trade.closed_at = datetime.utcnow()

    db.commit()
    db.refresh(trade)

    return trade


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
