"""
AutoTrader Pro - Paper Trader
Simulated trading engine that mirrors live execution against real market
prices while persisting every trade to the database with paper_mode=True.
"""

from __future__ import annotations

import json
import random
from datetime import datetime
from typing import Any, Dict, List, Optional

from backend.config import settings
from backend.database import SessionLocal
from backend.models import Trade
from backend.utils.helpers import calculate_pnl, format_inr
from backend.utils.logger import bot_logger


class PaperTrader:
    """In-memory paper-trading engine backed by the SQLite trades table.

    Positions are tracked in RAM for speed; every mutation is also
    written to the database so it survives restarts.
    """

    def __init__(self, initial_balance: Optional[float] = None) -> None:
        self.balance: float = initial_balance or settings.PAPER_BALANCE
        # positions: {trade_id: position_dict}
        self.positions: Dict[int, Dict[str, Any]] = {}

        # Restore any trades that were still OPEN from a previous run
        self._restore_open_positions()

    # ── Restore on startup ─────────────────────────────────────────────
    def _restore_open_positions(self) -> None:
        """Reload OPEN paper trades from the database."""
        session = SessionLocal()
        try:
            open_trades = (
                session.query(Trade)
                .filter(Trade.status == "OPEN", Trade.paper_mode.is_(True))
                .all()
            )
            for t in open_trades:
                self.positions[t.id] = {
                    "id": t.id,
                    "pair": t.pair,
                    "side": t.side,
                    "entry_price": t.entry_price,
                    "quantity": t.quantity,
                    "strategy": t.strategy,
                    "stop_loss": t.stop_loss,
                    "take_profit": t.take_profit,
                    "trailing_stop": t.trailing_stop,
                    "created_at": t.created_at.isoformat() if t.created_at else None,
                }
            if open_trades:
                bot_logger.info(
                    f"PaperTrader restored {len(open_trades)} open position(s)"
                )
        except Exception as exc:
            bot_logger.error(f"PaperTrader restore error: {exc}")
        finally:
            session.close()

    # ── Execute a new trade ────────────────────────────────────────────
    def execute_trade(
        self,
        pair: str,
        side: str,
        quantity: float,
        price: float,
        strategy: str = "manual",
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        entry_reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Open a paper trade at the exact given price (backward compatible).

        Returns a dict mirroring the Trade model fields.
        """
        return self._do_execute(
            pair=pair,
            side=side,
            quantity=quantity,
            price=price,
            strategy=strategy,
            stop_loss=stop_loss,
            take_profit=take_profit,
            entry_reason=entry_reason,
            order_type="EXACT",
            slippage_bps=0.0,
            had_partial=False,
            requested_price=price,
        )

    def execute_trade_with_slippage(
        self,
        pair: str,
        side: str,
        quantity: float,
        price: float,
        strategy: str = "manual",
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        entry_reason: Optional[str] = None,
        order_type: str = "MARKET",
        timeout_seconds: float = 15.0,
    ) -> Dict[str, Any]:
        """
        Execute paper trade with realistic slippage and partial fill modeling:
        - Market order: 0.01% - 0.05% slippage against trade direction.
        - Limit order: 80% full fill at price; 20% partial fill (50-90% at price, remainder at market with slippage).
        """
        side_norm = side.upper()
        order_type_norm = (order_type or "MARKET").upper()
        had_partial = False

        if order_type_norm == "LIMIT":
            # 80% chance of full fill at limit price, 20% partial fill
            is_partial = random.random() < 0.20
            if is_partial:
                had_partial = True
                part_ratio = random.uniform(0.50, 0.90)
                part_qty = quantity * part_ratio
                rem_qty = quantity - part_qty

                # Remainder filled at market with slippage
                if side_norm == "BUY":
                    m_slip = 1.0 + random.uniform(0.0001, 0.0005)
                else:
                    m_slip = 1.0 - random.uniform(0.0001, 0.0005)
                rem_price = price * m_slip

                effective_price = round(
                    (part_qty * price + rem_qty * rem_price) / max(quantity, 1e-9), 4
                )
            else:
                effective_price = price
        else:
            # MARKET order: 0.01% - 0.05% slippage against direction
            slip_pct = random.uniform(0.0001, 0.0005)
            if side_norm == "BUY":
                effective_price = round(price * (1.0 + slip_pct), 4)
            else:
                effective_price = round(price * (1.0 - slip_pct), 4)

        slippage_bps = round(abs(effective_price - price) / price * 10000.0, 2) if price > 0 else 0.0

        return self._do_execute(
            pair=pair,
            side=side_norm,
            quantity=quantity,
            price=effective_price,
            strategy=strategy,
            stop_loss=stop_loss,
            take_profit=take_profit,
            entry_reason=entry_reason,
            order_type=order_type_norm,
            slippage_bps=slippage_bps,
            had_partial=had_partial,
            requested_price=price,
        )

    def _do_execute(
        self,
        pair: str,
        side: str,
        quantity: float,
        price: float,
        strategy: str,
        stop_loss: Optional[float],
        take_profit: Optional[float],
        entry_reason: Optional[str],
        order_type: str,
        slippage_bps: float,
        had_partial: bool,
        requested_price: float,
    ) -> Dict[str, Any]:
        """Internal worker for opening paper positions and saving to database."""
        side = side.upper()
        notional = price * quantity

        if side == "BUY":
            if notional > self.balance:
                bot_logger.warning(
                    f"PaperTrader: Insufficient balance for BUY "
                    f"{quantity} {pair} @ {format_inr(price)}. "
                    f"Need {format_inr(notional)}, have {format_inr(self.balance)}"
                )
                return {"error": "Insufficient paper balance"}
            self.balance -= notional

        session = SessionLocal()
        try:
            trade = Trade(
                pair=pair,
                strategy=strategy,
                side=side,
                entry_price=price,
                quantity=quantity,
                status="OPEN",
                paper_mode=True,
                stop_loss=stop_loss,
                take_profit=take_profit,
                entry_reason=entry_reason,
                created_at=datetime.utcnow(),
            )
            session.add(trade)
            session.commit()
            session.refresh(trade)

            pos = {
                "id": trade.id,
                "pair": pair,
                "side": side,
                "entry_price": price,
                "requested_price": requested_price,
                "quantity": quantity,
                "strategy": strategy,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "trailing_stop": None,
                "entry_reason": entry_reason,
                "order_type": order_type,
                "slippage_bps": slippage_bps,
                "had_partial_fills": had_partial,
                "created_at": trade.created_at.isoformat(),
            }
            self.positions[trade.id] = pos

            slip_info = f" (slip: {slippage_bps:.1f} bps)" if slippage_bps > 0 else ""
            bot_logger.info(
                f"📝 Paper {side} {quantity} {pair} @ {format_inr(price)}{slip_info} "
                f"| Balance: {format_inr(self.balance)}"
            )
            return pos

        except Exception as exc:
            session.rollback()
            bot_logger.error(f"PaperTrader execute_trade error: {exc}")
            return {"error": str(exc)}
        finally:
            session.close()

    # ── Close an existing trade ────────────────────────────────────────
    def close_trade(
        self,
        trade_id: int,
        current_price: float,
        exit_reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Close a paper trade at *current_price*.

        Returns the updated trade dict including realised PnL.
        """
        pos = self.positions.get(trade_id)
        if pos is None:
            bot_logger.warning(f"PaperTrader: trade {trade_id} not found in positions")
            return {"error": f"Trade {trade_id} not found"}

        pnl = calculate_pnl(
            entry_price=pos["entry_price"],
            current_price=current_price,
            quantity=pos["quantity"],
            side=pos["side"],
        )

        # Credit balance
        if pos["side"] == "BUY":
            self.balance += current_price * pos["quantity"]
        else:
            self.balance += pos["entry_price"] * pos["quantity"] + pnl

        now = datetime.utcnow()

        session = SessionLocal()
        try:
            db_trade = session.query(Trade).filter(Trade.id == trade_id).first()
            if db_trade:
                db_trade.exit_price = current_price
                db_trade.pnl = round(pnl, 2)
                db_trade.status = "CLOSED"
                db_trade.closed_at = now
                db_trade.exit_reason = exit_reason
                session.commit()

            del self.positions[trade_id]

            pnl_str = format_inr(pnl)
            emoji = "✅" if pnl >= 0 else "❌"
            bot_logger.info(
                f"{emoji} Paper CLOSE trade #{trade_id} {pos['pair']} "
                f"@ {format_inr(current_price)} | PnL: {pnl_str} "
                f"| Balance: {format_inr(self.balance)}"
            )

            return {
                "id": trade_id,
                "pair": pos["pair"],
                "side": pos["side"],
                "entry_price": pos["entry_price"],
                "exit_price": current_price,
                "quantity": pos["quantity"],
                "pnl": round(pnl, 2),
                "status": "CLOSED",
                "closed_at": now.isoformat(),
            }
        except Exception as exc:
            session.rollback()
            bot_logger.error(f"PaperTrader close_trade error: {exc}")
            return {"error": str(exc)}
        finally:
            session.close()

    # ── Portfolio queries ──────────────────────────────────────────────
    def get_portfolio_value(self, current_prices: Dict[str, float]) -> float:
        """Total value = cash balance + mark-to-market of all positions."""
        total = self.balance
        for pos in self.positions.values():
            pair_price = current_prices.get(pos["pair"], pos["entry_price"])
            if pos["side"] == "BUY":
                total += pair_price * pos["quantity"]
            else:
                # Short PnL
                pnl = (pos["entry_price"] - pair_price) * pos["quantity"]
                total += pos["entry_price"] * pos["quantity"] + pnl
        return round(total, 2)

    def get_positions(self) -> List[Dict[str, Any]]:
        """Return a list of all open positions."""
        return list(self.positions.values())

    def get_balance(self) -> float:
        """Return current cash balance."""
        return round(self.balance, 2)

    # ── Trailing stop update helper ────────────────────────────────────
    def update_position_trailing_stop(
        self,
        trade_id: int,
        new_trailing_stop: float,
    ) -> None:
        """Persist a new trailing-stop value for an open position."""
        pos = self.positions.get(trade_id)
        if pos is None:
            return
        pos["trailing_stop"] = new_trailing_stop

        session = SessionLocal()
        try:
            db_trade = session.query(Trade).filter(Trade.id == trade_id).first()
            if db_trade:
                db_trade.trailing_stop = new_trailing_stop
                session.commit()
        except Exception as exc:
            session.rollback()
            bot_logger.error(f"PaperTrader trailing stop update error: {exc}")
        finally:
            session.close()

    # ── Trade History & Performance Summary ───────────────────────────
    def get_trade_history(
        self,
        limit: int = 50,
        pair_filter: Optional[str] = None,
        strategy_filter: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve recent paper trades from the database with optional filtering."""
        session = SessionLocal()
        try:
            query = session.query(Trade).filter(Trade.paper_mode.is_(True))
            if pair_filter:
                query = query.filter(Trade.pair == pair_filter.upper())
            if strategy_filter:
                query = query.filter(Trade.strategy == strategy_filter)

            trades = query.order_by(Trade.created_at.desc()).limit(limit).all()
            return [
                {
                    "id": t.id,
                    "pair": t.pair,
                    "side": t.side,
                    "strategy": t.strategy,
                    "entry_price": t.entry_price,
                    "exit_price": t.exit_price,
                    "quantity": t.quantity,
                    "amount_inr": t.amount_inr,
                    "pnl": t.pnl,
                    "pnl_pct": t.pnl_pct,
                    "status": t.status,
                    "stop_loss": t.stop_loss,
                    "take_profit": t.take_profit,
                    "trailing_stop": t.trailing_stop,
                    "created_at": t.created_at.isoformat() if t.created_at else None,
                    "closed_at": t.closed_at.isoformat() if t.closed_at else None,
                    "entry_reason": t.entry_reason,
                    "exit_reason": t.exit_reason,
                }
                for t in trades
            ]
        except Exception as exc:
            bot_logger.error(f"PaperTrader get_trade_history error: {exc}")
            return []
        finally:
            session.close()

    def get_performance_summary(self) -> Dict[str, Any]:
        """Calculate historical performance metrics across all closed paper trades."""
        session = SessionLocal()
        try:
            closed_trades = (
                session.query(Trade)
                .filter(Trade.status == "CLOSED", Trade.paper_mode.is_(True))
                .all()
            )
            total = len(closed_trades)
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
                }

            pnls = [float(t.pnl or 0.0) for t in closed_trades]
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
            for t in closed_trades:
                if t.created_at and t.closed_at:
                    hold_times.append((t.closed_at - t.created_at).total_seconds())

            avg_hold = round(sum(hold_times) / len(hold_times), 1) if hold_times else 0.0

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
            }
        except Exception as exc:
            bot_logger.error(f"PaperTrader get_performance_summary error: {exc}")
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
            }
        finally:
            session.close()
