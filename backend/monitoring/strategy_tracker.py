"""
AutoTrader Pro — Strategy Performance Tracker
=============================================
Rolling multi-window performance evaluator and degradation watchdog.
Maintains:
  - 100-trade & 30-trade rolling windows per strategy
  - Metrics: win_rate_100, win_rate_30, profit_factor, avg realized R:R, Sharpe, Max Drawdown
  - Degradation detection: win_rate_30 < win_rate_100 * 0.8 (20%+ collapse)
  - Auto-disable trigger: win_rate_30 < 0.35 OR profit_factor < 0.8
  - Closed-loop feedback: Dynamically computes strategy weights for SignalAggregator
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import numpy as np

from backend.models import Trade
from backend.monitoring.alert_manager import alert_manager
from backend.utils.logger import bot_logger


class StrategyPerformanceTracker:
    """
    Watches live and paper trade outcomes per strategy. Detects alpha decay
    and generates adaptive weightings for the SignalAggregator.
    """

    def __init__(self, engine: Optional[Any] = None) -> None:
        self.engine = engine
        self._trades_by_strategy: Dict[str, List[Trade]] = {}

        # Cache of strategy states
        self._strategy_states: Dict[str, Dict[str, Any]] = {}

    def set_engine(self, engine: Any) -> None:
        """Bind trading engine reference."""
        self.engine = engine

    def record_closed_trade(self, trade: Trade) -> Dict[str, Any]:
        """Record a closed trade and re-evaluate strategy health."""
        strat = trade.strategy or "manual"
        if strat not in self._trades_by_strategy:
            self._trades_by_strategy[strat] = []

        self._trades_by_strategy[strat].append(trade)
        return self.evaluate_strategy(strat)

    def sync_from_database(self, trades: List[Trade]) -> None:
        """Hydrate rolling history from past database trades."""
        self._trades_by_strategy.clear()
        for t in trades:
            if getattr(t, "status", "CLOSED").upper() == "CLOSED":
                strat = t.strategy or "manual"
                if strat not in self._trades_by_strategy:
                    self._trades_by_strategy[strat] = []
                self._trades_by_strategy[strat].append(t)

        for strat in self._trades_by_strategy:
            self.evaluate_strategy(strat)

    def evaluate_strategy(self, strategy_name: str) -> Dict[str, Any]:
        """
        Calculates rolling 100 and 30 trade metrics and assesses degradation.
        """
        all_trades = self._trades_by_strategy.get(strategy_name, [])
        if not all_trades:
            state = self._default_strategy_state(strategy_name)
            self._strategy_states[strategy_name] = state
            return state

        # Windows
        window_100 = all_trades[-100:]
        window_30 = all_trades[-30:]

        # Metrics for 100 window
        pnls_100 = [float(t.pnl or 0.0) for t in window_100]
        wins_100 = sum(1 for p in pnls_100 if p > 0)
        wr_100 = (wins_100 / len(window_100)) if window_100 else 0.0

        # Metrics for 30 window
        pnls_30 = [float(t.pnl or 0.0) for t in window_30]
        pnl_pcts_30 = [float(t.pnl_pct or 0.0) for t in window_30]
        wins_30 = sum(1 for p in pnls_30 if p > 0)
        losses_30 = sum(1 for p in pnls_30 if p < 0)
        wr_30 = (wins_30 / len(window_30)) if window_30 else 0.0

        gross_profit = sum(p for p in pnls_30 if p > 0)
        gross_loss = abs(sum(p for p in pnls_30 if p < 0))

        if gross_loss > 0:
            profit_factor = round(gross_profit / gross_loss, 2)
        elif gross_profit > 0:
            profit_factor = 99.0
        else:
            profit_factor = 0.0

        # Avg realized Risk:Reward (avg win / avg loss)
        avg_win = (gross_profit / wins_30) if wins_30 > 0 else 0.0
        avg_loss = (gross_loss / losses_30) if losses_30 > 0 else 0.0
        avg_rr = round(avg_win / avg_loss, 2) if avg_loss > 0 else (1.0 if avg_win > 0 else 0.0)

        # Sharpe over 30-trade window
        sharpe = 0.0
        if len(pnl_pcts_30) >= 2:
            arr = np.array(pnl_pcts_30) / 100.0
            std = np.std(arr, ddof=1)
            if std > 1e-8:
                sharpe = float((np.mean(arr) / std) * math.sqrt(365))

        # Max drawdown across 30 window
        max_dd_pct = 0.0
        cum = 0.0
        peak = 0.0
        for p in pnls_30:
            cum += p
            if cum > peak:
                peak = cum
            else:
                drop = peak - cum
                max_dd_pct = max(max_dd_pct, drop)

        # Degradation checks
        is_degraded = False
        auto_disabled = False

        sample_size = len(window_30)
        # Check degradation if we have at least 10 trades and a baseline
        if sample_size >= 10 and wr_100 > 0:
            if wr_30 < (wr_100 * 0.80):
                is_degraded = True

        # Check auto-disable condition
        if sample_size >= 10:
            if wr_30 < 0.35 or profit_factor < 0.80:
                auto_disabled = True

        state = {
            "strategy": strategy_name,
            "total_trades": len(all_trades),
            "sample_size_30": sample_size,
            "win_rate_100": round(wr_100, 3),
            "win_rate_30": round(wr_30, 3),
            "profit_factor": profit_factor,
            "avg_risk_reward": avg_rr,
            "sharpe_ratio": round(sharpe, 2),
            "max_drawdown_amount": round(max_dd_pct, 2),
            "is_degraded": is_degraded,
            "auto_disabled": auto_disabled,
            "status": "DISABLED" if auto_disabled else ("DEGRADED" if is_degraded else "HEALTHY"),
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
        }

        # Check if alert needs to be dispatched
        prev_state = self._strategy_states.get(strategy_name, {})
        if auto_disabled and not prev_state.get("auto_disabled", False):
            alert_manager.send_alert(
                event="STRATEGY_AUTO_DISABLED",
                message=(
                    f"Strategy '{strategy_name}' auto-disable threshold triggered! "
                    f"WinRate30={wr_30*100:.1f}%, ProfitFactor={profit_factor}. Suggest de-allocating."
                ),
                priority="HIGH",
                metadata=state,
            )
        elif is_degraded and not prev_state.get("is_degraded", False):
            alert_manager.send_alert(
                event="STRATEGY_DEGRADATION_DETECTED",
                message=(
                    f"Strategy '{strategy_name}' performance degraded: "
                    f"WinRate30 ({wr_30*100:.1f}%) < 80% of WinRate100 ({wr_100*100:.1f}%)."
                ),
                priority="HIGH",
                metadata=state,
            )

        self._strategy_states[strategy_name] = state
        self._sync_weights_to_engine()
        return state

    def get_strategy_report(self) -> Dict[str, Dict[str, Any]]:
        """Return states for all evaluated strategies."""
        return dict(self._strategy_states)

    def get_strategy_weights(self) -> Dict[str, float]:
        """
        Computes dynamic weights (0.0 to 1.0) for strategies based on health.
        - HEALTHY: 1.0
        - DEGRADED: 0.5
        - DISABLED: 0.0
        """
        weights = {}
        for strat, state in self._strategy_states.items():
            if state.get("auto_disabled", False):
                weights[strat] = 0.0
            elif state.get("is_degraded", False):
                weights[strat] = 0.5
            else:
                weights[strat] = 1.0
        return weights

    def _sync_weights_to_engine(self) -> None:
        """Update trading engine's strategy_performance for SignalAggregator."""
        if not self.engine:
            return

        weights = self.get_strategy_weights()
        if hasattr(self.engine, "strategy_performance"):
            for s, w in weights.items():
                self.engine.strategy_performance[s] = w

    @staticmethod
    def _default_strategy_state(strategy_name: str) -> Dict[str, Any]:
        """Default baseline state before trades occur."""
        return {
            "strategy": strategy_name,
            "total_trades": 0,
            "sample_size_30": 0,
            "win_rate_100": 0.50,
            "win_rate_30": 0.50,
            "profit_factor": 1.0,
            "avg_risk_reward": 1.5,
            "sharpe_ratio": 0.0,
            "max_drawdown_amount": 0.0,
            "is_degraded": False,
            "auto_disabled": False,
            "status": "HEALTHY",
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
        }


# Global Singleton
strategy_tracker = StrategyPerformanceTracker()
