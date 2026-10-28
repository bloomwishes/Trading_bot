"""
AutoTrader Pro - Emergency Shutdown Subsystem
=============================================
Provides circuit-breaker execution and emergency position liquidation.
When triggered by drawdown limits, loss streaks, or manual intervention,
it halts new order entry, cancels resting orders, and closes open positions.
"""

from __future__ import annotations

from typing import Dict, Any, Optional
from datetime import datetime, timezone

from backend.utils.logger import bot_logger


class EmergencyShutdown:
    """
    Emergency circuit breaker capable of halting all trading and
    liquidating open exposure across paper and live trading modes.
    """

    def __init__(self) -> None:
        self.trading_enabled: bool = True
        self.shutdown_triggered: bool = False
        self.last_shutdown_time: Optional[str] = None
        self.last_shutdown_reason: Optional[str] = None
        self.last_resume_time: Optional[str] = None

    def is_trading_allowed(self) -> bool:
        """Check if trading is currently permitted."""
        return self.trading_enabled and not self.shutdown_triggered

    def execute(self, reason: str, engine: Optional[Any] = None) -> Dict[str, Any]:
        """
        Execute emergency shutdown:
          1. Set global trading_enabled to False
          2. Cancel all open orders
          3. Close all open positions at market
          4. Pause engine / scheduler
          5. Log CRITICAL alert
        """
        self.trading_enabled = False
        self.shutdown_triggered = True
        self.last_shutdown_time = datetime.now(timezone.utc).isoformat()
        self.last_shutdown_reason = reason

        bot_logger.critical(
            f"🚨 EMERGENCY SHUTDOWN TRIGGERED: {reason}. Liquidating positions and halting operations."
        )

        closed_count = 0
        cancelled_orders = 0
        errors = []

        if engine:
            # 1. Stop engine
            try:
                if hasattr(engine, "stop"):
                    engine.stop()
            except Exception as e:
                errors.append(f"Engine stop error: {e}")

            # 2. Cancel all open live orders
            if hasattr(engine, "exchange_manager"):
                try:
                    open_orders = engine.exchange_manager.get_open_orders()
                    if isinstance(open_orders, list):
                        for o in open_orders:
                            oid = o.get("id") or o.get("order_id")
                            if oid:
                                try:
                                    engine.exchange_manager.cancel_order(oid)
                                    cancelled_orders += 1
                                except Exception as ce:
                                    errors.append(f"Cancel order {oid}: {ce}")
                except Exception as oe:
                    errors.append(f"Fetch open orders: {oe}")

            # 3. Close all open positions across DB, paper trader, and position tracker
            from backend.database import SessionLocal
            from backend.models import Trade

            db = SessionLocal()
            try:
                open_trades = db.query(Trade).filter(Trade.status == "OPEN").all()
                for trade in open_trades:
                    try:
                        ticker = None
                        if hasattr(engine, "exchange_manager"):
                            ticker = engine.exchange_manager.get_ticker(trade.pair)
                        price = 0.0
                        if isinstance(ticker, dict):
                            price = float(ticker.get("last_price", 0))
                        elif ticker:
                            price = float(ticker)
                        if price <= 0:
                            price = float(trade.entry_price or 1.0)

                        if hasattr(engine, "_close_trade_internal"):
                            engine._close_trade_internal(trade, price, f"EMERGENCY_SHUTDOWN: {reason}", db)
                        closed_count += 1
                    except Exception as te:
                        errors.append(f"Close trade #{trade.id}: {te}")
            except Exception as dbe:
                errors.append(f"DB close query: {dbe}")
            finally:
                db.close()

        result = {
            "status": "EMERGENCY_SHUTDOWN_ACTIVE",
            "trading_enabled": False,
            "reason": reason,
            "timestamp": self.last_shutdown_time,
            "closed_positions_count": closed_count,
            "cancelled_orders_count": cancelled_orders,
            "errors": errors,
        }
        bot_logger.critical(
            f"🚨 EMERGENCY SHUTDOWN COMPLETE: Closed {closed_count} position(s), "
            f"cancelled {cancelled_orders} order(s)."
        )
        return result

    def resume_trading(self, reason: str = "Manual operator review") -> Dict[str, Any]:
        """
        Re-enable trading following emergency shutdown or manual pause.
        """
        self.trading_enabled = True
        self.shutdown_triggered = False
        self.last_resume_time = datetime.now(timezone.utc).isoformat()

        bot_logger.info(
            f"✅ TRADING RESUMED by operator: {reason} at {self.last_resume_time}"
        )
        return {
            "status": "TRADING_RESUMED",
            "trading_enabled": True,
            "reason": reason,
            "timestamp": self.last_resume_time,
        }


# Global module singleton
emergency_shutdown = EmergencyShutdown()
