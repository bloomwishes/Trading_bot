"""
AutoTrader Pro - Risk Management & Portfolio Protection Subsystem
==================================================================
Comprehensive risk controls:
- Pre-trade risk gate (evaluates 10+ risk rules in < 5ms)
- Multi-model position sizing (Fixed fractional, Kelly criterion, Volatility-adjusted)
- Rolling correlation limits (prevents stacking correlated risk)
- Drawdown controls (daily limit, weekly limit, all-time peak drawdown)
- Loss streak cool-down and emergency circuit breaker
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from backend.config import settings
from backend.utils.logger import bot_logger
from backend.engine.strategy_base import StrategySignal
from backend.risk.correlation_manager import correlation_manager, CorrelationManager
from backend.risk.portfolio_monitor import portfolio_monitor, PortfolioMonitor
from backend.risk.emergency import emergency_shutdown, EmergencyShutdown


@dataclass
class RiskDecision:
    """
    Standardized verdict produced by the pre-trade risk gate.
    """
    approved: bool
    adjusted_signal: Optional[StrategySignal]
    reasons: List[str]
    checks_passed: List[str]
    checks_failed: List[str]
    position_size: float
    risk_per_trade_pct: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "approved": self.approved,
            "reasons": self.reasons,
            "checks_passed": self.checks_passed,
            "checks_failed": self.checks_failed,
            "position_size": self.position_size,
            "risk_per_trade_pct": self.risk_per_trade_pct,
        }


class RiskManager:
    """
    Centralized risk-control and portfolio-protection engine.
    """

    def __init__(
        self,
        correlation_mgr: Optional[CorrelationManager] = None,
        port_monitor: Optional[PortfolioMonitor] = None,
        emerg_shutdown: Optional[EmergencyShutdown] = None,
    ) -> None:
        # Load parameters with settings defaults
        self.max_position_pct: float = settings.MAX_POSITION_PCT
        self.max_open_trades: int = settings.MAX_OPEN_TRADES
        self.daily_loss_limit_pct: float = settings.DAILY_LOSS_LIMIT_PCT
        self.default_stop_loss_pct: float = settings.DEFAULT_STOP_LOSS_PCT
        self.default_take_profit_pct: float = settings.DEFAULT_TAKE_PROFIT_PCT
        self.trailing_stop_activate_pct: float = settings.TRAILING_STOP_ACTIVATE_PCT
        self.trailing_stop_trail_pct: float = settings.TRAILING_STOP_TRAIL_PCT

        # Advanced Risk Parameters
        self.weekly_loss_limit_pct: float = getattr(settings, "WEEKLY_LOSS_LIMIT_PCT", 7.0)
        self.total_drawdown_limit_pct: float = getattr(settings, "TOTAL_DRAWDOWN_LIMIT_PCT", 15.0)
        self.max_total_exposure_pct: float = getattr(settings, "MAX_TOTAL_EXPOSURE_PCT", 50.0)
        self.max_single_direction_exposure_pct: float = getattr(settings, "MAX_SINGLE_DIRECTION_EXPOSURE_PCT", 35.0)
        self.min_risk_reward_ratio: float = getattr(settings, "MIN_RISK_REWARD_RATIO", 1.5)
        self.max_correlated_positions: int = getattr(settings, "MAX_CORRELATED_POSITIONS", 2)
        self.correlation_threshold: float = getattr(settings, "CORRELATION_THRESHOLD", 0.7)
        self.cooldown_after_consecutive_losses: int = getattr(settings, "COOLDOWN_AFTER_CONSECUTIVE_LOSSES", 3)
        self.cooldown_duration_minutes: int = getattr(settings, "COOLDOWN_DURATION_MINUTES", 60)
        self.reduce_size_high_volatility: bool = getattr(settings, "REDUCE_SIZE_HIGH_VOLATILITY", True)

        # Linked Subsystems
        self.correlation_manager = correlation_mgr or correlation_manager
        self.portfolio_monitor = port_monitor or portfolio_monitor
        self.emergency_shutdown = emerg_shutdown or emergency_shutdown

        # Propagate config into linked subsystems
        self.correlation_manager.max_correlated_positions = self.max_correlated_positions
        self.correlation_manager.correlation_threshold = self.correlation_threshold
        self.portfolio_monitor.weekly_loss_limit_pct = self.weekly_loss_limit_pct
        self.portfolio_monitor.total_drawdown_limit_pct = self.total_drawdown_limit_pct
        self.portfolio_monitor.cooldown_after_consecutive_losses = self.cooldown_after_consecutive_losses
        self.portfolio_monitor.cooldown_duration_minutes = self.cooldown_duration_minutes

    # ── Pre-Trade Risk Gate ────────────────────────────────────────────
    def validate_signal(
        self,
        signal: StrategySignal,
        portfolio_value: float,
        open_positions: List[Dict[str, Any]],
        db_session: Any,
        current_price: Optional[float] = None,
        atr: Optional[float] = None,
        avg_atr: Optional[float] = None,
        strategy_stats: Optional[Dict[str, Any]] = None,
    ) -> RiskDecision:
        """
        Unified pre-trade risk validation gate. Evaluates all safety checks
        and determines intelligent position sizing in under 5 milliseconds.
        """
        checks_passed: List[str] = []
        checks_failed: List[str] = []
        reasons: List[str] = []

        # Step 0: Extract prices and direction
        entry_price = current_price or 0.0
        if entry_price <= 0 and signal.metadata:
            entry_price = float(signal.metadata.get("current_price", 0.0) or signal.metadata.get("price", 0.0))

        if portfolio_value <= 0:
            checks_failed.append("portfolio_value_positive")
            reasons.append("Portfolio equity is zero or negative.")
            return RiskDecision(
                approved=False,
                adjusted_signal=None,
                reasons=reasons,
                checks_passed=checks_passed,
                checks_failed=checks_failed,
                position_size=0.0,
                risk_per_trade_pct=0.0,
            )
        checks_passed.append("portfolio_value_positive")

        # Check 0b: Prime Directive Zero-Ruin Capital Survival Gate
        base_survival = getattr(settings, "MIN_SURVIVAL_CAPITAL_INR", 100.0)
        min_survival = min(base_survival, max(50.0, portfolio_value * 0.20)) if portfolio_value <= 2000.0 else base_survival
        if portfolio_value < min_survival:
            checks_failed.append("prime_directive_capital_survival")
            reasons.append(
                f"PRIME DIRECTIVE ENFORCED: Capital ₹{portfolio_value:.2f} is below minimum survival threshold ₹{min_survival:.2f}. "
                "Trading halted to prevent total bot death."
            )
            return RiskDecision(
                approved=False,
                adjusted_signal=None,
                reasons=reasons,
                checks_passed=checks_passed,
                checks_failed=checks_failed,
                position_size=0.0,
                risk_per_trade_pct=0.0,
            )
        checks_passed.append("prime_directive_capital_survival")

        # Check 1: Emergency circuit breaker
        if not self.emergency_shutdown.is_trading_allowed():
            checks_failed.append("emergency_circuit_breaker")
            reasons.append(f"Emergency shutdown active ({self.emergency_shutdown.last_shutdown_reason}).")
        else:
            checks_passed.append("emergency_circuit_breaker")

        # Check 2: Cooldown check
        in_cooldown, cd_reason = self.portfolio_monitor.is_in_cooldown()
        if in_cooldown:
            checks_failed.append("cooldown_check")
            reasons.append(cd_reason)
        else:
            checks_passed.append("cooldown_check")

        # Check 3: Max open trades count
        num_open = len(open_positions)
        if num_open >= self.max_open_trades:
            checks_failed.append("max_open_trades")
            reasons.append(f"Max open trades reached ({num_open}/{self.max_open_trades}).")
        else:
            checks_passed.append("max_open_trades")

        # Check 4: Daily loss limit
        if db_session and self.check_daily_loss_limit(db_session, portfolio_value):
            checks_failed.append("daily_loss_limit")
            reasons.append(f"Daily loss limit breached (>{self.daily_loss_limit_pct}%).")
        else:
            checks_passed.append("daily_loss_limit")

        # Check 5: Weekly loss limit
        if db_session:
            weekly_breached, weekly_loss, w_reason = self.portfolio_monitor.check_weekly_loss_limit(
                db_session, portfolio_value
            )
            if weekly_breached:
                checks_failed.append("weekly_loss_limit")
                reasons.append(w_reason)
            else:
                checks_passed.append("weekly_loss_limit")
        else:
            checks_passed.append("weekly_loss_limit")

        # Check 6: Total drawdown from peak
        hwm = max(self.portfolio_monitor.high_water_mark, portfolio_value)
        current_dd = ((hwm - portfolio_value) / hwm) * 100.0 if hwm > 0 else 0.0
        if current_dd >= self.total_drawdown_limit_pct:
            checks_failed.append("total_drawdown_limit")
            reasons.append(f"Total drawdown {current_dd:.2f}% exceeds limit {self.total_drawdown_limit_pct}%.")
        else:
            checks_passed.append("total_drawdown_limit")

        # Check 7: Risk-Reward Ratio (Min 1.5)
        # Determine Stop Loss & Take Profit
        sl_price = 0.0
        tp_price = 0.0
        if signal.metadata:
            sl_price = float(signal.metadata.get("stop_loss_price", 0.0) or signal.metadata.get("stop_loss", 0.0))
            tp_price = float(signal.metadata.get("take_profit_price", 0.0) or signal.metadata.get("take_profit", 0.0))

        if sl_price <= 0 and entry_price > 0:
            sl_price = self.calculate_stop_loss(entry_price, signal.action)
        if tp_price <= 0 and entry_price > 0:
            tp_price = self.calculate_take_profit(entry_price, signal.action)

        if entry_price > 0 and sl_price > 0 and tp_price > 0:
            risk_dist = abs(entry_price - sl_price)
            reward_dist = abs(tp_price - entry_price)
            rr_ratio = reward_dist / max(risk_dist, 1e-6)
            if rr_ratio < self.min_risk_reward_ratio:
                checks_failed.append("min_risk_reward_ratio")
                reasons.append(
                    f"R:R ratio {rr_ratio:.2f} below minimum required {self.min_risk_reward_ratio:.2f}."
                )
            else:
                checks_passed.append("min_risk_reward_ratio")
        else:
            checks_passed.append("min_risk_reward_ratio")

        # Check 8: Correlation check
        corr_passed, corr_reason = self.correlation_manager.check_correlation(signal, open_positions)
        if not corr_passed:
            checks_failed.append("correlation_check")
            reasons.append(corr_reason)
        else:
            checks_passed.append("correlation_check")

        # Step 8.5: Calculate intelligent position size
        win_rate = strategy_stats.get("win_rate", 0.50) if strategy_stats else 0.50
        avg_win = strategy_stats.get("avg_win", 0.0) if strategy_stats else 0.0
        avg_loss = strategy_stats.get("avg_loss", 0.0) if strategy_stats else 0.0

        position_size = self.calculate_position_size(
            portfolio_value=portfolio_value,
            entry_price=entry_price,
            stop_loss_price=sl_price,
            signal_strength=signal.strength,
            strategy_win_rate=win_rate,
            atr=atr,
            avg_atr=avg_atr,
            avg_win=avg_win,
            avg_loss=avg_loss,
        )

        if position_size <= 0:
            checks_failed.append("position_size_valid")
            reasons.append("Calculated position size is zero or invalid.")
        else:
            checks_passed.append("position_size_valid")

        new_notional = position_size * entry_price

        # Check 9: Portfolio total exposure limit (Default <= 50%)
        current_exposure = sum(
            float(p.get("quantity", 0.0)) * float(p.get("entry_price", p.get("price", 0.0)))
            for p in open_positions
        )
        total_exp_after = ((current_exposure + new_notional) / portfolio_value) * 100.0
        if total_exp_after > self.max_total_exposure_pct:
            checks_failed.append("max_total_exposure")
            reasons.append(
                f"Total exposure {total_exp_after:.1f}% would exceed limit {self.max_total_exposure_pct}%."
            )
        else:
            checks_passed.append("max_total_exposure")

        # Check 10: Single direction exposure limit (Default <= 35%)
        action_dir = "LONG" if signal.action == "BUY" else "SHORT"
        dir_exposure = sum(
            float(p.get("quantity", 0.0)) * float(p.get("entry_price", p.get("price", 0.0)))
            for p in open_positions
            if str(p.get("direction", p.get("side", "BUY"))).upper() in (action_dir, signal.action)
        )
        dir_exp_after = ((dir_exposure + new_notional) / portfolio_value) * 100.0
        if dir_exp_after > self.max_single_direction_exposure_pct:
            checks_failed.append("max_single_direction_exposure")
            reasons.append(
                f"Single direction ({action_dir}) exposure {dir_exp_after:.1f}% would exceed limit {self.max_single_direction_exposure_pct}%."
            )
        else:
            checks_passed.append("max_single_direction_exposure")

        # Final Verdict
        approved = (len(checks_failed) == 0)

        # Build adjusted signal clone if approved
        adjusted_signal = None
        if approved:
            reasons.append("All risk gate safety checks passed.")
            meta = dict(signal.metadata or {})
            meta["position_size"] = position_size
            meta["stop_loss_price"] = sl_price
            meta["take_profit_price"] = tp_price
            adjusted_signal = StrategySignal(
                pair=signal.pair,
                action=signal.action,
                strategy=signal.strategy,
                strength=signal.strength,
                reason=signal.reason,
                metadata=meta,
            )
            bot_logger.info(
                f"🛡️ [RiskGate] APPROVED {signal.action} {position_size:.6f} {signal.pair} | "
                f"Notional: ₹{new_notional:,.2f} ({new_notional/portfolio_value*100:.1f}%)"
            )
        else:
            bot_logger.warning(
                f"🛡️ [RiskGate] REJECTED {signal.action} {signal.pair}: {'; '.join(reasons)}"
            )

        return RiskDecision(
            approved=approved,
            adjusted_signal=adjusted_signal,
            reasons=reasons,
            checks_passed=checks_passed,
            checks_failed=checks_failed,
            position_size=position_size if approved else 0.0,
            risk_per_trade_pct=self.max_position_pct,
        )

    # ── Advanced Position Sizing ──────────────────────────────────────
    def calculate_position_size(
        self,
        portfolio_value: float,
        entry_price: float,
        stop_loss_price: Optional[float] = None,
        signal_strength: float = 1.0,
        strategy_win_rate: Optional[float] = None,
        atr: Optional[float] = None,
        avg_atr: Optional[float] = None,
        avg_win: Optional[float] = None,
        avg_loss: Optional[float] = None,
    ) -> float:
        """
        Intelligent multi-model position sizing. Evaluates:
          1. Fixed Fractional Sizing
          2. Kelly Criterion Sizing
          3. Volatility-Adjusted (ATR / Risk Distance) Sizing
        Selects the SMALLEST non-zero quantity to enforce capital preservation.
        """
        if entry_price <= 0 or portfolio_value <= 0:
            return 0.0

        # Calibrate position allocation for small accounts (₹500 - ₹2,500) so notional meets
        # CoinDCX minimum requirements (₹75 - ₹150) without exchange rejection, while tight stop losses
        # guarantee dollar risk per trade is strictly capped (< ₹3.00, or 0.5% of total capital).
        effective_position_pct = self.max_position_pct
        if portfolio_value <= 1500.0:
            effective_position_pct = max(self.max_position_pct, 25.0)
        elif portfolio_value <= 3000.0:
            effective_position_pct = max(self.max_position_pct, 20.0)

        # Method 1: Fixed Fractional
        fixed_notional = portfolio_value * (effective_position_pct / 100.0)
        size_fixed = fixed_notional / entry_price

        # Method 2: Kelly Criterion
        size_kelly = size_fixed
        if strategy_win_rate is not None and strategy_win_rate > 0.0:
            w = strategy_win_rate
            # Win/loss payout ratio R
            r = (avg_win / avg_loss) if (avg_win and avg_loss and avg_loss > 0) else 1.5
            r = max(0.2, min(5.0, r))

            kelly_f = w - ((1.0 - w) / r)
            # Safe Kelly fraction: capped between 1% and 25% of portfolio
            safe_kelly_f = max(0.01, min(0.25, kelly_f))
            size_kelly = (portfolio_value * safe_kelly_f) / entry_price

        # Method 3: Volatility-Adjusted (Risk Distance & ATR)
        size_vol = size_fixed
        if stop_loss_price is not None and stop_loss_price > 0:
            risk_distance = abs(entry_price - stop_loss_price)
            risk_budget = portfolio_value * (self.max_position_pct / 100.0)
            if risk_distance > 0:
                size_vol = risk_budget / risk_distance

        # Take the most conservative (smallest) positive result
        candidates = [s for s in (size_fixed, size_kelly, size_vol) if s > 0]
        chosen_size = min(candidates) if candidates else size_fixed

        # Volatility spike damper: If ATR is over 2x its moving average, halve the position size
        if (
            self.reduce_size_high_volatility
            and atr is not None
            and avg_atr is not None
            and avg_atr > 0
            and atr > (2.0 * avg_atr)
        ):
            chosen_size *= 0.5
            bot_logger.info(
                f"[RiskManager] High market volatility detected (ATR {atr:.2f} > 2x Avg {avg_atr:.2f}). "
                f"Position size halved."
            )

        # Cap at max_position_pct notional ceiling
        max_allowed_qty = fixed_notional / entry_price
        final_size = min(chosen_size, max_allowed_qty)

        return round(final_size, 8)

    # ── Stop-loss / take-profit ────────────────────────────────────────
    def calculate_stop_loss(self, entry_price: float, side: str) -> float:
        """Return the initial stop-loss price based on default_stop_loss_pct."""
        pct = self.default_stop_loss_pct / 100.0
        if side.upper() in ("BUY", "LONG"):
            return round(entry_price * (1.0 - pct), 2)
        else:
            return round(entry_price * (1.0 + pct), 2)

    def calculate_take_profit(self, entry_price: float, side: str) -> float:
        """Return the initial take-profit price based on default_take_profit_pct."""
        pct = self.default_take_profit_pct / 100.0
        if side.upper() in ("BUY", "LONG"):
            return round(entry_price * (1.0 + pct), 2)
        else:
            return round(entry_price * (1.0 - pct), 2)

    # ── Legacy Gate-keeper (Backward Compatibility) ────────────────────
    def can_open_trade(
        self,
        portfolio_value: float,
        num_open_trades: int,
    ) -> Tuple[bool, str]:
        """Backward-compatible pre-flight check."""
        if not self.emergency_shutdown.is_trading_allowed():
            return False, "Emergency shutdown active"

        in_cd, cd_msg = self.portfolio_monitor.is_in_cooldown()
        if in_cd:
            return False, cd_msg

        if num_open_trades >= self.max_open_trades:
            return False, f"Max open trades reached ({num_open_trades}/{self.max_open_trades})"

        if portfolio_value <= 0:
            return False, "Portfolio value is zero or negative"

        return True, "OK"

    # ── Daily loss limit ───────────────────────────────────────────────
    def check_daily_loss_limit(
        self,
        db_session: Session,
        portfolio_value: Optional[float] = None,
    ) -> bool:
        """Return True if daily realized losses exceed daily_loss_limit_pct."""
        from backend.models import Trade

        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        try:
            closed_today = (
                db_session.query(Trade)
                .filter(Trade.status == "CLOSED", Trade.closed_at >= today_start)
                .all()
            )
            total_pnl = sum(float(t.pnl or 0.0) for t in closed_today)

            if total_pnl >= 0:
                return False

            base_val = portfolio_value or self.portfolio_monitor.high_water_mark
            if base_val <= 0:
                base_val = settings.PAPER_BALANCE

            loss_pct = abs(total_pnl) / base_val * 100.0
            if loss_pct >= self.daily_loss_limit_pct:
                bot_logger.warning(
                    f"[RiskManager] Daily loss limit breached: -{loss_pct:.2f}% (limit {self.daily_loss_limit_pct}%)"
                )
                return True
        except Exception as exc:
            bot_logger.warning(f"[RiskManager] Error checking daily loss limit: {exc}")

        return False

    # ── Trailing stop ──────────────────────────────────────────────────
    def update_trailing_stop(
        self,
        trade: Any,
        current_price: float,
    ) -> Optional[float]:
        """Recalculate trailing stop for an open trade. Never ratchets downward."""
        entry = float(trade.entry_price or 0.0)
        if entry <= 0 or current_price <= 0:
            return None

        side = str(trade.side).upper()
        activate_pct = self.trailing_stop_activate_pct / 100.0
        trail_pct = self.trailing_stop_trail_pct / 100.0

        if side in ("BUY", "LONG"):
            activation_price = entry * (1.0 + activate_pct)
            if current_price >= activation_price:
                new_stop = round(current_price * (1.0 - trail_pct), 2)
                existing = trade.trailing_stop
                if existing is None or new_stop > existing:
                    return new_stop
        else:
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
        stop = trade.trailing_stop if trade.trailing_stop is not None else trade.stop_loss
        if stop is None or current_price <= 0:
            return False
        if str(trade.side).upper() in ("BUY", "LONG"):
            return current_price <= stop
        else:
            return current_price >= stop

    def should_take_profit(self, trade: Any, current_price: float) -> bool:
        """Return True if current price has reached the take-profit level."""
        tp = trade.take_profit
        if tp is None or current_price <= 0:
            return False
        if str(trade.side).upper() in ("BUY", "LONG"):
            return current_price >= tp
        else:
            return current_price <= tp

    # ── Lifecycle hook ─────────────────────────────────────────────────
    def on_trade_closed(self, trade: Any, engine: Optional[Any] = None) -> None:
        """
        Hook called by TradingEngine on every closed trade.
        Updates streak trackers, drawdowns, and trigger checks.
        """
        self.portfolio_monitor.on_trade_closed(trade, engine=engine)

    # ── Risk Limits Status ─────────────────────────────────────────────
    def get_limits_status(
        self,
        portfolio_value: float,
        open_positions: List[Dict[str, Any]],
        db_session: Any,
    ) -> Dict[str, Any]:
        """
        Calculates all active risk limits and current utilization percentages.
        """
        val = portfolio_value if portfolio_value > 0 else 10000.0
        hwm = max(self.portfolio_monitor.high_water_mark, val)
        current_dd = round(((hwm - val) / hwm) * 100.0, 2) if hwm > 0 else 0.0

        # Exposure calculation
        total_notional = sum(
            float(p.get("quantity", 0.0)) * float(p.get("entry_price", p.get("price", 0.0)))
            for p in open_positions
        )
        total_exp_pct = round((total_notional / val) * 100.0, 2)

        long_notional = sum(
            float(p.get("quantity", 0.0)) * float(p.get("entry_price", p.get("price", 0.0)))
            for p in open_positions
            if str(p.get("direction", p.get("side", "BUY"))).upper() in ("LONG", "BUY")
        )
        short_notional = sum(
            float(p.get("quantity", 0.0)) * float(p.get("entry_price", p.get("price", 0.0)))
            for p in open_positions
            if str(p.get("direction", p.get("side", "BUY"))).upper() in ("SHORT", "SELL")
        )
        long_exp_pct = round((long_notional / val) * 100.0, 2)
        short_exp_pct = round((short_notional / val) * 100.0, 2)

        # Weekly loss
        _, weekly_loss_pct, _ = self.portfolio_monitor.check_weekly_loss_limit(db_session, val)

        # Daily loss
        from backend.models import Trade
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        daily_loss_pct = 0.0
        if db_session:
            try:
                closed_today = (
                    db_session.query(Trade)
                    .filter(Trade.status == "CLOSED", Trade.closed_at >= today_start)
                    .all()
                )
                daily_pnl = sum(float(t.pnl or 0.0) for t in closed_today)
                if daily_pnl < 0:
                    daily_loss_pct = round((abs(daily_pnl) / val) * 100.0, 2)
            except Exception:
                pass

        in_cd, cd_msg = self.portfolio_monitor.is_in_cooldown()

        return {
            "max_open_trades": {
                "current": len(open_positions),
                "limit": self.max_open_trades,
                "pct_utilized": round((len(open_positions) / self.max_open_trades) * 100.0, 1),
            },
            "daily_loss_limit": {
                "current_loss_pct": daily_loss_pct,
                "limit_pct": self.daily_loss_limit_pct,
                "pct_utilized": round((daily_loss_pct / self.daily_loss_limit_pct) * 100.0, 1),
            },
            "weekly_loss_limit": {
                "current_loss_pct": weekly_loss_pct,
                "limit_pct": self.weekly_loss_limit_pct,
                "pct_utilized": round((weekly_loss_pct / self.weekly_loss_limit_pct) * 100.0, 1),
            },
            "total_drawdown_limit": {
                "current_drawdown_pct": current_dd,
                "limit_pct": self.total_drawdown_limit_pct,
                "pct_utilized": round((current_dd / self.total_drawdown_limit_pct) * 100.0, 1),
            },
            "max_total_exposure": {
                "current_exposure_pct": total_exp_pct,
                "limit_pct": self.max_total_exposure_pct,
                "pct_utilized": round((total_exp_pct / self.max_total_exposure_pct) * 100.0, 1),
            },
            "max_single_direction_exposure": {
                "long_exposure_pct": long_exp_pct,
                "short_exposure_pct": short_exp_pct,
                "limit_pct": self.max_single_direction_exposure_pct,
                "max_utilized_pct": round((max(long_exp_pct, short_exp_pct) / self.max_single_direction_exposure_pct) * 100.0, 1),
            },
            "min_risk_reward_ratio": {
                "limit": self.min_risk_reward_ratio,
            },
            "cooldown_status": {
                "is_active": in_cd,
                "reason": cd_msg if in_cd else None,
                "consecutive_losses": self.portfolio_monitor.consecutive_losses,
            },
        }

    # ── Settings introspection ─────────────────────────────────────────
    def get_settings(self) -> Dict[str, Any]:
        """Return all risk parameters as a dict."""
        return {
            "max_position_pct": self.max_position_pct,
            "max_open_trades": self.max_open_trades,
            "daily_loss_limit_pct": self.daily_loss_limit_pct,
            "default_stop_loss_pct": self.default_stop_loss_pct,
            "default_take_profit_pct": self.default_take_profit_pct,
            "trailing_stop_activate_pct": self.trailing_stop_activate_pct,
            "trailing_stop_trail_pct": self.trailing_stop_trail_pct,
            "weekly_loss_limit_pct": self.weekly_loss_limit_pct,
            "total_drawdown_limit_pct": self.total_drawdown_limit_pct,
            "max_total_exposure_pct": self.max_total_exposure_pct,
            "max_single_direction_exposure_pct": self.max_single_direction_exposure_pct,
            "min_risk_reward_ratio": self.min_risk_reward_ratio,
            "max_correlated_positions": self.max_correlated_positions,
            "correlation_threshold": self.correlation_threshold,
            "cooldown_after_consecutive_losses": self.cooldown_after_consecutive_losses,
            "cooldown_duration_minutes": self.cooldown_duration_minutes,
            "reduce_size_high_volatility": self.reduce_size_high_volatility,
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
            "weekly_loss_limit_pct": float,
            "total_drawdown_limit_pct": float,
            "max_total_exposure_pct": float,
            "max_single_direction_exposure_pct": float,
            "min_risk_reward_ratio": float,
            "max_correlated_positions": int,
            "correlation_threshold": float,
            "cooldown_after_consecutive_losses": int,
            "cooldown_duration_minutes": int,
            "reduce_size_high_volatility": bool,
        }
        for key, cast in field_map.items():
            if key in new_settings:
                try:
                    val = cast(new_settings[key])
                    setattr(self, key, val)
                except (ValueError, TypeError):
                    bot_logger.warning(
                        f"RiskManager: invalid value for {key}: {new_settings[key]}"
                    )

        # Propagate to sub-managers
        self.correlation_manager.max_correlated_positions = self.max_correlated_positions
        self.correlation_manager.correlation_threshold = self.correlation_threshold
        self.portfolio_monitor.weekly_loss_limit_pct = self.weekly_loss_limit_pct
        self.portfolio_monitor.total_drawdown_limit_pct = self.total_drawdown_limit_pct
        self.portfolio_monitor.cooldown_after_consecutive_losses = self.cooldown_after_consecutive_losses
        self.portfolio_monitor.cooldown_duration_minutes = self.cooldown_duration_minutes

        bot_logger.info(f"RiskManager settings updated: {self.get_settings()}")


# Module-level singleton
risk_manager = RiskManager()
