"""
AutoTrader Pro - APScheduler-based Task Scheduler
==================================================
Orchestrates all periodic jobs:
  1. main_cycle (60 s)    — run the full trading engine cycle.
  2. check_stops (30 s)   — monitor open trades for SL / TP / trailing.
  3. scan_opportunities (60 s) — scan all pairs for new opportunities.
  4. portfolio_snapshot (15 min) — record portfolio value to the DB.

Each job is wrapped in a try/except so a single failure never takes
down the scheduler. All errors are logged.
"""

import json
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from backend.config import settings
from backend.database import SessionLocal
from backend.models import BotLog, PortfolioSnapshot
from backend.utils.logger import bot_logger
from backend.utils.helpers import timestamp_now
from backend.engine.trading_engine import TradingEngine
from backend.scanner.opportunity_scanner import OpportunityScanner


class BotScheduler:
    """
    APScheduler-based orchestrator for all recurring bot tasks.

    Attributes:
        trading_engine (TradingEngine): The engine whose cycles we schedule.
        scanner (OpportunityScanner): The market scanner.
        scheduler (BackgroundScheduler): APScheduler instance.
    """

    def __init__(
        self,
        trading_engine: TradingEngine,
        scanner: OpportunityScanner,
    ):
        self.trading_engine = trading_engine
        self.scanner = scanner
        self.scheduler = BackgroundScheduler(
            timezone="Asia/Kolkata",
            job_defaults={
                "coalesce": True,       # Skip missed runs, don't stack up
                "max_instances": 1,     # One instance of each job at a time
                "misfire_grace_time": 30,
            },
        )

        self._paused: bool = False

        # Track last-run timestamps for status reporting
        self._last_run: Dict[str, Optional[str]] = {
            "main_cycle": None,
            "check_stops": None,
            "scan_opportunities": None,
            "portfolio_snapshot": None,
        }

        self._register_jobs()

    # ------------------------------------------------------------------
    # Job registration
    # ------------------------------------------------------------------
    def _register_jobs(self):
        """Add all periodic jobs to the scheduler."""
        self.scheduler.add_job(
            func=self._job_main_cycle,
            trigger=IntervalTrigger(seconds=30),
            id="main_cycle",
            name="Main Trading Cycle",
            replace_existing=True,
        )

        self.scheduler.add_job(
            func=self._job_check_stops,
            trigger=IntervalTrigger(seconds=10),
            id="check_stops",
            name="Check Stop-Loss / Take-Profit",
            replace_existing=True,
        )

        self.scheduler.add_job(
            func=self._job_scan_opportunities,
            trigger=IntervalTrigger(seconds=30),
            id="scan_opportunities",
            name="Opportunity Scanner",
            replace_existing=True,
        )

        self.scheduler.add_job(
            func=self._job_portfolio_snapshot,
            trigger=IntervalTrigger(minutes=15),
            id="portfolio_snapshot",
            name="Portfolio Snapshot",
            replace_existing=True,
        )

    # ------------------------------------------------------------------
    # Job implementations (each wrapped in try/except)
    # ------------------------------------------------------------------
    def _job_main_cycle(self):
        """Run the full trading engine cycle on watched pairs."""
        if self._paused:
            return
        try:
            pairs = self._get_watchlist()
            actions = self.trading_engine.run_cycle(pairs)
            self._last_run["main_cycle"] = timestamp_now()
            if actions:
                bot_logger.info(
                    f"[Scheduler] main_cycle: {len(actions)} actions executed"
                )
        except Exception as e:
            bot_logger.error(f"[Scheduler] main_cycle error: {e}")

    def _job_check_stops(self):
        """Check open trades for stop-loss / take-profit triggers."""
        if self._paused:
            return
        try:
            self.trading_engine.check_open_trades()
            self._last_run["check_stops"] = timestamp_now()
        except Exception as e:
            bot_logger.error(f"[Scheduler] check_stops error: {e}")

    def _job_scan_opportunities(self):
        """Scan the market for new opportunities."""
        if self._paused:
            return
        try:
            opportunities = self.scanner.scan_all_pairs()
            self._last_run["scan_opportunities"] = timestamp_now()
            if opportunities:
                bot_logger.info(
                    f"[Scheduler] scan_opportunities: "
                    f"found {len(opportunities)} opportunities, "
                    f"top score={opportunities[0]['score']}"
                )
        except Exception as e:
            bot_logger.error(f"[Scheduler] scan_opportunities error: {e}")

    def _job_portfolio_snapshot(self):
        """Take a portfolio value snapshot and save to the database."""
        if self._paused:
            return
        try:
            current_prices = self.trading_engine.exchange_manager.get_current_prices()
            portfolio_value = self.trading_engine.paper_trader.get_portfolio_value(current_prices)
            self._save_portfolio_snapshot(portfolio_value)
            self._last_run["portfolio_snapshot"] = timestamp_now()
            bot_logger.info(
                f"[Scheduler] portfolio_snapshot: ₹{portfolio_value:.2f}"
            )
        except Exception as e:
            bot_logger.error(
                f"[Scheduler] portfolio_snapshot error: {e}"
            )

    # ------------------------------------------------------------------
    # Portfolio snapshot persistence
    # ------------------------------------------------------------------
    def _save_portfolio_snapshot(self, value: float):
        """Write a portfolio snapshot to the database."""
        db = SessionLocal()
        try:
            cash = value
            positions = []
            try:
                if self.trading_engine.mode == "paper":
                    cash = self.trading_engine.paper_trader.get_balance()
                    positions = self.trading_engine.paper_trader.get_positions()
                else:
                    # Live balance fetching can be implemented or default to cash value
                    balance = self.trading_engine.exchange_manager.get_balances()
                    cash = float(balance.get("INR", {}).get("available", value))
            except Exception:
                pass

            snapshot = PortfolioSnapshot(
                total_value=value,
                cash=cash,
                positions_json=json.dumps(positions),
                paper_mode=(self.trading_engine.mode == "paper"),
                created_at=timestamp_now(),
            )
            db.add(snapshot)
            db.commit()
        except Exception as e:
            db.rollback()
            bot_logger.error(
                f"[Scheduler] Failed to save portfolio snapshot: {e}"
            )
        finally:
            db.close()

    # ------------------------------------------------------------------
    # Watchlist helper
    # ------------------------------------------------------------------
    @staticmethod
    def _get_watchlist():
        """Return the configured watchlist of trading pairs."""
        try:
            return getattr(settings, "WATCHED_PAIRS", [
                "BTC/INR", "ETH/INR", "SOL/INR", "XRP/INR", "DOGE/INR",
            ])
        except Exception:
            return ["BTC/INR", "ETH/INR"]

    # ------------------------------------------------------------------
    # Lifecycle controls
    # ------------------------------------------------------------------
    def start(self):
        """Start the scheduler (begins running all registered jobs)."""
        if not self.scheduler.running:
            self.scheduler.start()
            self._paused = False
            bot_logger.info("[Scheduler] STARTED — all jobs active")

    def stop(self):
        """Shut down the scheduler gracefully."""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            bot_logger.info("[Scheduler] STOPPED")

    def pause(self):
        """Pause all jobs without shutting down the scheduler."""
        self._paused = True
        # Pause each job individually in APScheduler
        for job in self.scheduler.get_jobs():
            job.pause()
        bot_logger.info("[Scheduler] PAUSED — all jobs suspended")

    def resume(self):
        """Resume all paused jobs."""
        self._paused = False
        for job in self.scheduler.get_jobs():
            job.resume()
        bot_logger.info("[Scheduler] RESUMED — all jobs active")

    # ------------------------------------------------------------------
    # Status / introspection
    # ------------------------------------------------------------------
    @property
    def is_running(self) -> bool:
        """Whether the scheduler is currently running."""
        return self.scheduler.running and not self._paused

    def get_status(self) -> Dict[str, Any]:
        """
        Return a status dict with scheduler state and job details.

        Returns:
            Dict with keys: running, paused, jobs (list), last_run_times.
        """
        jobs_info = []
        for job in self.scheduler.get_jobs():
            next_run = str(job.next_run_time) if job.next_run_time else None
            jobs_info.append({
                "id": job.id,
                "name": job.name,
                "next_run": next_run,
                "pending": job.pending,
            })

        return {
            "running": self.scheduler.running,
            "paused": self._paused,
            "jobs": jobs_info,
            "last_run_times": self._last_run.copy(),
            "trading_engine_status": self.trading_engine.get_status(),
        }
