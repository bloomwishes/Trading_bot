"""
AutoTrader Pro - Risk Manager
Configurable position-sizing, stop-loss, take-profit, trailing-stop,
and daily-loss-limit logic.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple

from sqlalchemy.orm import Session

from backend.config import settings
from backend.utils.logger import bot_logger


class RiskManager:
    """Centralised risk-control engine.

    All percentage parameters are stored as plain floats
    (e.g. 5.0 means 5 %).
    """

    def __init__(self) -> None:
        # Load defaults from global settings
        self.max_position_pct: float = settings.MAX_POSITION_PCT
        self.max_open_trades: int = settings.MAX_OPEN_TRADES
        self.daily_loss_limit_pct: float = settings.DAILY_LOSS_LIMIT_PCT
        self.default_stop_loss_pct: float = settings.DEFAULT_STOP_LOSS_PCT
        self.default_take_profit_pct: float = settings.DEFAULT_TAKE_PROFIT_PCT
        self.trailing_stop_activate_pct: float = settings.TRAILING_STOP_ACTIVATE_PCT
        self.trailing_stop_trail_pct: float = settings.TRAILING_STOP_TRAIL_PCT

    # ── Gate-keeper ────────────────────────────────────────────────────
    def can_open_trade(
        self,
        portfolio_value: float,
        num_open_trades: int,
    ) -> Tuple[bool, str]:
        """Check whether a new trade is permissible.

        Returns (allowed: bool, reason: str).
        """
        if num_open_trades >= self.max_open_trades:
            reason = (
                f"Max open trades reached ({num_open_trades}/{self.max_open_trades})"
            )
            bot_logger.warning(f"Risk gate: {reason}")
            return False, reason

        if portfolio_value <= 0:
            reason = "Portfolio value is zero or negative"
            bot_logger.warning(f"Risk gate: {reason}")
            return False, reason

        return True, "OK"

    # ── Position sizing ────────────────────────────────────────────────
    def calculate_position_size(
        self,
        portfolio_value: float,
        entry_price: float,
    ) -> float:
        """Return the maximum quantity to buy given position-size limits.

        quantity = (portfolio_value * max_position_pct / 100) / entry_price
        """
        if entry_price <= 0:
            return 0.0
        max_notional = portfolio_value * (self.max_position_pct / 100.0)
        quantity = max_notional / entry_price
        return round(quantity, 8)

    # ── Stop-loss / take-profit ────────────────────────────────────────
    def calculate_stop_loss(self, entry_price: float, side: str) -> float:
        """Return the initial stop-loss price."""
        pct = self.default_stop_loss_pct / 100.0
        if side.upper() == "BUY":
            return round(entry_price * (1.0 - pct), 2)
        else:
            return round(entry_price * (1.0 + pct), 2)

    def calculate_take_profit(self, entry_price: float, side: str) -> float:
        """Return the initial take-profit price."""
        pct = self.default_take_profit_pct / 100.0
        if side.upper() == "BUY":
            return round(entry_price * (1.0 + pct), 2)
        else:
            return round(entry_price * (1.0 - pct), 2)

    # ── Daily loss limit ───────────────────────────────────────────────
    def check_daily_loss_limit(self, db_session: Session) -> bool:
        """Return True if the daily loss limit has been breached.

        Scans all trades closed today and sums realised PnL.
        """
        from backend.models import Trade

        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        closed_today = (
            db_session.query(Trade)
            .filter(
                Trade.status == "CLOSED",
                Trade.closed_at >= today_start,
            )
            .all()
        )

        total_pnl = sum(t.pnl for t in closed_today if t.pnl is not None)

        if total_pnl >= 0:
            return False  # no loss

        # Need portfolio value to compute pct – use total_value from latest snapshot
        from backend.models import PortfolioSnapshot

        snapshot = (
            db_session.query(PortfolioSnapshot)
            .order_by(PortfolioSnapshot.created_at.desc())
            .first()
        )
        portfolio_value = snapshot.total_value if snapshot else settings.PAPER_BALANCE

        if portfolio_value <= 0:
            return True

        loss_pct = abs(total_pnl) / portfolio_value * 100.0
        if loss_pct >= self.daily_loss_limit_pct:
            bot_logger.warning(
                f"Daily loss limit breached: {loss_pct:.2f}% "
                f"(limit {self.daily_loss_limit_pct}%)"
            )
            return True
        return False

    # ── Trailing stop ──────────────────────────────────────────────────
    def update_trailing_stop(
        self,
        trade: Any,
        current_price: float,
    ) -> Optional[float]:
        """Recalculate trailing stop for an open trade.

        The trailing stop activates once price moves *activate_pct* in
        favour, then trails by *trail_pct*.

        Returns the new trailing-stop price, or None if no update needed.
        """
        entry = trade.entry_price
        side = trade.side.upper()
        activate_pct = self.trailing_stop_activate_pct / 100.0
        trail_pct = self.trailing_stop_trail_pct / 100.0

        if side == "BUY":
            activation_price = entry * (1.0 + activate_pct)
            if current_price >= activation_price:
                new_stop = round(current_price * (1.0 - trail_pct), 2)
                existing = trade.trailing_stop
                if existing is None or new_stop > existing:
                    return new_stop
        else:  # SELL (short)
            activation_price = entry * (1.0 - activate_pct)
            if current_price <= activation_price:
                new_stop = round(current_price * (1.0 + trail_pct), 2)
                existing = trade.trailing_stop
                if existing is None or new_stop < existing:
                    return new_stop

        return None

    # ── Exit checks ────────────────────────────────────────────────────
    def should_stop_loss(self, trade: Any, current_price: float) -> bool:
        """Return True if current price has breached the stop-loss level."""
        # Prefer trailing stop if set, else static stop-loss
        stop = trade.trailing_stop if trade.trailing_stop is not None else trade.stop_loss
        if stop is None:
            return False
        if trade.side.upper() == "BUY":
            return current_price <= stop
        else:
            return current_price >= stop

    def should_take_profit(self, trade: Any, current_price: float) -> bool:
        """Return True if current price has reached the take-profit level."""
        tp = trade.take_profit
        if tp is None:
            return False
        if trade.side.upper() == "BUY":
            return current_price >= tp
        else:
            return current_price <= tp

    # ── Settings introspection ─────────────────────────────────────────
    def get_settings(self) -> Dict[str, Any]:
        """Return current risk parameters as a dict."""
        return {
            "max_position_pct": self.max_position_pct,
            "max_open_trades": self.max_open_trades,
            "daily_loss_limit_pct": self.daily_loss_limit_pct,
            "default_stop_loss_pct": self.default_stop_loss_pct,
            "default_take_profit_pct": self.default_take_profit_pct,
            "trailing_stop_activate_pct": self.trailing_stop_activate_pct,
            "trailing_stop_trail_pct": self.trailing_stop_trail_pct,
        }

    def update_settings(self, new_settings: Dict[str, Any]) -> None:
        """Merge *new_settings* into the current parameters."""
        field_map = {
            "max_position_pct": float,
            "max_open_trades": int,
            "daily_loss_limit_pct": float,
            "default_stop_loss_pct": float,
            "default_take_profit_pct": float,
            "trailing_stop_activate_pct": float,
            "trailing_stop_trail_pct": float,
        }
        for key, cast in field_map.items():
            if key in new_settings:
                try:
                    setattr(self, key, cast(new_settings[key]))
                except (ValueError, TypeError):
                    bot_logger.warning(
                        f"RiskManager: invalid value for {key}: {new_settings[key]}"
                    )

        bot_logger.info(f"RiskManager settings updated: {self.get_settings()}")


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
risk_manager = RiskManager()
