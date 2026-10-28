"""
AutoTrader Pro - Statistical Arbitrage Strategy
===============================================
Identifies cointegrated cryptocurrency pairs using the Engle-Granger two-step
test on a rolling 60-candle window. Monitors spread z-score divergences and
emits paired mean-reverting signals (Long Underperformer + Short Outperformer).

Key Rules:
  - Cointegration: Engle-Granger p-value < 0.05
  - Entry: Spread z-score > 2.0 (or < -2.0)
  - Exit: Spread z-score reverts to 0.5 (or |z| <= 0.5)
  - Default tested pair universe:
      * BTC/INR vs ETH/INR
      * SOL/INR vs XRP/INR
      * ETH/INR vs SOL/INR
      * BTC/INR vs SOL/INR
"""

from __future__ import annotations

from typing import Optional, Dict, Any, List, Tuple
import numpy as np
import pandas as pd

from backend.engine.strategy_base import StrategyBase, StrategySignal
from backend.utils.logger import bot_logger

# ── Engle-Granger Cointegration Test Implementation ──────────────────────────
def engle_granger_coint(
    y: np.ndarray, x: np.ndarray
) -> Tuple[float, float, Dict[str, float]]:
    """
    Perform Engle-Granger two-step cointegration test between series y and x.

    Step 1: OLS regression of y on x -> y = alpha + beta * x + residual
    Step 2: Augmented Dickey-Fuller test on the residuals

    Returns:
        Tuple of (adf_statistic, p_value, critical_values_dict).
    """
    y_arr = np.asarray(y, dtype=np.float64)
    x_arr = np.asarray(x, dtype=np.float64)

    n = len(y_arr)
    if n < 30 or len(x_arr) != n:
        return 0.0, 1.0, {"1%": -3.90, "5%": -3.34, "10%": -3.04}

    # Step 1: OLS regression
    x_mean = np.mean(x_arr)
    y_mean = np.mean(y_arr)
    x_var = np.var(x_arr)

    if x_var <= 1e-12:
        return 0.0, 1.0, {"1%": -3.90, "5%": -3.34, "10%": -3.04}

    beta = float(np.cov(x_arr, y_arr, bias=True)[0, 1] / x_var)
    alpha = float(y_mean - beta * x_mean)
    resid = y_arr - (alpha + beta * x_arr)

    # Step 2: Dickey-Fuller test on residuals: delta_e = gamma * e_{t-1} + error
    delta_resid = np.diff(resid)
    lag_resid = resid[:-1]

    denom = np.sum(lag_resid ** 2)
    if denom <= 1e-12:
        return 0.0, 1.0, {"1%": -3.90, "5%": -3.34, "10%": -3.04}

    gamma = float(np.sum(delta_resid * lag_resid) / denom)
    resid_err = delta_resid - gamma * lag_resid
    k = len(delta_resid)
    s2 = np.sum(resid_err ** 2) / max(1, k - 1)
    se_gamma = float(np.sqrt(s2 / denom))

    t_stat = float(gamma / se_gamma) if se_gamma > 0 else 0.0

    # Engle-Granger critical values (approximate for n=60 with constant)
    crit_values = {"1%": -3.90, "5%": -3.34, "10%": -3.04}

    # Approximate p-value from t_stat
    if t_stat <= crit_values["1%"]:
        p_val = 0.01
    elif t_stat <= crit_values["5%"]:
        # linear interpolate 0.01 to 0.05
        p_val = 0.01 + 0.04 * (t_stat - crit_values["1%"]) / (crit_values["5%"] - crit_values["1%"])
    elif t_stat <= crit_values["10%"]:
        # linear interpolate 0.05 to 0.10
        p_val = 0.05 + 0.05 * (t_stat - crit_values["5%"]) / (crit_values["10%"] - crit_values["5%"])
    else:
        # p-value > 0.10
        p_val = min(1.0, 0.10 + 0.90 * max(0.0, (t_stat - crit_values["10%"]) / 3.0))

    return round(t_stat, 4), round(p_val, 4), crit_values


# Expose coint on scipy.stats if not present
try:
    import scipy.stats
    if not hasattr(scipy.stats, "coint"):
        scipy.stats.coint = engle_granger_coint
except Exception:
    pass


