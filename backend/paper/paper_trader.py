"""
AutoTrader Pro - Paper Trader
Simulated trading engine that mirrors live execution against real market
prices while persisting every trade to the database with paper_mode=True.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from backend.config import settings
from backend.database import SessionLocal
from backend.models import Trade, PortfolioSnapshot
from backend.utils.helpers import calculate_pnl, format_inr
from backend.utils.logger import bot_logger


class PaperTrader:
    """In-memory paper-trading engine backed by the SQLite trades table.

    Positions are tracked in RAM for speed; every mutation is also
    written to the database so it survives restarts.
    """

    def __init__(self, initial_balance: Optional[float] = None) -> None:
        # positions: {trade_id: position_dict}
        self.positions: Dict[int, Dict[str, Any]] = {}

        # Restore any trades that were still OPEN from a previous run
        self._restore_open_positions()

    @property
    def balance(self) -> float:
        """Calculate the current paper trading cash balance dynamically from trades in DB.

        Cash Balance = starting_balance + sum(pnl of closed trades) - sum(entry cost of open BUY trades)
        """
        session = SessionLocal()
        try:
            from sqlalchemy import func
            
            # Sum PnL of all closed paper trades
            closed_pnl = session.query(func.sum(Trade.pnl)).filter(
                Trade.status == "CLOSED",
                Trade.paper_mode.is_(True)
            ).scalar() or 0.0

            # Sum entry cost of all open paper BUY trades
            open_buy_cost = session.query(func.sum(Trade.entry_price * Trade.quantity)).filter(
                Trade.status == "OPEN",
                Trade.side == "BUY",
                Trade.paper_mode.is_(True)
            ).scalar() or 0.0

            return round(settings.PAPER_BALANCE + closed_pnl - open_buy_cost, 2)
        except Exception as exc:
            bot_logger.error(f"Error calculating paper balance dynamically: {exc}")
            return settings.PAPER_BALANCE
        finally:
            session.close()

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
        """Open a paper trade at the given price.

        Returns a dict mirroring the Trade model fields.
        """
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
                "quantity": quantity,
                "strategy": strategy,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "trailing_stop": None,
                "entry_reason": entry_reason,
                "created_at": trade.created_at.isoformat(),
            }
            self.positions[trade.id] = pos

            bot_logger.info(
                f"📝 Paper {side} {quantity} {pair} @ {format_inr(price)} "
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
