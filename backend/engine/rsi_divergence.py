"""
AutoTrader Pro - RSI Divergence Strategy
=========================================
Strategy 3: Detects bullish and bearish divergences between price action
and the Relative Strength Index (RSI).

Logic:
  Bullish divergence — price makes a LOWER low but RSI makes a HIGHER low → BUY.
  Bearish divergence — price makes a HIGHER high but RSI makes a LOWER high → SELL.

Works on any timeframe; the caller provides the appropriate DataFrame
(e.g. 15 m or 1 h candles).
"""

from typing import Optional, List, Tuple

import pandas as pd
import numpy as np

from backend.engine.strategy_base import StrategyBase, StrategySignal
from backend.engine.indicators import (
    calculate_rsi,
    detect_swing_highs,
    detect_swing_lows,
)
from backend.utils.logger import bot_logger


class RSIDivergenceStrategy(StrategyBase):
    """
    RSI Divergence — fade exhaustion moves using divergence signals.

    Default Parameters:
        rsi_period (int): RSI calculation period (default 14).
        swing_window (int): Bars on each side for swing-point detection
            (default 5).
        min_divergence_bars (int): Minimum bars between the two swing points
            forming the divergence (default 3).
        max_divergence_bars (int): Maximum bars between swing points
            (default 50). Prevents ancient divergences from firing.
    """

    DEFAULT_PARAMS = {
        "rsi_period": 14,
        "swing_window": 5,
        "min_divergence_bars": 3,
        "max_divergence_bars": 50,
    }

    def __init__(self, params: dict = None):
        merged = {**self.DEFAULT_PARAMS, **(params or {})}
        super().__init__(name="RSI_Divergence", default_params=merged)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _swing_highs_for_series(
        series: pd.Series, window: int
    ) -> List[Tuple[int, float]]:
        """Detect swing highs in an arbitrary numeric series."""
        values = series.values
        swings: List[Tuple[int, float]] = []
        for i in range(window, len(values) - window):
            if pd.isna(values[i]):
                continue
            is_swing = True
            for j in range(1, window + 1):
                left = values[i - j]
                right = values[i + j]
                if pd.isna(left) or pd.isna(right):
                    is_swing = False
                    break
                if values[i] <= left or values[i] <= right:
                    is_swing = False
                    break
            if is_swing:
                swings.append((series.index[i], float(values[i])))
        return swings

    @staticmethod
    def _swing_lows_for_series(
        series: pd.Series, window: int
    ) -> List[Tuple[int, float]]:
        """Detect swing lows in an arbitrary numeric series."""
        values = series.values
        swings: List[Tuple[int, float]] = []
        for i in range(window, len(values) - window):
            if pd.isna(values[i]):
                continue
            is_swing = True
            for j in range(1, window + 1):
                left = values[i - j]
                right = values[i + j]
                if pd.isna(left) or pd.isna(right):
                    is_swing = False
                    break
                if values[i] >= left or values[i] >= right:
                    is_swing = False
                    break
            if is_swing:
                swings.append((series.index[i], float(values[i])))
        return swings

    # ------------------------------------------------------------------
    # Main analysis
    # ------------------------------------------------------------------
    def analyze(self, df: pd.DataFrame, pair: str) -> Optional[StrategySignal]:
        """
        Scan for RSI divergence.

        Args:
            df: OHLCV DataFrame.
            pair: Trading pair string.

        Returns:
            StrategySignal on divergence detection, else None.
        """
        rsi_period = self.params["rsi_period"]
        swing_window = self.params["swing_window"]
        min_div_bars = self.params["min_divergence_bars"]
        max_div_bars = self.params["max_divergence_bars"]

        min_rows = rsi_period + swing_window * 2 + min_div_bars + 5
        if df is None or len(df) < min_rows:
            return None

        try:
            # ------------------------------------------------------------------
            # 1. Calculate RSI
            # ------------------------------------------------------------------
            rsi = calculate_rsi(df, period=rsi_period)
            if rsi.empty:
                return None

            # ------------------------------------------------------------------
            # 2. Detect swing points in price and RSI
            # ------------------------------------------------------------------
            price_swing_lows = detect_swing_lows(df, window=swing_window)
            price_swing_highs = detect_swing_highs(df, window=swing_window)

            rsi_swing_lows = self._swing_lows_for_series(rsi, window=swing_window)
            rsi_swing_highs = self._swing_highs_for_series(rsi, window=swing_window)

            # ------------------------------------------------------------------
            # 3. Check for bullish divergence (lower low in price, higher low in RSI)
            # ------------------------------------------------------------------
            bullish_signal = self._check_bullish_divergence(
                price_swing_lows,
                rsi_swing_lows,
                pair,
                df,
                rsi,
                min_div_bars,
                max_div_bars,
            )
            if bullish_signal is not None:
                return bullish_signal

            # ------------------------------------------------------------------
            # 4. Check for bearish divergence (higher high in price, lower high in RSI)
            # ------------------------------------------------------------------
            bearish_signal = self._check_bearish_divergence(
                price_swing_highs,
                rsi_swing_highs,
                pair,
                df,
                rsi,
                min_div_bars,
                max_div_bars,
            )
            if bearish_signal is not None:
                return bearish_signal

            return None

        except Exception as e:
            bot_logger.error(
                f"[RSI_Divergence] Analysis error for {pair}: {e}"
            )
            return None

    def _check_bullish_divergence(
        self,
        price_lows: List[Tuple],
        rsi_lows: List[Tuple],
        pair: str,
        df: pd.DataFrame,
        rsi: pd.Series,
        min_bars: int,
        max_bars: int,
    ) -> Optional[StrategySignal]:
        """Check the most recent two swing lows for bullish divergence."""
        if len(price_lows) < 2 or len(rsi_lows) < 2:
            return None

        # Take the last two price swing lows
        prev_price_idx, prev_price_val = price_lows[-2]
        curr_price_idx, curr_price_val = price_lows[-1]

        # Bars between the two price lows
        try:
            pos_prev = df.index.get_loc(prev_price_idx)
            pos_curr = df.index.get_loc(curr_price_idx)
        except KeyError:
            return None

        bar_distance = pos_curr - pos_prev
        if bar_distance < min_bars or bar_distance > max_bars:
            return None

        # Price makes a lower low
        if curr_price_val >= prev_price_val:
            return None

        # Find RSI swing lows closest to those price swing indices
        prev_rsi_val = self._find_nearest_swing(rsi_lows, prev_price_idx, df)
        curr_rsi_val = self._find_nearest_swing(rsi_lows, curr_price_idx, df)

        if prev_rsi_val is None or curr_rsi_val is None:
            return None

        # RSI makes a higher low (divergence)
        if curr_rsi_val <= prev_rsi_val:
            return None

        # Divergence confirmed!
        # Strength based on divergence magnitude
        price_drop_pct = abs(curr_price_val - prev_price_val) / prev_price_val * 100
        rsi_rise = curr_rsi_val - prev_rsi_val
        strength = min(1.0, 0.4 + 0.3 * min(1.0, price_drop_pct / 5.0) + 0.3 * min(1.0, rsi_rise / 15.0))

        latest_rsi = float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else 0
        latest_close = float(df["close"].iloc[-1])

        reason = (
            f"Bullish RSI divergence: price made lower low "
            f"(₹{prev_price_val:.2f} → ₹{curr_price_val:.2f}) "
            f"but RSI made higher low ({prev_rsi_val:.1f} → {curr_rsi_val:.1f}). "
            f"Current RSI={latest_rsi:.1f}. "
            f"Divergence over {bar_distance} bars."
        )
        bot_logger.info(f"[RSI_Divergence] BUY signal for {pair}: {reason}")

        return StrategySignal(
            pair=pair,
            action="BUY",
            strategy=self.name,
            strength=strength,
            reason=reason,
            metadata={
                "divergence_type": "bullish",
                "prev_price_low": prev_price_val,
                "curr_price_low": curr_price_val,
                "prev_rsi_low": prev_rsi_val,
                "curr_rsi_low": curr_rsi_val,
                "bar_distance": bar_distance,
                "current_rsi": latest_rsi,
                "current_price": latest_close,
            },
        )

    def _check_bearish_divergence(
        self,
        price_highs: List[Tuple],
        rsi_highs: List[Tuple],
        pair: str,
        df: pd.DataFrame,
        rsi: pd.Series,
        min_bars: int,
        max_bars: int,
    ) -> Optional[StrategySignal]:
        """Check the most recent two swing highs for bearish divergence."""
        if len(price_highs) < 2 or len(rsi_highs) < 2:
            return None

        prev_price_idx, prev_price_val = price_highs[-2]
        curr_price_idx, curr_price_val = price_highs[-1]

        try:
            pos_prev = df.index.get_loc(prev_price_idx)
            pos_curr = df.index.get_loc(curr_price_idx)
        except KeyError:
            return None

        bar_distance = pos_curr - pos_prev
        if bar_distance < min_bars or bar_distance > max_bars:
            return None

        # Price makes a higher high
        if curr_price_val <= prev_price_val:
            return None

        # Find RSI swing highs closest to those price swing indices
        prev_rsi_val = self._find_nearest_swing(rsi_highs, prev_price_idx, df)
        curr_rsi_val = self._find_nearest_swing(rsi_highs, curr_price_idx, df)

        if prev_rsi_val is None or curr_rsi_val is None:
            return None

        # RSI makes a lower high (divergence)
        if curr_rsi_val >= prev_rsi_val:
            return None

        # Divergence confirmed!
        price_rise_pct = abs(curr_price_val - prev_price_val) / prev_price_val * 100
        rsi_drop = prev_rsi_val - curr_rsi_val
        strength = min(1.0, 0.4 + 0.3 * min(1.0, price_rise_pct / 5.0) + 0.3 * min(1.0, rsi_drop / 15.0))

        latest_rsi = float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else 0
        latest_close = float(df["close"].iloc[-1])

        reason = (
            f"Bearish RSI divergence: price made higher high "
            f"(₹{prev_price_val:.2f} → ₹{curr_price_val:.2f}) "
            f"but RSI made lower high ({prev_rsi_val:.1f} → {curr_rsi_val:.1f}). "
            f"Current RSI={latest_rsi:.1f}. "
            f"Divergence over {bar_distance} bars."
        )
        bot_logger.info(f"[RSI_Divergence] SELL signal for {pair}: {reason}")

        return StrategySignal(
            pair=pair,
            action="SELL",
            strategy=self.name,
            strength=strength,
            reason=reason,
            metadata={
                "divergence_type": "bearish",
                "prev_price_high": prev_price_val,
                "curr_price_high": curr_price_val,
                "prev_rsi_high": prev_rsi_val,
                "curr_rsi_high": curr_rsi_val,
                "bar_distance": bar_distance,
                "current_rsi": latest_rsi,
                "current_price": latest_close,
            },
        )

    @staticmethod
    def _find_nearest_swing(
        swings: List[Tuple], target_idx, df: pd.DataFrame, tolerance: int = 5
    ) -> Optional[float]:
        """
        Find the swing point value nearest to target_idx (within tolerance bars).

        Args:
            swings: List of (index, value) tuples.
            target_idx: The DataFrame index to search near.
            df: The full DataFrame (used to compute positional distance).
            tolerance: Maximum positional distance in bars.

        Returns:
            The swing value if found within tolerance, else None.
        """
        try:
            target_pos = df.index.get_loc(target_idx)
        except KeyError:
            return None

        best_val = None
        best_dist = tolerance + 1

        for swing_idx, swing_val in swings:
            try:
                swing_pos = df.index.get_loc(swing_idx)
            except KeyError:
                continue
            dist = abs(swing_pos - target_pos)
            if dist < best_dist:
                best_dist = dist
                best_val = swing_val

        return best_val if best_dist <= tolerance else None
