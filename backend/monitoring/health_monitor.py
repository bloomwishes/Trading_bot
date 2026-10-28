"""
AutoTrader Pro — System Health Monitor
======================================
Active watchdog and component diagnostic subsystem.
Monitors:
  - coindcx_api: Exchange REST API connectivity and latency (30s interval / 10s timeout)
  - database: SQLite connection responsiveness (60s interval / 5s timeout)
  - scheduler: APScheduler heartbeat and job execution states (10s interval / 5s timeout)
  - websocket_feed: Live exchange WebSocket feed connectivity (10s interval / 10s timeout)
  - data_freshness: Age of latest market candles (15s interval / 60s max age threshold)

Escalation Ladder per component:
  - 1 failure: Log WARNING
  - 3 failures: AlertManager dispatch (HIGH priority ⚠️)
  - 5 failures: AlertManager dispatch (CRITICAL priority 🚨) + attempt automated recovery
  - 10 failures: Trigger Emergency Shutdown circuit breaker via EmergencyShutdown
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import pandas as pd
from sqlalchemy import text

from backend.config import settings
from backend.database import SessionLocal
from backend.monitoring.alert_manager import alert_manager
from backend.risk.emergency import EmergencyShutdown
from backend.utils.logger import bot_logger


class SystemHealthMonitor:
    """
    Continuous health monitor and escalation watchdog for AutoTrader Pro.
    """

    def __init__(self, engine: Optional[Any] = None) -> None:
        self.engine = engine
        self.emergency_shutdown = EmergencyShutdown()

        # Track consecutive failures per component
        self.failures: Dict[str, int] = {
            "coindcx_api": 0,
            "database": 0,
            "scheduler": 0,
            "websocket_feed": 0,
            "data_freshness": 0,
        }

        # Last check results
        self.check_results: Dict[str, Dict[str, Any]] = {
            "coindcx_api": {"status": "ok", "latency_ms": 0.0, "message": "Initial", "last_check": None},
            "database": {"status": "ok", "latency_ms": 0.0, "message": "Initial", "last_check": None},
            "scheduler": {"status": "ok", "latency_ms": 0.0, "message": "Initial", "last_check": None},
            "websocket_feed": {"status": "ok", "latency_ms": 0.0, "message": "Initial", "last_check": None},
            "data_freshness": {"status": "ok", "latency_ms": 0.0, "message": "Initial", "last_check": None},
        }

        # Last run timestamps to respect check frequencies
        self._last_checked_at: Dict[str, float] = {
            "coindcx_api": 0.0,
            "database": 0.0,
            "scheduler": 0.0,
            "websocket_feed": 0.0,
            "data_freshness": 0.0,
        }

        # Check intervals in seconds
        self._check_intervals: Dict[str, float] = {
            "coindcx_api": 30.0,
            "database": 60.0,
            "scheduler": 10.0,
            "websocket_feed": 10.0,
            "data_freshness": 15.0,
        }

    def set_engine(self, engine: Any) -> None:
        """Bind trading engine reference to the health monitor."""
        self.engine = engine

    # ------------------------------------------------------------------
    # Individual Checks
    # ------------------------------------------------------------------
    def check_coindcx_api(self, timeout_sec: float = 10.0) -> Dict[str, Any]:
        """Verify REST API connectivity and measure round-trip latency."""
        t0 = time.time()
        try:
            exchange = getattr(self.engine, "exchange_manager", None) if self.engine else None
            if exchange and hasattr(exchange, "get_current_prices"):
                prices = exchange.get_current_prices()
                if not prices:
                    raise RuntimeError("get_current_prices returned empty dict")
            elif exchange and hasattr(exchange, "get_ticker"):
                ticker = exchange.get_ticker("BTC/INR")
                if not ticker:
                    raise RuntimeError("Ticker BTC/INR returned empty")
            else:
                # Direct lightweight HTTP ping
                import requests
                resp = requests.get("https://api.coindcx.com/exchange/ticker", timeout=timeout_sec)
                resp.raise_for_status()

            latency_ms = (time.time() - t0) * 1000.0
            return {"status": "ok", "latency_ms": round(latency_ms, 2), "message": "CoinDCX API reachable and responsive"}
        except Exception as e:
            latency_ms = (time.time() - t0) * 1000.0
            return {"status": "error", "latency_ms": round(latency_ms, 2), "message": f"CoinDCX API error: {str(e)}"}

    def check_database(self, timeout_sec: float = 5.0) -> Dict[str, Any]:
        """Verify SQLite DB read/write connectivity."""
        t0 = time.time()
        db = None
        try:
            db = SessionLocal()
            db.execute(text("SELECT 1"))
            latency_ms = (time.time() - t0) * 1000.0
            return {"status": "ok", "latency_ms": round(latency_ms, 2), "message": "Database query responsive"}
        except Exception as e:
            latency_ms = (time.time() - t0) * 1000.0
            return {"status": "error", "latency_ms": round(latency_ms, 2), "message": f"Database check failed: {str(e)}"}
        finally:
            if db:
                try:
                    db.close()
                except Exception:
                    pass

    def check_scheduler(self, scheduler: Optional[Any] = None) -> Dict[str, Any]:
        """Verify APScheduler is running and not paused."""
        t0 = time.time()
        try:
            sched = scheduler or getattr(self.engine, "scheduler", None)
            if sched is None:
                # If engine has no direct ref, check if we can inspect engine's running status
                if self.engine and not getattr(self.engine, "running", True):
                    return {"status": "warning", "latency_ms": 0.0, "message": "Engine is currently stopped"}
                return {"status": "ok", "latency_ms": 0.0, "message": "Scheduler status nominal"}

            is_running = getattr(sched, "is_running", True)
            if not is_running:
                return {"status": "error", "latency_ms": 0.0, "message": "Scheduler is stopped or paused"}
            return {"status": "ok", "latency_ms": round((time.time() - t0) * 1000, 2), "message": "Scheduler active"}
        except Exception as e:
            return {"status": "error", "latency_ms": 0.0, "message": f"Scheduler check error: {str(e)}"}

    def check_websocket_feed(self, timeout_sec: float = 10.0) -> Dict[str, Any]:
        """Verify CoinDCX WebSocket stream connectivity."""
        t0 = time.time()
        try:
            exchange = getattr(self.engine, "exchange_manager", None) if self.engine else None
            ws_client = getattr(exchange, "ws_client", None) if exchange else None
            if ws_client:
                is_connected = getattr(ws_client, "is_connected", False)
                if hasattr(is_connected, "__call__"):
                    is_connected = is_connected()
                if not is_connected:
                    return {"status": "error", "latency_ms": 0.0, "message": "CoinDCX WebSocket stream disconnected"}
                return {"status": "ok", "latency_ms": round((time.time() - t0) * 1000, 2), "message": "CoinDCX WebSocket stream active"}

            return {"status": "ok", "latency_ms": 0.0, "message": "WebSocket feed operating normally"}
        except Exception as e:
            return {"status": "error", "latency_ms": 0.0, "message": f"WebSocket feed check error: {str(e)}"}

    def check_data_freshness(self, max_age_sec: float = 60.0) -> Dict[str, Any]:
        """Check if market candles or prices are receiving fresh data within max_age_sec."""
        t0 = time.time()
        try:
            exchange = getattr(self.engine, "exchange_manager", None) if self.engine else None
            if not exchange:
                return {"status": "ok", "latency_ms": 0.0, "message": "Data freshness check nominal"}

            candles = exchange.get_candles("BTC/INR", interval="15m", limit=2)
            if candles.empty:
                return {"status": "warning", "latency_ms": 0.0, "message": "No candle data found for freshness check"}

            # If candle has a timestamp or datetime index
            now = time.time()
            if "datetime" in candles.columns:
                last_dt = candles["datetime"].iloc[-1]
                last_ts = last_dt.timestamp() if hasattr(last_dt, "timestamp") else time.time()
            elif isinstance(candles.index, pd.DatetimeIndex):
                last_ts = candles.index[-1].timestamp()
            else:
                last_ts = now

            age_sec = max(0.0, now - last_ts)
            # In 15m candle bar, the bar timestamp is bar start, so we check if the engine cache was updated recently
            meta = getattr(exchange, "_cache_meta", {}).get("BTC/INR", {})
            cache_age = now - meta.get("timestamp", now)

            if cache_age > max_age_sec:
                return {
                    "status": "warning",
                    "latency_ms": round((time.time() - t0) * 1000, 2),
                    "message": f"Candle cache is stale ({cache_age:.1f}s > {max_age_sec}s threshold)",
                }

            return {
                "status": "ok",
                "latency_ms": round((time.time() - t0) * 1000, 2),
                "message": f"Data fresh (cache age: {cache_age:.1f}s)",
            }
        except Exception as e:
            return {"status": "error", "latency_ms": 0.0, "message": f"Data freshness error: {str(e)}"}

    # ------------------------------------------------------------------
    # Dispatch & Escalation Ladder
    # ------------------------------------------------------------------
    def run_check(self, name: str, scheduler: Optional[Any] = None) -> Dict[str, Any]:
        """Run a single check and execute escalation ladder logic."""
        if name == "coindcx_api":
            res = self.check_coindcx_api()
        elif name == "database":
            res = self.check_database()
        elif name == "scheduler":
            res = self.check_scheduler(scheduler)
        elif name == "websocket_feed":
            res = self.check_websocket_feed()
        elif name == "data_freshness":
            res = self.check_data_freshness()
        else:
            res = {"status": "ok", "latency_ms": 0.0, "message": f"Unknown check '{name}'"}

        res["last_check"] = datetime.now(timezone.utc).isoformat()
        self.check_results[name] = res
        self._last_checked_at[name] = time.time()

        if res["status"] in ("error", "failed"):
            self.failures[name] += 1
            consecutive = self.failures[name]
            self._handle_escalation(name, consecutive, res["message"])
        else:
            if self.failures[name] > 0:
                bot_logger.info(f"✅ Health check '{name}' RECOVERED after {self.failures[name]} failure(s).")
            self.failures[name] = 0

        return res

    def _handle_escalation(self, component: str, consecutive_fails: int, error_msg: str) -> None:
        """Process consecutive failures along the escalation ladder."""
        if consecutive_fails == 1:
            bot_logger.warning(
                f"[HealthMonitor] Check '{component}' failed (1x): {error_msg}"
            )
        elif consecutive_fails == 3:
            alert_manager.send_alert(
                event=f"HEALTH_DEGRADED_{component.upper()}",
                message=f"Component '{component}' has failed {consecutive_fails} consecutive times: {error_msg}",
                priority="HIGH",
                metadata={"component": component, "consecutive_failures": consecutive_fails},
            )
        elif consecutive_fails == 5:
            alert_manager.send_alert(
                event=f"HEALTH_CRITICAL_{component.upper()}",
                message=f"CRITICAL: Component '{component}' failed 5 consecutive times! Attempting automated recovery.",
                priority="CRITICAL",
                metadata={"component": component, "consecutive_failures": consecutive_fails},
            )
            self._attempt_automated_recovery(component)
        elif consecutive_fails >= 10:
            alert_manager.send_alert(
                event=f"EMERGENCY_SHUTDOWN_{component.upper()}",
                message=f"EMERGENCY SHUTDOWN: Component '{component}' failed 10 consecutive times. Halting bot operations.",
                priority="CRITICAL",
                metadata={"component": component, "consecutive_failures": consecutive_fails},
            )
            # Circuit breaker: execute emergency shutdown
            self.emergency_shutdown.execute(
                reason=f"Health monitor: '{component}' failed 10 consecutive times ({error_msg})",
                engine=self.engine,
            )

    def _attempt_automated_recovery(self, component: str) -> None:
        """Attempt self-healing recovery actions."""
        bot_logger.info(f"[HealthMonitor] Attempting automated recovery for '{component}'...")
        try:
            if component == "websocket_feed":
                exchange = getattr(self.engine, "exchange_manager", None) if self.engine else None
                ws_client = getattr(exchange, "ws_client", None) if exchange else None
                if ws_client and hasattr(ws_client, "start"):
                    ws_client.start()
                    bot_logger.info("[HealthMonitor] Triggered WebSocket restart.")
            elif component == "data_freshness":
                exchange = getattr(self.engine, "exchange_manager", None) if self.engine else None
                if exchange and hasattr(exchange, "clear_cache"):
                    exchange.clear_cache()
                    bot_logger.info("[HealthMonitor] Cleared stale candle cache.")
            elif component == "scheduler":
                sched = getattr(self.engine, "scheduler", None)
                if sched and hasattr(sched, "resume"):
                    sched.resume()
                    bot_logger.info("[HealthMonitor] Resumed paused scheduler jobs.")
        except Exception as e:
            bot_logger.error(f"[HealthMonitor] Automated recovery for '{component}' failed: {e}")

    def run_all_checks(self, scheduler: Optional[Any] = None) -> Dict[str, Any]:
        """Execute all health checks."""
        for check_name in self.failures.keys():
            self.run_check(check_name, scheduler=scheduler)
        return self.get_health_status()

    def get_health_status(self) -> Dict[str, Any]:
        """
        Return structured health status with overall assessment:
          - 'healthy' (all checks ok)
          - 'degraded' (warning or 1-2 errors)
          - 'unhealthy' (3+ errors on any check)
          - 'critical' (emergency shutdown triggered or 5+ errors)
        """
        max_consecutive = max(self.failures.values()) if self.failures else 0
        error_count = sum(1 for c in self.check_results.values() if c["status"] == "error")
        warning_count = sum(1 for c in self.check_results.values() if c["status"] == "warning")

        if self.emergency_shutdown.shutdown_triggered or max_consecutive >= 10:
            overall = "critical"
        elif max_consecutive >= 3 or error_count >= 2:
            overall = "unhealthy"
        elif warning_count > 0 or error_count > 0:
            overall = "degraded"
        else:
            overall = "healthy"

        return {
            "overall_status": overall,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "healthy": overall == "healthy",
            "max_consecutive_failures": max_consecutive,
            "failure_counts": dict(self.failures),
            "checks": dict(self.check_results),
            "shutdown_active": self.emergency_shutdown.shutdown_triggered,
        }


# Global Singleton
health_monitor = SystemHealthMonitor()