class StatisticalArbitrageStrategy(StrategyBase):
    """
    Statistical Arbitrage (Pairs Trading) Strategy using Engle-Granger Cointegration
    and rolling spread z-scores.
    """

    DEFAULT_PARAMS: Dict[str, Any] = {
        "rolling_window": 60,
        "z_score_entry": 2.0,
        "z_score_exit": 0.5,
        "coint_pvalue_threshold": 0.05,
        "max_half_life": 30.0,
    }

    # Tested cointegration pairs
    CANDIDATE_PAIRS: List[Tuple[str, str]] = [
        ("BTC/INR", "ETH/INR"),
        ("SOL/INR", "XRP/INR"),
        ("ETH/INR", "SOL/INR"),
        ("BTC/INR", "SOL/INR"),
    ]

    def __init__(
        self,
        name: str = "Stat_Arb",
        exchange_manager: Optional[Any] = None,
        candidate_pairs: Optional[List[Tuple[str, str]]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Initialize the Statistical Arbitrage strategy."""
        merged = {**self.DEFAULT_PARAMS, **(params or {})}
        super().__init__(name=name, default_params=merged)
        self.exchange_manager = exchange_manager
        self.candidate_pairs = candidate_pairs or self.CANDIDATE_PAIRS
        self._candles_cache: Dict[str, pd.DataFrame] = {}

    def set_exchange_manager(self, exchange_manager: Any) -> None:
        """Update exchange manager reference."""
        self.exchange_manager = exchange_manager

    def _get_candles_for_pair(self, pair: str, limit: int = 60) -> Optional[pd.DataFrame]:
        """Fetch candles from cache or exchange manager."""
        cached = self._candles_cache.get(pair)
        if cached is not None and len(cached) >= limit:
            return cached

        if self.exchange_manager:
            try:
                df = self.exchange_manager.get_candles(pair=pair, interval="15m", limit=limit + 10)
                if df is not None and len(df) >= limit:
                    self._candles_cache[pair] = df
                    return df
            except Exception as e:
                bot_logger.debug(f"[{self.name}] Could not fetch candles for partner {pair}: {e}")

        return None

    def analyze(self, df: pd.DataFrame, pair: str) -> Optional[StrategySignal]:
        """
        Analyze pair relationships for the given asset against cointegrated partners.

        Args:
            df: OHLCV DataFrame for *pair*.
            pair: Trading pair symbol (e.g. 'BTC/INR').

        Returns:
            StrategySignal if an arbitrage divergence is detected, else None.
        """
        if df is None or len(df) < 60:
            return None

        # Store latest candles for this pair in cache
        self._candles_cache[pair] = df

        rolling_window = int(self.params.get("rolling_window", 60))
        z_entry = float(self.params.get("z_score_entry", 2.0))
        z_exit = float(self.params.get("z_score_exit", 0.5))
        p_threshold = float(self.params.get("coint_pvalue_threshold", 0.05))

        # Check candidate pairs involving this asset
        for p1, p2 in self.candidate_pairs:
            if pair != p1 and pair != p2:
                continue

            partner = p2 if pair == p1 else p1
            df_partner = self._get_candles_for_pair(partner, limit=rolling_window)
            if df_partner is None or len(df_partner) < rolling_window:
                continue

            try:
                # Align closing prices
                closes_y = df["close"].tail(rolling_window).astype(float).values
                closes_x = df_partner["close"].tail(rolling_window).astype(float).values

                if len(closes_y) != rolling_window or len(closes_x) != rolling_window:
                    continue

                # Run Engle-Granger Cointegration Test
                t_stat, p_val, _ = engle_granger_coint(closes_y, closes_x)

                if p_val > p_threshold:
                    # Not statistically cointegrated at required alpha
                    continue

                # OLS to compute spread: y = alpha + beta * x
                x_mean = np.mean(closes_x)
                y_mean = np.mean(closes_y)
                x_var = np.var(closes_x)
                if x_var <= 1e-12:
                    continue

                beta = float(np.cov(closes_x, closes_y, bias=True)[0, 1] / x_var)
                alpha = float(y_mean - beta * x_mean)
                spread = closes_y - (alpha + beta * closes_x)

                spread_mean = np.mean(spread)
                spread_std = np.std(spread)
                if spread_std <= 1e-12:
                    continue

                curr_spread = spread[-1]
                z_score = float((curr_spread - spread_mean) / spread_std)

                # Entry signals:
                # If z_score > 2.0: spread is abnormally high -> y is outperformer, x is underperformer.
                # If z_score < -2.0: spread is abnormally low -> y is underperformer, x is outperformer.
                action = None
                reason = ""
                long_leg = ""
                short_leg = ""

                if z_score > z_entry:
                    # y is overpriced, x is underpriced
                    long_leg = partner  # x
                    short_leg = pair    # y
                    action = "SELL"
                    reason = (
                        f"Stat Arb SELL {pair}: Spread z-score={z_score:+.2f} > {z_entry} "
                        f"(cointegrated with {partner}, p={p_val:.3f}, hedge_ratio={beta:.3f}). "
                        f"{pair} is outperforming (Short), {partner} is underperforming (Long)."
                    )

                elif z_score < -z_entry:
                    # y is underpriced, x is overpriced
                    long_leg = pair     # y
                    short_leg = partner  # x
                    action = "BUY"
                    reason = (
                        f"Stat Arb BUY {pair}: Spread z-score={z_score:+.2f} < -{z_entry} "
                        f"(cointegrated with {partner}, p={p_val:.3f}, hedge_ratio={beta:.3f}). "
                        f"{pair} is underperforming (Long), {partner} is outperforming (Short)."
                    )

                elif abs(z_score) <= z_exit:
                    bot_logger.debug(
                        f"[{self.name}] Spread between {pair} and {partner} in equilibrium (z={z_score:+.2f})"
                    )

                if action is not None:
                    # Strength scales with divergence beyond z_entry
                    divergence_excess = min(1.0, (abs(z_score) - z_entry) / 2.0)
                    strength = round(min(0.95, max(0.55, 0.65 + 0.25 * divergence_excess + 0.05 * (1.0 - p_val)), 4))

                    metadata = {
                        "pair_trade": True,
                        "primary_pair": pair,
                        "partner_pair": partner,
                        "action": action,
                        "long_leg": long_leg,
                        "short_leg": short_leg,
                        "underperformer": long_leg,
                        "outperformer": short_leg,
                        "z_score": round(z_score, 4),
                        "z_score_entry": z_entry,
                        "z_score_exit": z_exit,
                        "hedge_ratio": round(beta, 4),
                        "coint_pvalue": round(p_val, 4),
                        "rolling_window": rolling_window,
                    }

                    bot_logger.info(f"[{self.name}] {pair} -> {action} signal (strength={strength:.2f})")
                    return StrategySignal(
                        pair=pair,
                        action=action,
                        strategy=self.name,
                        strength=strength,
                        reason=reason,
                        metadata=metadata,
                    )

            except Exception as exc:
                bot_logger.error(
                    f"[{self.name}] Error testing cointegration between {pair} and {partner}: {exc}"
                )

        return None
