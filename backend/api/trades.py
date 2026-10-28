"""
AutoTrader Pro — Trades Router
===============================
GET  /api/trades/open               →  open trades
GET  /api/trades/history            →  closed trades (paginated, filtered)
POST /api/trade/manual              →  create a manual trade
POST /api/trade/close/{id}          →  close a specific trade
POST /api/trades/close-all          →  emergency close all open trades
GET  /api/trades/export             →  CSV export of trade history
GET  /api/trades/performance        →  aggregated win-rate, profit factor, Sharpe
GET  /api/trades/positions          →  unified mark-to-market positions
GET  /api/trades/execution-quality  →  order execution & slippage analytics
PUT  /api/trades/{id}/stop-loss     →  update open trade stop loss
PUT  /api/trades/{id}/take-profit   →  update open trade take profit
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
from backend.schemas import (
    TradeCreate,
    TradeResponse,
    StopLossUpdate,
    TakeProfitUpdate,
)
from backend.engine.position_tracker import PositionTracker
from backend.utils.auth import require_api_key
from backend.utils.logger import bot_logger

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

@router.post(
    "/api/trade/manual",
    summary="Place a manual trade",
    response_model=TradeResponse,
    status_code=201,
    dependencies=[Depends(require_api_key)],
)
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
    if engine.mode == "paper":
        portfolio_value = engine.paper_trader.get_portfolio_value(current_prices)
    else:
        # Live mode: compute real net portfolio value from exchange balances
        try:
            balances = engine.exchange_manager.get_balances()
            portfolio_value = 0.0
            inr_info = balances.get("INR", {})
            portfolio_value += inr_info.get("available", 0.0) + inr_info.get("locked", 0.0)
            for cur, bal_dict in balances.items():
                if cur != "INR":
                    tot_cur = bal_dict.get("available", 0.0) + bal_dict.get("locked", 0.0)
                    cur_price = current_prices.get(f"{cur}/INR", 0.0)
                    portfolio_value += tot_cur * cur_price
            if portfolio_value <= 0:
                portfolio_value = inr_info.get("available", 0.0)
        except Exception as exc:
            bot_logger.error(f"[Trades API] Failed to fetch live balances for portfolio validation: {exc}")
            portfolio_value = 0.0

        if portfolio_value <= 0:
            raise HTTPException(
                status_code=400,
                detail="Cannot open live trade: Exchange portfolio value is ₹0.00 or inaccessible.",
            )

    max_pos = portfolio_value * (risk_mgr.max_position_pct / 100.0)
    if amount_inr > max_pos:
        raise HTTPException(
            status_code=400,
            detail=f"Amount ₹{amount_inr:,.2f} exceeds max position size ₹{max_pos:,.2f} ({risk_mgr.max_position_pct}% of portfolio ₹{portfolio_value:,.2f}).",
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
            # Live Mode: Round quantity to exchange precision and step size
            rounded_qty = engine.exchange_manager.round_quantity(body.pair.upper(), quantity)
            result = engine.exchange_manager.place_order(
                pair=body.pair.upper(),
                side=body.side.upper(),
                quantity=rounded_qty,
                price=current_price,
                order_type="LIMIT",
            )
            # Validate exchange response strictly
            if (
                not isinstance(result, dict)
                or "error" in result
                or result.get("status") in ("rejected", "failed")
            ):
                err_detail = result.get("error") if isinstance(result, dict) else str(result)
                bot_logger.error(f"[Trades API] Exchange rejected order: {err_detail}")
                raise HTTPException(
                    status_code=502,
                    detail=f"Exchange order rejected: {err_detail}",
                )

            trade = Trade(
                pair=body.pair.upper(),
                strategy=strategy_name,
                side=body.side.upper(),
                entry_price=current_price,
                quantity=rounded_qty,
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

        # Sync with unified position tracker
        if hasattr(engine, "position_tracker") and trade:
            engine.position_tracker.open_position({
                "pair": trade.pair,
                "side": trade.side,
                "quantity": trade.quantity,
                "price": trade.entry_price,
                "stop_loss": trade.stop_loss,
                "take_profit": trade.take_profit,
                "strategy": trade.strategy,
                "trade_id": trade.id,
            })
    except Exception as exc:
        if isinstance(exc, HTTPException):
            raise exc
        raise HTTPException(status_code=500, detail=f"Trade execution failed: {exc}") from exc

    return trade


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# POST /api/trade/close/{trade_id}
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.post(
    "/api/trade/close/{trade_id}",
    summary="Close a trade",
    response_model=TradeResponse,
    dependencies=[Depends(require_api_key)],
)
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

@router.post(
    "/api/trades/close-all",
    summary="Emergency exit: Close all open trades",
    dependencies=[Depends(require_api_key)],
)
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


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GET /api/trades/performance
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/api/trades/performance", summary="Overall trade performance metrics")
async def get_performance(
    paper_mode: Optional[bool] = Query(None, description="Filter by paper_mode"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """
    Returns aggregated metrics: win rate, profit factor, average PnL,
    best/worst trade, and estimated Sharpe ratio across closed trades.
    """
    query = db.query(Trade).filter(Trade.status == "CLOSED")
    if paper_mode is not None:
        query = query.filter(Trade.paper_mode == paper_mode)
    closed = query.all()

    total = len(closed)
    if total == 0:
        return {
            "total_trades": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "win_rate": 0.0,
            "total_pnl": 0.0,
            "avg_pnl": 0.0,
            "profit_factor": 0.0,
            "best_trade": 0.0,
            "worst_trade": 0.0,
            "avg_hold_time_seconds": 0.0,
            "sharpe_ratio": 0.0,
        }

    pnls = [float(t.pnl or 0.0) for t in closed]
    pnl_pcts = [float(t.pnl_pct or 0.0) for t in closed]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]

    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    total_pnl = sum(pnls)

    if gross_loss > 0:
        profit_factor = round(gross_profit / gross_loss, 2)
    elif gross_profit > 0:
        profit_factor = round(gross_profit, 2)
    else:
        profit_factor = 0.0

    hold_times = []
    for t in closed:
        if t.created_at and t.closed_at:
            hold_times.append((t.closed_at - t.created_at).total_seconds())
    avg_hold = round(sum(hold_times) / len(hold_times), 1) if hold_times else 0.0

    # Sharpe ratio estimate (using trade return % distribution)
    sharpe = 0.0
    if len(pnl_pcts) > 1:
        mean_ret = sum(pnl_pcts) / len(pnl_pcts)
        variance = sum((x - mean_ret) ** 2 for x in pnl_pcts) / (len(pnl_pcts) - 1)
        std_ret = variance ** 0.5
        if std_ret > 0:
            sharpe = round(mean_ret / std_ret, 3)

    return {
        "total_trades": total,
        "winning_trades": len(wins),
        "losing_trades": len(losses),
        "win_rate": round(len(wins) / total, 4),
        "total_pnl": round(total_pnl, 2),
        "avg_pnl": round(total_pnl / total, 2),
        "profit_factor": profit_factor,
        "best_trade": round(max(pnls), 2) if pnls else 0.0,
        "worst_trade": round(min(pnls), 2) if pnls else 0.0,
        "avg_hold_time_seconds": avg_hold,
        "sharpe_ratio": sharpe,
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GET /api/trades/positions
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/api/trades/positions", summary="Aggregated open positions")
async def get_positions(
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """
    Returns aggregated net positions with real-time mark-to-market valuations
    and total portfolio exposure.
    """
    engine = getattr(request.app.state, "engine", None)
    if engine and hasattr(engine, "position_tracker"):
        # Update mark-to-market prices
        current_prices: dict[str, float] = {}
        if hasattr(engine, "exchange_manager"):
            try:
                pairs = list(engine.position_tracker.positions.keys())
                for pair in pairs:
                    ticker = engine.exchange_manager.get_ticker(pair)
                    price = float(ticker.get("last_price", 0)) if isinstance(ticker, dict) else float(ticker or 0)
                    if price > 0:
                        current_prices[pair] = price
            except Exception:
                pass
        if current_prices:
            engine.position_tracker.update_mark_to_market(current_prices)

        positions = [p.to_dict() for p in engine.position_tracker.get_all_positions()]
        total_exposure = engine.position_tracker.get_total_exposure()
        return {
            "positions": positions,
            "total_exposure": round(total_exposure, 2),
            "count": len(positions),
        }

    # Fallback to DB open trades if tracker not in memory
    open_trades = db.query(Trade).filter(Trade.status == "OPEN").all()
    temp_tracker = PositionTracker()
    temp_tracker.sync_from_trades(open_trades)
    positions = [p.to_dict() for p in temp_tracker.get_all_positions()]
    return {
        "positions": positions,
        "total_exposure": round(temp_tracker.get_total_exposure(), 2),
        "count": len(positions),
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GET /api/trades/execution-quality
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/api/trades/execution-quality", summary="Order execution quality and slippage")
async def get_execution_quality(
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """
    Returns execution quality metrics: average slippage in basis points,
    router status, and supported routing architectures.
    """
    engine = getattr(request.app.state, "engine", None)
    trades = db.query(Trade).order_by(desc(Trade.created_at)).limit(100).all()

    slippages = []
    if engine and hasattr(engine, "paper_trader"):
        for t in trades:
            pos = engine.paper_trader.positions.get(t.id)
            if pos and "slippage_bps" in pos:
                slippages.append(pos["slippage_bps"])

    avg_slippage_bps = round(sum(slippages) / len(slippages), 2) if slippages else 0.0

    return {
        "analyzed_trades": len(trades),
        "average_slippage_bps": avg_slippage_bps,
        "sample_size": len(slippages),
        "router_status": "ACTIVE" if (engine and hasattr(engine, "order_router")) else "STANDBY",
        "supported_order_types": ["MARKET", "LIMIT", "TWAP"],
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PUT /api/trades/{trade_id}/stop-loss
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.put(
    "/api/trades/{trade_id}/stop-loss",
    summary="Update trade stop loss",
    response_model=TradeResponse,
    dependencies=[Depends(require_api_key)],
)
async def update_stop_loss(
    trade_id: int,
    body: StopLossUpdate,
    request: Request,
    db: Session = Depends(get_db),
) -> Trade:
    """
    Updates the stop loss price for an active trade in the database,
    memory positions, and unified position tracker.
    """
    trade = db.query(Trade).filter(Trade.id == trade_id).first()
    if not trade:
        raise HTTPException(status_code=404, detail=f"Trade #{trade_id} not found.")
    if trade.status != "OPEN":
        raise HTTPException(status_code=400, detail=f"Trade #{trade_id} is already {trade.status}.")

    trade.stop_loss = body.stop_loss
    db.commit()
    db.refresh(trade)

    # Sync with engine subsystems
    engine = getattr(request.app.state, "engine", None)
    if engine:
        if hasattr(engine, "paper_trader") and trade_id in engine.paper_trader.positions:
            engine.paper_trader.positions[trade_id]["stop_loss"] = body.stop_loss
        if hasattr(engine, "position_tracker"):
            engine.position_tracker.update_stop_loss(trade.pair, body.stop_loss)

    return trade


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PUT /api/trades/{trade_id}/take-profit
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.put(
    "/api/trades/{trade_id}/take-profit",
    summary="Update trade take profit",
    response_model=TradeResponse,
    dependencies=[Depends(require_api_key)],
)
async def update_take_profit(
    trade_id: int,
    body: TakeProfitUpdate,
    request: Request,
    db: Session = Depends(get_db),
) -> Trade:
    """
    Updates the take profit price for an active trade in the database,
    memory positions, and unified position tracker.
    """
    trade = db.query(Trade).filter(Trade.id == trade_id).first()
    if not trade:
        raise HTTPException(status_code=404, detail=f"Trade #{trade_id} not found.")
    if trade.status != "OPEN":
        raise HTTPException(status_code=400, detail=f"Trade #{trade_id} is already {trade.status}.")

    trade.take_profit = body.take_profit
    db.commit()
    db.refresh(trade)

    # Sync with engine subsystems
    engine = getattr(request.app.state, "engine", None)
    if engine:
        if hasattr(engine, "paper_trader") and trade_id in engine.paper_trader.positions:
            engine.paper_trader.positions[trade_id]["take_profit"] = body.take_profit
        if hasattr(engine, "position_tracker"):
            engine.position_tracker.update_take_profit(trade.pair, body.take_profit)

    return trade
