"""
AutoTrader Pro - Unified Position Tracker
=========================================
Centralized position management and mark-to-market tracking across all
monitored cryptocurrency pairs. Consolidates individual trades into aggregate
net positions, maintains dynamic risk thresholds, and calculates exposure
and unrealized PnL.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

from backend.utils.logger import bot_logger
from backend.utils.helpers import calculate_pnl, calculate_pnl_pct


@dataclass
class Position:
    """
    Represents an active net position in a trading pair.

    Attributes:
        pair: Ticker symbol (e.g. 'BTC/INR')
        direction: 'LONG' (from BUY) or 'SHORT' (from SELL)
        quantity: Total open quantity
        avg_entry_price: Volume-weighted average entry price
        stop_loss: Active stop loss price
        take_profit: Active take profit price
        trailing_stop: Trailing stop price if enabled
        strategy: Strategy name or combined strategy label
        trade_ids: List of database trade IDs comprising this position
        opened_at: ISO-8601 timestamp string when position was first opened
        unrealized_pnl: Mark-to-market profit/loss in INR
        unrealized_pnl_pct: Mark-to-market profit/loss percentage
    """
    pair: str
    direction: str
    quantity: float
    avg_entry_price: float
    stop_loss: float
    take_profit: float
    trailing_stop: Optional[float] = None
    strategy: str = "MANUAL"
    trade_ids: List[int] = field(default_factory=list)
    opened_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    unrealized_pnl: float = 0.0
    unrealized_pnl_pct: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert position dataclass to dictionary."""
        return {
            "pair": self.pair,
            "direction": self.direction,
            "quantity": round(self.quantity, 6),
            "avg_entry_price": round(self.avg_entry_price, 4),
            "stop_loss": round(self.stop_loss, 4) if self.stop_loss is not None else None,
            "take_profit": round(self.take_profit, 4) if self.take_profit is not None else None,
            "trailing_stop": round(self.trailing_stop, 4) if self.trailing_stop is not None else None,
            "strategy": self.strategy,
            "trade_ids": list(self.trade_ids),
            "opened_at": self.opened_at,
            "unrealized_pnl": round(self.unrealized_pnl, 2),
            "unrealized_pnl_pct": round(self.unrealized_pnl_pct, 2),
        }


