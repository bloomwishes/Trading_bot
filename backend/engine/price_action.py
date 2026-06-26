"""
AutoTrader Pro - Price Action Strategy
=======================================
Strategy 5: Uses pure price action (candlestick patterns + support/resistance)
to generate high-probability reversal signals.

Signals:
  BUY  - Price is near a major support level and forms a Bullish Pin Bar or Bullish Engulfing.
  SELL - Price is near a major resistance level and forms a Bearish Pin Bar or Bearish Engulfing.
"""

from typing import Optional
import pandas as pd
from backend.engine.strategy_base import StrategyBase, StrategySignal
from backend.utils.logger import bot_logger

class PriceActionStrategy(StrategyBase):
    """
    Price Action Strategy - trade key levels using candlestick reversals.
    """

    DEFAULT_PARAMS = {
        "lookback": 30,             # Candles to calculate support/resistance
        "proximity_pct": 1.0,       # Max distance from S/R to validate setups
        "profit_target_pct": 2.0    # Used in signal metadata
    }

    def __init__(self, params: dict = None):
        merged = {**self.DEFAULT_PARAMS, **(params or {})}
        super().__init__(name="Price_Action", default_params=merged)

    def analyze(self, df: pd.DataFrame, pair: str) -> Optional[StrategySignal]:
        """
        Analyze candle data for price action setups.

        Args:
            df: OHLCV DataFrame.
            pair: Trading pair string.

        Returns:
            StrategySignal if setup triggers, else None.
        """
        lookback = int(self.params["lookback"])
        proximity_pct = float(self.params["proximity_pct"])

        # We need at least lookback + 2 candles (to compute S/R and check current + previous candles)
        if df is None or len(df) < lookback + 2:
            return None

        try:
            # 1. Compute Support & Resistance levels over lookback window (excluding current candle)
            historical_df = df.iloc[-lookback-1:-1]
            support_level = float(historical_df["low"].min())
            resistance_level = float(historical_df["high"].max())

            # 2. Extract current and previous candle metrics
            latest = df.iloc[-1]
            prev = df.iloc[-2]

            open_p = float(latest["open"])
            high_p = float(latest["high"])
            low_p = float(latest["low"])
            close_p = float(latest["close"])
            range_p = high_p - low_p

            prev_open = float(prev["open"])
            prev_close = float(prev["close"])

            if range_p <= 0:
                return None

            body_p = abs(close_p - open_p)
            upper_shadow = high_p - max(open_p, close_p)
            lower_shadow = min(open_p, close_p) - low_p

            # 3. Detect Candlestick Patterns
            # Bullish Pin Bar: Small body at the top, long lower tail
            is_bull_pin = (
                body_p <= range_p * 0.3 and
                lower_shadow >= range_p * 0.6 and
                upper_shadow <= range_p * 0.15
            )

            # Bearish Pin Bar: Small body at the bottom, long upper tail
            is_bear_pin = (
                body_p <= range_p * 0.3 and
                upper_shadow >= range_p * 0.6 and
                lower_shadow <= range_p * 0.15
            )

            # Bullish Engulfing: Current bullish body fully engulfs previous bearish body
            is_bull_engulfing = (
                prev_close < prev_open and
                close_p > open_p and
                open_p <= prev_close and
                close_p >= prev_open
            )

            # Bearish Engulfing: Current bearish body fully engulfs previous bullish body
            is_bear_engulfing = (
                prev_close > prev_open and
                close_p < open_p and
                open_p >= prev_close and
                close_p <= prev_open
            )

            # 4. Check proximity to S/R levels
            # Support proximity check (close price is below support + tolerance)
            near_support = close_p <= support_level * (1.0 + proximity_pct / 100.0)
            # Resistance proximity check (close price is above resistance - tolerance)
            near_resistance = close_p >= resistance_level * (1.0 - proximity_pct / 100.0)

            # 5. Signal Triggering
            # BUY Signal (Bullish reversal near support)
            if near_support and (is_bull_pin or is_bull_engulfing):
                pattern_name = "Bullish Pin Bar" if is_bull_pin else "Bullish Engulfing"
                strength = 0.85 if is_bull_pin else 0.80
                reason = (
                    f"Price Action BUY: {pattern_name} detected near support "
                    f"₹{support_level:.2f} (Current Price: ₹{close_p:.2f})"
                )
                bot_logger.info(f"[Price_Action] BUY signal for {pair}: {reason}")
                return StrategySignal(
                    pair=pair,
                    action="BUY",
                    strategy=self.name,
                    strength=strength,
                    reason=reason,
                    metadata={
                        "support_level": support_level,
                        "resistance_level": resistance_level,
                        "candlestick_pattern": pattern_name,
                        "profit_target_pct": self.params["profit_target_pct"]
                    }
                )

            # SELL Signal (Bearish reversal near resistance)
            if near_resistance and (is_bear_pin or is_bear_engulfing):
                pattern_name = "Bearish Pin Bar" if is_bear_pin else "Bearish Engulfing"
                strength = 0.85 if is_bear_pin else 0.80
                reason = (
                    f"Price Action SELL: {pattern_name} detected near resistance "
                    f"₹{resistance_level:.2f} (Current Price: ₹{close_p:.2f})"
                )
                bot_logger.info(f"[Price_Action] SELL signal for {pair}: {reason}")
                return StrategySignal(
                    pair=pair,
                    action="SELL",
                    strategy=self.name,
                    strength=strength,
                    reason=reason,
                    metadata={
                        "support_level": support_level,
                        "resistance_level": resistance_level,
                        "candlestick_pattern": pattern_name,
                        "profit_target_pct": self.params["profit_target_pct"]
                    }
                )

            return None

        except Exception as e:
            bot_logger.error(f"[Price_Action] Strategy analysis error for {pair}: {e}")
            return None
