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
) -> list[TradeResponse]:
    query = db.query(Trade).filter(Trade.status == "OPEN")
    if paper_mode is not None:
        query = query.filter(Trade.paper_mode == paper_mode)
    trades = query.order_by(desc(Trade.created_at)).all()

    # Try to fetch current live prices to calculate real-time unrealized PnL
    engine = getattr(request.app.state, "engine", None)
    current_prices: dict[str, float] = {}
    if engine and hasattr(engine, "exchange_manager"):
        try:
            pairs = list({t.pair for t in trades})
            for pair in pairs:
                ticker = engine.exchange_manager.get_ticker(pair)
                if isinstance(ticker, dict):
                    price = float(ticker.get("last_price", 0))
                else:
                    price = float(ticker or 0)
                if price > 0:
                    current_prices[pair] = price
        except Exception:
            pass

    results: list[TradeResponse] = []
    for t in trades:
        cur_price = current_prices.get(t.pair, t.entry_price)
        multiplier = 1.0 if t.side == "BUY" else -1.0
        unrealized = (cur_price - t.entry_price) * t.quantity * multiplier if cur_price else 0.0
        unrealized_pct = ((cur_price - t.entry_price) / t.entry_price * 100.0 * multiplier) if t.entry_price else 0.0

        trade_data = {
            "id": t.id,
            "pair": t.pair,
            "strategy": t.strategy,
            "side": t.side,
            "entry_price": t.entry_price,
            "exit_price": t.exit_price,
            "quantity": t.quantity,
            "amount_inr": t.amount_inr,
            "pnl": round(unrealized, 2),
            "pnl_pct": round(unrealized_pct, 2),
            "current_price": round(cur_price, 4),
            "unrealized_pnl": round(unrealized, 2),
            "unrealized_pnl_pct": round(unrealized_pct, 2),
            "status": t.status,
            "paper_mode": t.paper_mode,
            "stop_loss": t.stop_loss,
            "take_profit": t.take_profit,
            "trailing_stop": t.trailing_stop,
            "created_at": t.created_at,
            "closed_at": t.closed_at,
            "entry_reason": t.entry_reason,
            "exit_reason": t.exit_reason,
        }
        results.append(TradeResponse(**trade_data))

    return results


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
    limit: Optional[int] = Query(None, ge=0, le=10000, description="Page size (0 or omit for all trades)"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    db: Session = Depends(get_db),
) -> list[Trade]:
    query = db.query(Trade).filter(Trade.status == "CLOSED")

    if date_from is not None:
        query = query.filter(Trade.created_at >= date_from)
    if date_to is not None:
        if date_to.hour == 0 and date_to.minute == 0 and date_to.second == 0:
            date_to_end = date_to.replace(hour=23, minute=59, second=59, microsecond=999999)
        else:
            date_to_end = date_to
        query = query.filter(Trade.created_at <= date_to_end)
    if pair is not None:
        query = query.filter(Trade.pair == pair.upper())
    if strategy is not None:
        query = query.filter(Trade.strategy == strategy)
    if paper_mode is not None:
        query = query.filter(Trade.paper_mode == paper_mode)

    query = query.order_by(desc(Trade.closed_at), desc(Trade.created_at))
    if offset > 0:
        query = query.offset(offset)
    if limit is not None and limit > 0:
        query = query.limit(limit)

    return query.all()


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