class PositionTracker:
    """
    Unified registry of all open trading positions across the engine.
    """

    def __init__(self) -> None:
        # Keyed by trading pair symbol (e.g. 'BTC/INR')
        self.positions: Dict[str, Position] = {}

    def open_position(self, trade_info: Dict[str, Any]) -> Position:
        """
        Create a new position or aggregate into an existing position for the pair.

        Args:
            trade_info: Dict containing pair, side, quantity, price, stop_loss,
                        take_profit, strategy, trade_id / id.

        Returns:
            The created or updated Position instance.
        """
        pair = str(trade_info.get("pair", "")).upper()
        side = str(trade_info.get("side", "BUY")).upper()
        direction = "LONG" if side == "BUY" else "SHORT"
        qty = float(trade_info.get("quantity", 0.0))
        price = float(trade_info.get("price", 0.0) or trade_info.get("entry_price", 0.0))
        sl = float(trade_info.get("stop_loss", 0.0) or 0.0)
        tp = float(trade_info.get("take_profit", 0.0) or 0.0)
        trailing_stop = trade_info.get("trailing_stop")
        strategy = str(trade_info.get("strategy", "MANUAL"))
        trade_id = trade_info.get("trade_id") or trade_info.get("id")

        if pair in self.positions:
            existing = self.positions[pair]
            if existing.direction == direction:
                # Same direction: aggregate position using weighted average entry
                total_qty = existing.quantity + qty
                if total_qty > 0:
                    new_avg = (
                        (existing.avg_entry_price * existing.quantity) + (price * qty)
                    ) / total_qty
                else:
                    new_avg = price

                existing.quantity = round(total_qty, 6)
                existing.avg_entry_price = round(new_avg, 4)
                if trade_id is not None and trade_id not in existing.trade_ids:
                    existing.trade_ids.append(int(trade_id))

                # Update stop-loss and take-profit if provided
                if sl > 0:
                    existing.stop_loss = sl
                if tp > 0:
                    existing.take_profit = tp
                if trailing_stop is not None:
                    existing.trailing_stop = trailing_stop

                bot_logger.info(
                    f"[PositionTracker] Aggregated into existing {direction} on {pair}: "
                    f"Total Qty={existing.quantity:.6f} @ AvgPrice=₹{existing.avg_entry_price:.2f}"
                )
                return existing
            else:
                # Opposite direction: reduce or flip position
                net_qty = existing.quantity - qty
                if net_qty > 0:
                    existing.quantity = round(net_qty, 6)
                    bot_logger.info(
                        f"[PositionTracker] Reduced {existing.direction} on {pair} to {existing.quantity:.6f}"
                    )
                    return existing
                elif net_qty < 0:
                    # Flipped position
                    self.positions[pair] = Position(
                        pair=pair,
                        direction=direction,
                        quantity=round(abs(net_qty), 6),
                        avg_entry_price=price,
                        stop_loss=sl,
                        take_profit=tp,
                        trailing_stop=trailing_stop,
                        strategy=strategy,
                        trade_ids=[int(trade_id)] if trade_id is not None else [],
                        opened_at=datetime.now(timezone.utc).isoformat(),
                    )
                    bot_logger.info(
                        f"[PositionTracker] Flipped position on {pair} to {direction} Qty={abs(net_qty):.6f}"
                    )
                    return self.positions[pair]
                else:
                    # Exactly closed
                    del self.positions[pair]
                    bot_logger.info(f"[PositionTracker] Position on {pair} net zeroed out.")
                    return Position(
                        pair=pair,
                        direction=direction,
                        quantity=0.0,
                        avg_entry_price=price,
                        stop_loss=sl,
                        take_profit=tp,
                    )

        # New Position
        pos = Position(
            pair=pair,
            direction=direction,
            quantity=round(qty, 6),
            avg_entry_price=price,
            stop_loss=sl,
            take_profit=tp,
            trailing_stop=trailing_stop,
            strategy=strategy,
            trade_ids=[int(trade_id)] if trade_id is not None else [],
            opened_at=datetime.now(timezone.utc).isoformat(),
        )
        self.positions[pair] = pos
        bot_logger.info(
            f"[PositionTracker] Opened new {direction} on {pair}: {qty:.6f} @ ₹{price:.2f} | Strategy={strategy}"
        )
        return pos

    def close_position(self, pair: str, exit_price: float, reason: str = "MANUAL") -> float:
        """
        Close an existing position for pair and return realized PnL.

        Args:
            pair: Ticker symbol (e.g. 'BTC/INR')
            exit_price: Fill price at close
            reason: Reason for closure

        Returns:
            Realized PnL in INR.
        """
        pair_upper = pair.upper()
        pos = self.positions.pop(pair_upper, None)
        if pos is None:
            return 0.0

        pnl = calculate_pnl(
            entry_price=pos.avg_entry_price,
            current_price=exit_price,
            quantity=pos.quantity,
            side="BUY" if pos.direction == "LONG" else "SELL",
        )
        bot_logger.info(
            f"[PositionTracker] Closed {pos.direction} on {pair_upper} @ ₹{exit_price:.2f} ({reason}) | Realized PnL: ₹{pnl:+.2f}"
        )
        return round(pnl, 2)

    def update_mark_to_market(self, current_prices: Dict[str, float]) -> None:
        """
        Recalculate unrealized PnL and return percentages for all open positions.
        """
        for pair, pos in self.positions.items():
            curr_p = current_prices.get(pair)
            if curr_p and curr_p > 0:
                side = "BUY" if pos.direction == "LONG" else "SELL"
                pnl = calculate_pnl(pos.avg_entry_price, curr_p, pos.quantity, side)
                pnl_pct = calculate_pnl_pct(pos.avg_entry_price, curr_p, side)
                pos.unrealized_pnl = round(pnl, 2)
                pos.unrealized_pnl_pct = round(pnl_pct, 2)

    def get_position(self, pair: str) -> Optional[Position]:
        """Return the open position for *pair*, or None."""
        return self.positions.get(pair.upper())

    def get_all_positions(self) -> List[Position]:
        """Return a list of all active open positions."""
        return list(self.positions.values())

    def get_total_exposure(self) -> float:
        """Calculate total gross notional exposure across all open positions."""
        return round(
            sum(pos.avg_entry_price * pos.quantity for pos in self.positions.values()),
            2,
        )

    def get_total_unrealized_pnl(self) -> float:
        """Calculate total aggregate unrealized PnL in INR."""
        return round(sum(pos.unrealized_pnl for pos in self.positions.values()), 2)

    def sync_with_paper_trader(
        self,
        paper_trader: Any,
        current_prices: Optional[Dict[str, float]] = None,
    ) -> None:
        """
        Synchronize position tracker state with PaperTrader in-memory positions.
        """
        if not paper_trader or not hasattr(paper_trader, "positions"):
            return

        # Rebuild registry from active paper trader positions
        new_positions: Dict[str, Position] = {}
        for trade_id, pos_dict in paper_trader.positions.items():
            pair = str(pos_dict.get("pair", "")).upper()
            side = str(pos_dict.get("side", "BUY")).upper()
            direction = "LONG" if side == "BUY" else "SHORT"
            qty = float(pos_dict.get("quantity", 0.0))
            price = float(pos_dict.get("entry_price", 0.0))
            sl = float(pos_dict.get("stop_loss", 0.0) or 0.0)
            tp = float(pos_dict.get("take_profit", 0.0) or 0.0)
            trailing_stop = pos_dict.get("trailing_stop")
            strategy = pos_dict.get("strategy", "MANUAL")
            opened_at = pos_dict.get("created_at") or datetime.now(timezone.utc).isoformat()

            if pair in new_positions:
                ex = new_positions[pair]
                total_qty = ex.quantity + qty
                ex.avg_entry_price = (
                    ((ex.avg_entry_price * ex.quantity) + (price * qty)) / total_qty
                    if total_qty > 0
                    else price
                )
                ex.quantity = total_qty
                ex.trade_ids.append(int(trade_id))
            else:
                new_positions[pair] = Position(
                    pair=pair,
                    direction=direction,
                    quantity=qty,
                    avg_entry_price=price,
                    stop_loss=sl,
                    take_profit=tp,
                    trailing_stop=trailing_stop,
                    strategy=strategy,
                    trade_ids=[int(trade_id)],
                    opened_at=opened_at,
                )

        self.positions = new_positions
        if current_prices:
            self.update_mark_to_market(current_prices)

    def sync_from_trades(
        self,
        trades: List[Any],
        current_prices: Optional[Dict[str, float]] = None,
    ) -> None:
        """
        Reconstruct positions from a given list of Trade records.
        """
        try:
            new_positions: Dict[str, Position] = {}
            for t in trades:
                pair = str(t.pair).upper()
                side = str(t.side).upper()
                direction = "LONG" if side == "BUY" else "SHORT"
                qty = float(t.quantity or 0.0)
                price = float(t.entry_price or 0.0)
                sl = float(t.stop_loss or 0.0)
                tp = float(t.take_profit or 0.0)
                trailing_stop = t.trailing_stop
                strategy = t.strategy or "MANUAL"
                opened_at = t.created_at.isoformat() if t.created_at else datetime.now(timezone.utc).isoformat()

                if pair in new_positions:
                    ex = new_positions[pair]
                    tot = ex.quantity + qty
                    ex.avg_entry_price = (
                        ((ex.avg_entry_price * ex.quantity) + (price * qty)) / tot
                        if tot > 0
                        else price
                    )
                    ex.quantity = tot
                    if t.id and t.id not in ex.trade_ids:
                        ex.trade_ids.append(t.id)
                else:
                    new_positions[pair] = Position(
                        pair=pair,
                        direction=direction,
                        quantity=qty,
                        avg_entry_price=price,
                        stop_loss=sl,
                        take_profit=tp,
                        trailing_stop=trailing_stop,
                        strategy=strategy,
                        trade_ids=[t.id] if t.id else [],
                        opened_at=opened_at,
                    )
            self.positions = new_positions
            if current_prices:
                self.update_mark_to_market(current_prices)
        except Exception as exc:
            bot_logger.error(f"[PositionTracker] sync_from_trades error: {exc}")

    def sync_with_db(
        self,
        db: Any,
        current_prices: Optional[Dict[str, float]] = None,
    ) -> None:
        """
        Reconstruct positions from all OPEN Trade records in the SQLite database.
        """
        from backend.models import Trade
        try:
            open_trades = db.query(Trade).filter(Trade.status == "OPEN").all()
            new_positions: Dict[str, Position] = {}
            for t in open_trades:
                pair = str(t.pair).upper()
                side = str(t.side).upper()
                direction = "LONG" if side == "BUY" else "SHORT"
                qty = float(t.quantity or 0.0)
                price = float(t.entry_price or 0.0)
                sl = float(t.stop_loss or 0.0)
                tp = float(t.take_profit or 0.0)
                trailing_stop = t.trailing_stop
                strategy = t.strategy or "MANUAL"
                opened_at = t.created_at.isoformat() if t.created_at else datetime.now(timezone.utc).isoformat()

                if pair in new_positions:
                    ex = new_positions[pair]
                    tot = ex.quantity + qty
                    ex.avg_entry_price = (
                        ((ex.avg_entry_price * ex.quantity) + (price * qty)) / tot
                        if tot > 0
                        else price
                    )
                    ex.quantity = tot
                    ex.trade_ids.append(t.id)
                else:
                    new_positions[pair] = Position(
                        pair=pair,
                        direction=direction,
                        quantity=qty,
                        avg_entry_price=price,
                        stop_loss=sl,
                        take_profit=tp,
                        trailing_stop=trailing_stop,
                        strategy=strategy,
                        trade_ids=[t.id],
                        opened_at=opened_at,
                    )
            self.positions = new_positions
            if current_prices:
                self.update_mark_to_market(current_prices)
        except Exception as exc:
            bot_logger.error(f"[PositionTracker] DB sync error: {exc}")

    def update_stop_loss(self, pair: str, new_stop_loss: float) -> bool:
        """Update stop loss price for an open position."""
        pos = self.positions.get(pair.upper())
        if pos:
            pos.stop_loss = new_stop_loss
            return True
        return False

    def update_take_profit(self, pair: str, new_take_profit: float) -> bool:
        """Update take profit price for an open position."""
        pos = self.positions.get(pair.upper())
        if pos:
            pos.take_profit = new_take_profit
            return True
        return False

    def update_trailing_stop(self, pair: str, new_trailing_stop: float) -> bool:
        """Update trailing stop price for an open position."""
        pos = self.positions.get(pair.upper())
        if pos:
            pos.trailing_stop = new_trailing_stop
            return True
        return False
