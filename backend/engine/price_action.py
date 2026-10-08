"""
AutoTrader Pro - Price Action Strategy
=======================================
Strategy: High-probability Price Action trading using candlestick patterns
(Pin Bars, Hammers, Shooting Stars, Engulfing Bars) confirmed by Key Support &
Resistance levels, Volume validation, and dynamic Risk-to-Reward targets.

Logic:
  BUY:
    - Bullish Pin Bar (Hammer) or Bullish Engulfing candle formed.
    - Price is at or near Key Support / Swing Low zone (within support_tolerance_pct).
    - Volume confirms the rejection (current volume > volume_sma * volume_factor).
    - Stop Loss placed just below the rejection candle low.
    - Take Profit set with minimum Risk/Reward ratio (default 2.0x).
  SELL / EXIT:
    - Bearish Pin Bar (Shooting Star) or Bearish Engulfing at Resistance,
      or target reached.
"""

from typing import Optional, List, Tuple, Dict, Any
import pandas as pd
import numpy as np

from backend.engine.strategy_base import StrategyBase, StrategySignal
from backend.engine.indicators import (
    calculate_volume_sma,
    calculate_atr,
    detect_swing_highs,
    detect_swing_lows,
)
from backend.utils.logger import bot_logger


class PriceActionStrategy(StrategyBase):
    """
    Price Action Strategy — Trades pure market structure, rejection wicks,
    and institutional candlestick patterns at key levels.

    Default Parameters:
        swing_window (int): Lookback on each side for swing level detection (default 5).
        pin_bar_ratio (float): Ratio of rejection wick to candle body (default 2.0).
        support_tolerance_pct (float): Max distance (%) from Support/Resistance level (default 0.8%).
        profit_target_rr (float): Risk-to-Reward ratio for take-profit calculation (default 2.0).
        volume_factor (float): Volume multiplier relative to 20-period average (default 1.2).
        min_confidence (float): Minimum confidence threshold (0.0 to 1.0, default 0.75).
    """

    DEFAULT_PARAMS = {
        "swing_window": 5,
        "pin_bar_ratio": 2.0,
        "support_tolerance_pct": 0.8,
        "profit_target_rr": 2.0,
        "volume_factor": 1.2,
        "min_confidence": 0.75,
    }

    def __init__(self, params: dict = None):
        merged = {**self.DEFAULT_PARAMS, **(params or {})}
        super().__init__(name="Price_Action", default_params=merged)

    def analyze(self, df: pd.DataFrame, pair: str) -> Optional[StrategySignal]:
        """
        Analyze candlestick price action for high-probability setups.

        Args:
            df: OHLCV DataFrame (minimum ~35 candles recommended).
            pair: Trading pair string.

        Returns:
            StrategySignal on valid setup, else None.
        """
        if df is None or len(df) < 30:
            return None

        try:
            # 1. Volume moving average
            vol_sma = calculate_volume_sma(df, period=20)
            atr_series = calculate_atr(df, period=14)
            atr = float(atr_series.iloc[-1]) if not atr_series.empty and not pd.isna(atr_series.iloc[-1]) else 0.0

            # 2. Extract recent candles
            curr = df.iloc[-1]
            prev = df.iloc[-2]

            curr_open = float(curr["open"])
            curr_high = float(curr["high"])
            curr_low = float(curr["low"])
            curr_close = float(curr["close"])
            curr_vol = float(curr.get("volume", 0))

            prev_open = float(prev["open"])
            prev_high = float(prev["high"])
            prev_low = float(prev["low"])
            prev_close = float(prev["close"])

            candle_range = curr_high - curr_low
            if candle_range <= 0:
                return None

            body = abs(curr_close - curr_open)
            body = max(body, candle_range * 0.05)  # prevent division by zero
            upper_wick = curr_high - max(curr_open, curr_close)
            lower_wick = min(curr_open, curr_close) - curr_low

            # Volume confirmation
            avg_vol = float(vol_sma.iloc[-1]) if not vol_sma.empty and not pd.isna(vol_sma.iloc[-1]) else 1.0
            volume_confirmed = curr_vol >= (avg_vol * self.params["volume_factor"])

            # 3. Detect Key Support & Resistance (Swing Highs / Lows)
            swing_window = int(self.params["swing_window"])
            swing_lows = detect_swing_lows(df.iloc[:-1], window=swing_window)
            swing_highs = detect_swing_highs(df.iloc[:-1], window=swing_window)

            nearest_support = None
            if swing_lows:
                # Find the most relevant support level below or near current price
                supports = [price for _, price in swing_lows if price <= curr_close * 1.01]
                if supports:
                    nearest_support = max(supports)

            nearest_resistance = None
            if swing_highs:
                resistances = [price for _, price in swing_highs if price >= curr_close * 0.99]
                if resistances:
                    nearest_resistance = min(resistances)

            # Check distance to support (in %)
            at_support = False
            if nearest_support:
                dist_pct = abs(curr_low - nearest_support) / nearest_support * 100.0
                at_support = dist_pct <= self.params["support_tolerance_pct"]

            at_resistance = False
            if nearest_resistance:
                dist_pct = abs(curr_high - nearest_resistance) / nearest_resistance * 100.0
                at_resistance = dist_pct <= self.params["support_tolerance_pct"]

            # 4. Candlestick Pattern Checks
            pin_ratio = float(self.params["pin_bar_ratio"])
            rr_ratio = float(self.params["profit_target_rr"])

            # A. Bullish Pin Bar (Hammer)
            # Long lower shadow, small body, close near top
            is_bullish_pin = (
                lower_wick >= (body * pin_ratio)
                and upper_wick <= (body * 0.8)
                and (curr_close >= curr_open or (curr_close - curr_low) >= (candle_range * 0.65))
            )

            # B. Bullish Engulfing
            # Prior candle red, current candle green, engulfing prior body
            is_bullish_engulfing = (
                prev_close < prev_open
                and curr_close > curr_open
                and curr_open <= prev_close
                and curr_close >= prev_open
                and body > abs(prev_close - prev_open) * 1.1
            )

            # C. Bearish Pin Bar (Shooting Star)
            is_bearish_pin = (
                upper_wick >= (body * pin_ratio)
                and lower_wick <= (body * 0.8)
                and (curr_close <= curr_open or (curr_high - curr_close) >= (candle_range * 0.65))
            )

            # D. Bearish Engulfing
            is_bearish_engulfing = (
                prev_close > prev_open
                and curr_close < curr_open
                and curr_open >= prev_close
                and curr_close <= prev_open
                and body > abs(prev_close - prev_open) * 1.1
            )

            # 5. Evaluate BUY Signal
            if is_bullish_pin or is_bullish_engulfing:
                pattern_name = "Bullish Pin Bar (Hammer)" if is_bullish_pin else "Bullish Engulfing"
                
                # Base confidence
                confidence = 0.75
                if at_support:
                    confidence += 0.12
                if volume_confirmed:
                    confidence += 0.08
                if curr_close > prev_high:
                    confidence += 0.05

                confidence = min(0.95, round(confidence, 2))

                if confidence >= self.params["min_confidence"]:
                    # Stop loss: just below candle low or support
                    risk_buffer = (atr * 0.5) if atr > 0 else (curr_close * 0.005)
                    sl_price = min(curr_low, (nearest_support or curr_low)) - risk_buffer
                    risk_dist = curr_close - sl_price

                    if risk_dist > 0:
                        tp_price = curr_close + (risk_dist * rr_ratio)
                        if nearest_resistance and nearest_resistance > curr_close:
                            # If resistance is further than 1.5x risk, target it
                            if (nearest_resistance - curr_close) >= (risk_dist * 1.5):
                                tp_price = max(tp_price, nearest_resistance)

                        bot_logger.info(
                            f"[PriceAction] BUY signal on {pair}: {pattern_name} "
                            f"(confidence={confidence}, at_support={at_support}, vol={volume_confirmed}) "
                            f"Price=₹{curr_close:.2f} SL=₹{sl_price:.2f} TP=₹{tp_price:.2f}"
                        )

                        return StrategySignal(
                            strategy=self.name,
                            pair=pair,
                            action="BUY",
                            strength=confidence,
                            reason=(
                                f"{pattern_name} rejection"
                                + (" at Key Support" if at_support else "")
                                + (" with Volume surge" if volume_confirmed else "")
                            ),
                            metadata={
                                "pattern": pattern_name,
                                "stop_loss_price": round(sl_price, 4),
                                "take_profit_price": round(tp_price, 4),
                                "support_level": round(nearest_support, 4) if nearest_support else None,
                                "at_support": at_support,
                                "volume_confirmed": volume_confirmed,
                                "risk_reward": rr_ratio,
                            },
                        )

            # 6. Evaluate SELL Signal (rejection at resistance)
            if is_bearish_pin or is_bearish_engulfing:
                pattern_name = "Bearish Pin Bar (Shooting Star)" if is_bearish_pin else "Bearish Engulfing"
                confidence = 0.70
                if at_resistance:
                    confidence += 0.15
                if volume_confirmed:
                    confidence += 0.10

                confidence = min(0.95, round(confidence, 2))

                if confidence >= self.params["min_confidence"] and at_resistance:
                    bot_logger.info(
                        f"[PriceAction] SELL signal on {pair}: {pattern_name} at Resistance (conf={confidence})"
                    )
                    return StrategySignal(
                        strategy=self.name,
                        pair=pair,
                        action="SELL",
                        strength=confidence,
                        reason=f"{pattern_name} rejection at Resistance level",
                        metadata={
                            "pattern": pattern_name,
                            "at_resistance": at_resistance,
                            "resistance_level": round(nearest_resistance, 4) if nearest_resistance else None,
                        },
                    )

        except Exception as exc:
            bot_logger.error(f"[PriceAction] analyze error on {pair}: {exc}")

        return None
