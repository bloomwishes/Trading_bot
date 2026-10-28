"""
AutoTrader Pro - Signal Aggregator
==================================
Sits between strategy output and trade execution.
Provides multi-strategy signal aggregation, conflict resolution,
regime-fit scoring, win-rate ranking, and time-based throttling.
"""

from __future__ import annotations

import time
from typing import Dict, List, Optional, Any

from backend.engine.strategy_base import StrategySignal
from backend.utils.logger import bot_logger


# Default regime fit score mapping per strategy category / name
REGIME_FIT_TABLE: Dict[str, Dict[str, float]] = {
    # Trend Following
    "MA_Pullback": {
        "TRENDING_UP": 1.0,
        "TRENDING_DOWN": 1.0,
        "RANGING": 0.3,
        "HIGH_VOLATILITY": 0.6,
        "NEUTRAL": 0.7,
    },
    # Mean Reversion
    "Mean_Reversion": {
        "RANGING": 1.0,
        "TRENDING_UP": 0.2,
        "TRENDING_DOWN": 0.2,
        "HIGH_VOLATILITY": 0.4,
        "NEUTRAL": 0.8,
    },
    # Breakout Hunter
    "Breakout_Hunter": {
        "HIGH_VOLATILITY": 1.0,
        "TRENDING_UP": 0.9,
        "TRENDING_DOWN": 0.9,
        "NEUTRAL": 0.8,
        "RANGING": 0.4,
    },
    # Scalping
    "Scalping": {
        "HIGH_VOLATILITY": 1.0,
        "RANGING": 0.8,
        "NEUTRAL": 0.7,
        "TRENDING_UP": 0.5,
        "TRENDING_DOWN": 0.5,
    },
    # Grid Trading
    "Grid_Trading": {
        "RANGING": 1.0,
        "TRENDING_UP": 0.0,
        "TRENDING_DOWN": 0.0,
        "HIGH_VOLATILITY": 0.2,
        "NEUTRAL": 0.5,
    },
    # Statistical Arbitrage
    "Statistical_Arbitrage": {
        "RANGING": 1.0,
        "NEUTRAL": 0.8,
        "HIGH_VOLATILITY": 0.6,
        "TRENDING_UP": 0.5,
        "TRENDING_DOWN": 0.5,
    },
    "Stat_Arb": {
        "RANGING": 1.0,
        "NEUTRAL": 0.8,
        "HIGH_VOLATILITY": 0.6,
        "TRENDING_UP": 0.5,
        "TRENDING_DOWN": 0.5,
    },
    # RSI Divergence
    "RSI_Divergence": {
        "RANGING": 0.9,
        "NEUTRAL": 0.8,
        "TRENDING_UP": 0.7,
        "TRENDING_DOWN": 0.7,
        "HIGH_VOLATILITY": 0.5,
    },
    # Price Action
    "Price_Action": {
        "TRENDING_UP": 0.9,
        "TRENDING_DOWN": 0.9,
        "RANGING": 0.8,
        "NEUTRAL": 0.7,
        "HIGH_VOLATILITY": 0.6,
    },
    # Sentiment LLM
    "Sentiment_LLM": {
        "TRENDING_UP": 0.8,
        "TRENDING_DOWN": 0.8,
        "RANGING": 0.8,
        "NEUTRAL": 0.8,
        "HIGH_VOLATILITY": 0.7,
    },
}

DEFAULT_MIN_STRENGTH: float = 0.45
DEFAULT_THROTTLE_WINDOW_SEC: int = 300  # 5 minutes


