"""
AutoTrader Pro - Portfolio Risk Monitor
=======================================
Tracks peak equity (high-water mark), real-time drawdowns, rolling weekly losses,
and win/loss streaks. Automatically enforces loss-streak cooldowns and triggers
emergency circuit-breaker shutdown upon severe drawdown.
"""

from __future__ import annotations

from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timedelta, timezone

from backend.config import settings
from backend.utils.logger import bot_logger
from backend.risk.emergency import emergency_shutdown


class PortfolioMonitor:
    """
    Monitors portfolio drawdowns from high-water mark, multi-day losses,
    and consecutive losing streaks.
    """

    def __init__(
        self,
        weekly_loss_limit_pct: float = 7.0,
        total_drawdown_limit_pct: float = 15.0,
        cooldown_after_consecutive_losses: int = 3,
        cooldown_duration_minutes: int = 60,
        initial_peak: float = 10000.0,
    ) -> None:
        self.weekly_loss_limit_pct = weekly_loss_limit_pct
        self.total_drawdown_limit_pct = total_drawdown_limit_pct
        self.cooldown_after_consecutive_losses = cooldown_after_consecutive_losses
        self.cooldown_duration_minutes = cooldown_duration_minutes

        self.high_water_mark: float = initial_peak
        self.current_value: float = initial_peak
        self.peak_drawdown_pct: float = 0.0

        self.consecutive_losses: int = 0
        self.consecutive_wins: int = 0
        self.cooldown_until: Optional[datetime] = None
        self.cooldown_reason: Optional[str] = None

    def update_portfolio_value(
        self,
        current_value: float,
        engine: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Record current portfolio mark-to-market value and evaluate drawdowns.
        """
        if current_value > 0:
            self.current_value = current_value
            if current_value > self.high_water_mark:
                self.high_water_mark = current_value

        drawdown_pct = (
            ((self.high_water_mark - self.current_value) / self.high_water_mark) * 100.0
            if self.high_water_mark > 0
            else 0.0
        )
        if drawdown_pct > self.peak_drawdown_pct:
            self.peak_drawdown_pct = round(drawdown_pct, 2)

        # Total Drawdown Circuit Breaker
        if drawdown_pct >= self.total_drawdown_limit_pct:
            reason = (
                f"Peak drawdown ({drawdown_pct:.2f}%) breached maximum allowed limit "
                f"({self.total_drawdown_limit_pct}%) from HWM ₹{self.high_water_mark:,.2f}"
            )
            bot_logger.critical(f"[PortfolioMonitor] {reason}")
            emergency_shutdown.execute(reason=reason, engine=engine)

        return self.get_state(current_value)

    def on_trade_closed(self, trade: Any, engine: Optional[Any] = None) -> None:
        """
        Update streak tracking when a trade closes.
        Applies escalating cooldown timers on losing streaks:
          - 3 losses: 60m cooldown
          - 5 losses: 4h cooldown
          - 7 losses: emergency shutdown
        """
        pnl = float(getattr(trade, "pnl", 0.0) or 0.0)

        if pnl < 0:
            self.consecutive_losses += 1
            self.consecutive_wins = 0

            bot_logger.warning(
                f"[PortfolioMonitor] Closed trade #{getattr(trade, 'id', '?')} loss: ₹{pnl:.2f}. "
                f"Streak: {self.consecutive_losses} consecutive loss(es)"
            )

            # Check streak thresholds
            if self.consecutive_losses >= 7:
                reason = f"7 consecutive losses reached ({self.consecutive_losses})"
                emergency_shutdown.execute(reason=reason, engine=engine)
            elif self.consecutive_losses >= 5:
                self.cooldown_until = datetime.utcnow() + timedelta(hours=4)
                self.cooldown_reason = f"5 consecutive losses ({self.consecutive_losses})"
                bot_logger.warning(
                    f"[PortfolioMonitor] 4-hour cooldown activated until {self.cooldown_until.isoformat()}Z"
                )
            elif self.consecutive_losses >= self.cooldown_after_consecutive_losses:
                self.cooldown_until = datetime.utcnow() + timedelta(minutes=self.cooldown_duration_minutes)
                self.cooldown_reason = f"{self.consecutive_losses} consecutive losses"
                bot_logger.warning(
                    f"[PortfolioMonitor] {self.cooldown_duration_minutes}-minute cooldown activated "
                    f"until {self.cooldown_until.isoformat()}Z"
                )
        elif pnl > 0:
            self.consecutive_wins += 1
            self.consecutive_losses = 0
            self.cooldown_until = None
            self.cooldown_reason = None
            bot_logger.info(
                f"[PortfolioMonitor] Closed trade #{getattr(trade, 'id', '?')} profit: ₹{pnl:.2f}. "
                f"Win streak: {self.consecutive_wins}"
            )

    def is_in_cooldown(self) -> Tuple[bool, str]:
        """
        Check if trading is currently suspended due to shutdown or loss-streak cooldown.
        """
        if not emergency_shutdown.is_trading_allowed():
            return True, f"Emergency shutdown active: {emergency_shutdown.last_shutdown_reason}"

        if self.cooldown_until:
            now = datetime.utcnow()
            if now < self.cooldown_until:
                remaining_sec = (self.cooldown_until - now).total_seconds()
                reason = (
                    f"Loss-streak cooldown active ({self.cooldown_reason}). "
                    f"{int(remaining_sec // 60)}m {int(remaining_sec % 60)}s remaining."
                )
                return True, reason
            else:
                # Cooldown expired
                self.cooldown_until = None
                self.cooldown_reason = None

        return False, "OK"

    def check_weekly_loss_limit(
        self,
        db_session: Any,
        portfolio_value: float,
    ) -> Tuple[bool, float, str]:
        """
        Verify rolling 7-day realized losses against weekly_loss_limit_pct.
        """
        if not db_session:
            return False, 0.0, "OK"

        from backend.models import Trade
        try:
            seven_days_ago = datetime.utcnow() - timedelta(days=7)
            closed_7d = (
                db_session.query(Trade)
                .filter(Trade.status == "CLOSED", Trade.closed_at >= seven_days_ago)
                .all()
            )
            weekly_pnl = sum(float(t.pnl or 0.0) for t in closed_7d)

            if weekly_pnl >= 0:
                return False, 0.0, "OK"

            loss_amount = abs(weekly_pnl)
            base_value = portfolio_value if portfolio_value > 0 else self.high_water_mark
            loss_pct = (loss_amount / max(base_value, 1.0)) * 100.0

            if loss_pct >= self.weekly_loss_limit_pct:
                reason = (
                    f"Weekly loss limit breached: -{loss_pct:.2f}% (₹{loss_amount:,.2f}) "
                    f">= limit {self.weekly_loss_limit_pct}% over last 7 days"
                )
                bot_logger.warning(f"[PortfolioMonitor] {reason}")
                return True, round(loss_pct, 2), reason

            return False, round(loss_pct, 2), "OK"
        except Exception as exc:
            bot_logger.warning(f"[PortfolioMonitor] Weekly loss check failed: {exc}")
            return False, 0.0, "OK"

    def get_state(
        self,
        portfolio_value: Optional[float] = None,
        db_session: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Compile full portfolio risk metrics state for API and dashboard.
        """
        val = portfolio_value or self.current_value
        hwm = max(self.high_water_mark, val)
        current_dd = round(((hwm - val) / hwm) * 100.0, 2) if hwm > 0 else 0.0

        in_cooldown, cd_reason = self.is_in_cooldown()
        remaining_sec = 0.0
        if self.cooldown_until:
            now = datetime.utcnow()
            if self.cooldown_until > now:
                remaining_sec = round((self.cooldown_until - now).total_seconds(), 1)

        weekly_pnl = 0.0
        weekly_loss_pct = 0.0
        if db_session:
            _, weekly_loss_pct, _ = self.check_weekly_loss_limit(db_session, val)
            from backend.models import Trade
            try:
                seven_days_ago = datetime.utcnow() - timedelta(days=7)
                closed_7d = (
                    db_session.query(Trade)
                    .filter(Trade.status == "CLOSED", Trade.closed_at >= seven_days_ago)
                    .all()
                )
                weekly_pnl = round(sum(float(t.pnl or 0.0) for t in closed_7d), 2)
            except Exception:
                pass

        return {
            "high_water_mark": round(hwm, 2),
            "current_value": round(val, 2),
            "current_drawdown_pct": current_dd,
            "peak_drawdown_pct": self.peak_drawdown_pct,
            "consecutive_losses": self.consecutive_losses,
            "consecutive_wins": self.consecutive_wins,
            "is_in_cooldown": in_cooldown,
            "cooldown_reason": cd_reason if in_cooldown else None,
            "cooldown_until": self.cooldown_until.isoformat() + "Z" if self.cooldown_until else None,
            "cooldown_remaining_sec": remaining_sec,
            "weekly_pnl": weekly_pnl,
            "weekly_loss_pct": weekly_loss_pct,
            "trading_enabled": emergency_shutdown.is_trading_allowed(),
        }


# Global module singleton
portfolio_monitor = PortfolioMonitor()
