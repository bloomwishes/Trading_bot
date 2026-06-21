"""
AutoTrader Pro - Breakout Hunter Strategy
==========================================
Strategy 2: Detects Bollinger Band squeezes (low-volatility consolidation)
followed by breakouts confirmed by above-average volume.

Logic:
  BUY  — Bandwidth < squeeze_threshold (squeeze detected) AND
          close > upper Bollinger Band AND
          volume > volume_multiplier × 20-period volume SMA.
  Stop loss set at the middle Bollinger Band.
"""

from typing import Optional

import pandas as pd

from backend.engine.strategy_base import StrategyBase, StrategySignal
from backend.engine.indicators import (
    calculate_bollinger_bands,
    calculate_volume_sma,
)
from backend.utils.logger import bot_logger


class BreakoutHunterStrategy(StrategyBase):
    """
    Breakout Hunter — capture explosive moves after low-volatility squeezes.

    Default Parameters:
        bb_period (int): Bollinger Band lookback period (default 20).
        bb_std (int): Bollinger Band standard deviations (default 2).
        squeeze_threshold (float): Bandwidth below which a squeeze is detected
            (default 0.02, i.e. 2%).
        volume_multiplier (float): Current bar volume must exceed this multiple
            of the 20-period volume average (default 1.5).
        lookback_squeeze_bars (int): Number of recent bars that must have been
            in a squeeze to qualify (default 3).
    """

    DEFAULT_PARAMS = {
        "bb_period": 20,
        "bb_std": 2,
        "squeeze_threshold": 0.02,
        "volume_multiplier": 1.5,
        "lookback_squeeze_bars": 3,
    }

    def __init__(self, params: dict = None):
        merged = {**self.DEFAULT_PARAMS, **(params or {})}
        super().__init__(name="Breakout_Hunter", default_params=merged)

    def analyze(self, df: pd.DataFrame, pair: str) -> Optional[StrategySignal]:
        """
        Analyze candle data for Bollinger Band squeeze breakouts.

        Args:
            df: OHLCV DataFrame (minimum ~30 rows recommended).
            pair: Trading pair string.

        Returns:
            StrategySignal on breakout detection, else None.
        """
        bb_period = self.params["bb_period"]

        if df is None or len(df) < bb_period + 5:
            return None

        try:
            # ------------------------------------------------------------------
            # 1. Calculate Bollinger Bands
            # ------------------------------------------------------------------
            upper, middle, lower, bandwidth = calculate_bollinger_bands(
                df, period=bb_period, std_dev=self.params["bb_std"]
            )
            if upper.empty or bandwidth.empty:
                return None

            # ------------------------------------------------------------------
            # 2. Calculate volume metrics
            # ------------------------------------------------------------------
            vol_sma = calculate_volume_sma(df, period=bb_period)
            if vol_sma.empty:
                return None

            # Latest values
            latest_close = float(df["close"].iloc[-1])
            latest_upper = float(upper.iloc[-1])
            latest_middle = float(middle.iloc[-1])
            latest_lower = float(lower.iloc[-1])
            latest_bandwidth = float(bandwidth.iloc[-1])
            latest_volume = float(df["volume"].iloc[-1])
            latest_vol_sma = float(vol_sma.iloc[-1])

            if any(
                pd.isna(v)
                for v in [
                    latest_upper,
                    latest_middle,
                    latest_lower,
                    latest_bandwidth,
                    latest_vol_sma,
                ]
            ):
                return None

            squeeze_threshold = self.params["squeeze_threshold"]
            volume_multiplier = self.params["volume_multiplier"]
            lookback = self.params["lookback_squeeze_bars"]

            # ------------------------------------------------------------------
            # 3. Detect squeeze — recent bars must have had tight bandwidth
            # ------------------------------------------------------------------
            recent_bandwidths = bandwidth.iloc[-(lookback + 1) : -1].dropna()
            if len(recent_bandwidths) < lookback:
                return None

            was_in_squeeze = all(
                bw < squeeze_threshold for bw in recent_bandwidths.values
            )

            # ------------------------------------------------------------------
            # 4. Check breakout conditions
            # ------------------------------------------------------------------
            breaks_upper = latest_close > latest_upper
            breaks_lower = latest_close < latest_lower
            volume_confirmed = (
                latest_vol_sma > 0
                and latest_volume > volume_multiplier * latest_vol_sma
            )

            # ------------------------------------------------------------------
            # 5. BUY breakout — price above upper band with volume
            # ------------------------------------------------------------------
            if was_in_squeeze and breaks_upper and volume_confirmed:
                volume_ratio = latest_volume / latest_vol_sma if latest_vol_sma > 0 else 0
                # Strength: combination of bandwidth compression + volume spike
                strength = min(
                    1.0,
                    0.5
                    + 0.25 * min(1.0, (squeeze_threshold - latest_bandwidth) / squeeze_threshold * 2)
                    + 0.25 * min(1.0, (volume_ratio - volume_multiplier) / volume_multiplier),
                )
                strength = max(0.4, strength)

                reason = (
                    f"Bollinger squeeze breakout: bandwidth was "
                    f"{recent_bandwidths.mean():.4f} (< {squeeze_threshold}), "
                    f"price ₹{latest_close:.2f} broke above upper band "
                    f"₹{latest_upper:.2f}. Volume {latest_volume:.0f} = "
                    f"{volume_ratio:.1f}x average."
                )
                bot_logger.info(
                    f"[Breakout_Hunter] BUY signal for {pair}: {reason}"
                )
                return StrategySignal(
                    pair=pair,
                    action="BUY",
                    strategy=self.name,
                    strength=strength,
                    reason=reason,
                    metadata={
                        "stop_loss_price": latest_middle,
                        "upper_band": latest_upper,
                        "middle_band": latest_middle,
                        "lower_band": latest_lower,
                        "bandwidth": latest_bandwidth,
                        "volume_ratio": volume_ratio,
                        "squeeze_avg_bandwidth": float(recent_bandwidths.mean()),
                    },
                )

            # ------------------------------------------------------------------
            # 6. SELL breakout — price below lower band with volume (bearish)
            # ------------------------------------------------------------------
            if was_in_squeeze and breaks_lower and volume_confirmed:
                volume_ratio = latest_volume / latest_vol_sma if latest_vol_sma > 0 else 0
                strength = min(
                    1.0,
                    0.5
                    + 0.25 * min(1.0, (squeeze_threshold - latest_bandwidth) / squeeze_threshold * 2)
                    + 0.25 * min(1.0, (volume_ratio - volume_multiplier) / volume_multiplier),
                )
                strength = max(0.4, strength)

                reason = (
                    f"Bollinger squeeze breakdown: bandwidth was "
                    f"{recent_bandwidths.mean():.4f} (< {squeeze_threshold}), "
                    f"price ₹{latest_close:.2f} broke below lower band "
                    f"₹{latest_lower:.2f}. Volume {latest_volume:.0f} = "
                    f"{volume_ratio:.1f}x average."
                )
                bot_logger.info(
                    f"[Breakout_Hunter] SELL signal for {pair}: {reason}"
                )
                return StrategySignal(
                    pair=pair,
                    action="SELL",
                    strategy=self.name,
                    strength=strength,
                    reason=reason,
                    metadata={
                        "stop_loss_price": latest_middle,
                        "upper_band": latest_upper,
                        "middle_band": latest_middle,
                        "lower_band": latest_lower,
                        "bandwidth": latest_bandwidth,
                        "volume_ratio": volume_ratio,
                        "squeeze_avg_bandwidth": float(recent_bandwidths.mean()),
                    },
                )

            # No breakout detected
            return None

        except Exception as e:
            bot_logger.error(
                f"[Breakout_Hunter] Analysis error for {pair}: {e}"
            )
            return None