class SignalAggregator:
    """
    Consolidates, filters, resolves conflicts, and ranks signals from multiple strategies.

    Attributes:
        min_strength (float): Minimum confidence threshold (default 0.45).
        throttle_seconds (int): Minimum interval between accepted signals per pair (default 300s).
    """

    def __init__(
        self,
        min_strength: float = DEFAULT_MIN_STRENGTH,
        throttle_seconds: int = DEFAULT_THROTTLE_WINDOW_SEC,
    ) -> None:
        """Initialize the signal aggregator with configuration and throttle tracking."""
        self.min_strength = float(min_strength)
        self.throttle_seconds = int(throttle_seconds)
        self._last_signal_time: Dict[str, float] = {}

    def reset_throttle(self, pair: Optional[str] = None) -> None:
        """Clear throttling history for a specific pair or all pairs."""
        if pair:
            self._last_signal_time.pop(pair, None)
        else:
            self._last_signal_time.clear()

    def get_regime_fit_score(self, strategy_name: str, regime: str) -> float:
        """
        Calculate regime fit multiplier for a strategy.
        Neural Network strategies are regime-agnostic (0.8x base, trusts own patterns).
        """
        regime_upper = (regime or "NEUTRAL").upper()

        # Neural Network models are regime-agnostic
        if strategy_name.startswith("Neural_Network"):
            return 0.8

        strat_table = REGIME_FIT_TABLE.get(strategy_name)
        if strat_table:
            return strat_table.get(regime_upper, 0.7)

        # Fallback default
        return 0.7

    def aggregate(
        self,
        signals: List[StrategySignal],
        regime: str = "NEUTRAL",
        win_rates: Optional[Dict[str, float]] = None,
        pair_regimes: Optional[Dict[str, str]] = None,
        enforce_throttle: bool = True,
    ) -> List[StrategySignal]:
        """
        Filter, deconflict, regime-weight, and rank candidate signals.

        Steps:
          1. Discard signals with strength < 0.45 (or min_strength).
          2. Group signals by trading pair.
          3. Resolve conflicts:
             - If a pair has both BUY and SELL signals:
               * Compute sum of confidence scores for BUY and SELL.
               * Keep direction only if cumulative confidence is > 2x the other.
               * If neither dominates, discard all signals for that pair.
          4. Score with regime fit:
             - Multiply signal strength by regime_fit_score.
          5. Rank:
             - Sort remaining signals by (adjusted_strength * strategy_historical_win_rate).
          6. Throttle:
             - Discard if less than 5 minutes since last accepted signal for that pair.
          7. Output:
             - Return top-ranked signal per pair.

        Args:
            signals: Raw signals generated by active strategies.
            regime: Global or fallback market regime string (e.g. 'RANGING', 'TRENDING_UP').
            win_rates: Optional map of strategy name -> historical win rate (0.0 to 1.0).
            pair_regimes: Optional pair-specific regime map {pair: regime}.
            enforce_throttle: Whether to enforce the 5-minute per-pair throttle.

        Returns:
            List of aggregated, top-ranked StrategySignal instances (at most 1 per pair).
        """
        if not signals:
            return []

        rates = win_rates or {}
        now = time.time()

        # ── Step 1: Filter signals below minimum strength ──────────────────
        valid_signals: List[StrategySignal] = []
        for s in signals:
            if s.action == "HOLD":
                continue
            if s.strength < self.min_strength:
                bot_logger.debug(
                    f"[SignalAggregator] Discarded low-strength signal from {s.strategy} "
                    f"on {s.pair}: strength={s.strength:.3f} < {self.min_strength}"
                )
                continue
            valid_signals.append(s)

        if not valid_signals:
            return []

        # ── Step 2: Group by pair ──────────────────────────────────────────
        by_pair: Dict[str, List[StrategySignal]] = {}
        for s in valid_signals:
            by_pair.setdefault(s.pair, []).append(s)

        output_signals: List[StrategySignal] = []

        # Process each pair
        for pair, pair_sigs in by_pair.items():
            # ── Step 3: Conflict resolution (BUY vs SELL) ───────────────────
            buys = [s for s in pair_sigs if s.action == "BUY"]
            sells = [s for s in pair_sigs if s.action == "SELL"]

            surviving_sigs: List[StrategySignal] = []

            if buys and sells:
                buy_conf = sum(s.strength for s in buys)
                sell_conf = sum(s.strength for s in sells)

                if buy_conf > 2.0 * sell_conf:
                    bot_logger.info(
                        f"[SignalAggregator] Conflict on {pair}: BUY dominates "
                        f"(buy_conf={buy_conf:.2f} > 2x sell_conf={sell_conf:.2f}). Dropping SELLs."
                    )
                    surviving_sigs = buys
                elif sell_conf > 2.0 * buy_conf:
                    bot_logger.info(
                        f"[SignalAggregator] Conflict on {pair}: SELL dominates "
                        f"(sell_conf={sell_conf:.2f} > 2x buy_conf={buy_conf:.2f}). Dropping BUYs."
                    )
                    surviving_sigs = sells
                else:
                    bot_logger.info(
                        f"[SignalAggregator] Discarding conflicting signals for {pair}: "
                        f"buy_conf={buy_conf:.2f} vs sell_conf={sell_conf:.2f} (neither > 2x)."
                    )
                    continue
            else:
                surviving_sigs = buys if buys else sells

            if not surviving_sigs:
                continue

            # ── Step 4: Regime fit scoring ─────────────────────────────────
            active_regime = (pair_regimes.get(pair) if pair_regimes else None) or regime or "NEUTRAL"

            scored_candidates = []
            for s in surviving_sigs:
                fit_score = self.get_regime_fit_score(s.strategy, active_regime)
                adjusted_strength = min(1.0, max(0.0, s.strength * fit_score))

                # Historical win rate (default 0.50 if no trade history yet)
                win_rate = rates.get(s.strategy, 0.50)
                rank_score = adjusted_strength * win_rate

                scored_candidates.append({
                    "signal": s,
                    "fit_score": fit_score,
                    "adjusted_strength": adjusted_strength,
                    "win_rate": win_rate,
                    "rank_score": rank_score,
                })

            if not scored_candidates:
                continue

            # ── Step 5: Rank by rank_score (adjusted_strength * win_rate) ──
            scored_candidates.sort(key=lambda item: item["rank_score"], reverse=True)
            top_candidate = scored_candidates[0]
            top_signal = top_candidate["signal"]

            # Update signal strength and enrich metadata
            top_signal.metadata = dict(top_signal.metadata or {})
            top_signal.metadata["original_strength"] = top_signal.strength
            top_signal.metadata["regime_fit_score"] = top_candidate["fit_score"]
            top_signal.metadata["regime"] = active_regime
            top_signal.metadata["historical_win_rate"] = top_candidate["win_rate"]
            top_signal.metadata["rank_score"] = round(top_candidate["rank_score"], 4)
            top_signal.strength = round(top_candidate["adjusted_strength"], 4)

            # ── Step 6: Throttle check (max 1 signal per pair per 5m) ──────
            if enforce_throttle:
                last_time = self._last_signal_time.get(pair, 0.0)
                elapsed = now - last_time
                if elapsed < self.throttle_seconds:
                    bot_logger.info(
                        f"[SignalAggregator] Throttled signal for {pair}: {top_signal.strategy} {top_signal.action} "
                        f"suppressed ({elapsed:.1f}s < {self.throttle_seconds}s throttle window)."
                    )
                    continue

            # Record throttle time and accept top signal
            self._last_signal_time[pair] = now
            output_signals.append(top_signal)

        return output_signals
