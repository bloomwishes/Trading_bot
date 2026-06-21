"""
AutoTrader Pro - MA Pullback Strategy
======================================
Strategy 1: Identifies pullback entries in trending markets using
triple EMA alignment (9/21/50) confirmed by Stochastic RSI oversold/overbought.

Logic:
  BUY  — EMA9 > EMA21 > EMA50 (uptrend), price near EMA21 (±0.5%),
          StochRSI %K < 30 (oversold).
  SELL — StochRSI %K > 70 (overbought) in an existing position context,
          or profit target reached (≥ 2%).
"""

from typing import Optional

import pandas as pd

from backend.engine.strategy_base import StrategyBase, StrategySignal
from backend.engine.indicators import (
    calculate_ema,
    calculate_stoch_rsi,
)
from backend.utils.logger import bot_logger


class MAPullbackStrategy(StrategyBase):
    """
    MA Pullback — buy the dip in a confirmed trend.

    Default Parameters:
        ema_fast (int): Fast EMA period (default 9).
        ema_mid (int): Mid EMA period (default 21).
        ema_slow (int): Slow EMA period (default 50).
        stoch_rsi_buy (float): StochRSI threshold for buy signal (default 30).
        stoch_rsi_sell (float): StochRSI threshold for sell signal (default 70).
        profit_target_pct (float): Target profit percentage (default 2.0).
        pullback_tolerance_pct (float): Max distance from EMA21 to count as
            a pullback (default 0.5%).
    """

    DEFAULT_PARAMS = {
        "ema_fast": 9,
        "ema_mid": 21,
        "ema_slow": 50,
        "stoch_rsi_buy": 30,
        "stoch_rsi_sell": 70,
        "profit_target_pct": 2.0,
        "pullback_tolerance_pct": 0.5,
    }

    def __init__(self, params: dict = None):
        merged = {**self.DEFAULT_PARAMS, **(params or {})}
        super().__init__(name="MA_Pullback", default_params=merged)

    def analyze(self, df: pd.DataFrame, pair: str) -> Optional[StrategySignal]:
        """
        Analyze candle data for a pullback entry or exit.

        Args:
            df: OHLCV DataFrame (minimum ~60 rows recommended).
            pair: Trading pair string.

        Returns:
            StrategySignal on BUY / SELL opportunity, else None.
        """
        if df is None or len(df) < self.params["ema_slow"] + 5:
            return None

        try:
            # ------------------------------------------------------------------
            # 1. Calculate indicators
            # ------------------------------------------------------------------
            ema_fast = calculate_ema(df, self.params["ema_fast"])
            ema_mid = calculate_ema(df, self.params["ema_mid"])
            ema_slow = calculate_ema(df, self.params["ema_slow"])
            stoch_k, stoch_d = calculate_stoch_rsi(df)

            if ema_fast.empty or ema_mid.empty or ema_slow.empty or stoch_k.empty:
                return None

            # Latest values
            latest_close = float(df["close"].iloc[-1])
            latest_ema_fast = float(ema_fast.iloc[-1])
            latest_ema_mid = float(ema_mid.iloc[-1])
            latest_ema_slow = float(ema_slow.iloc[-1])
            latest_stoch_k = float(stoch_k.iloc[-1])

            if any(
                pd.isna(v)
                for v in [
                    latest_ema_fast,
                    latest_ema_mid,
                    latest_ema_slow,
                    latest_stoch_k,
                ]
            ):
                return None

            # ------------------------------------------------------------------
            # 2. Check trend alignment
            # ------------------------------------------------------------------
            uptrend = latest_ema_fast > latest_ema_mid > latest_ema_slow
            downtrend = latest_ema_fast < latest_ema_mid < latest_ema_slow

            # ------------------------------------------------------------------
            # 3. Check pullback proximity to EMA21
            # ------------------------------------------------------------------
            distance_to_mid_pct = (
                abs(latest_close - latest_ema_mid) / latest_ema_mid * 100.0
            )
            is_near_mid = distance_to_mid_pct <= self.params["pullback_tolerance_pct"]

            # ------------------------------------------------------------------
            # 4. BUY signal — uptrend pullback with oversold StochRSI
            # ------------------------------------------------------------------
            stoch_buy_threshold = self.params["stoch_rsi_buy"]
            stoch_sell_threshold = self.params["stoch_rsi_sell"]

            if uptrend and is_near_mid and latest_stoch_k < stoch_buy_threshold:
                # Strength: the more oversold, the stronger the signal
                # StochRSI 0 → strength 1.0, StochRSI 30 → strength ~0.3
                strength = max(
                    0.3,
                    min(1.0, 1.0 - (latest_stoch_k / stoch_buy_threshold)),
                )
                reason = (
                    f"Uptrend pullback: EMA9({latest_ema_fast:.2f}) > "
                    f"EMA21({latest_ema_mid:.2f}) > EMA50({latest_ema_slow:.2f}). "
                    f"Price ₹{latest_close:.2f} within {distance_to_mid_pct:.2f}% "
                    f"of EMA21. StochRSI K={latest_stoch_k:.1f} (oversold)."
                )
                bot_logger.info(
                    f"[MA_Pullback] BUY signal for {pair}: {reason}"
                )
                return StrategySignal(
                    pair=pair,
                    action="BUY",
                    strategy=self.name,
                    strength=strength,
                    reason=reason,
                    metadata={
                        "ema_fast": latest_ema_fast,
                        "ema_mid": latest_ema_mid,
                        "ema_slow": latest_ema_slow,
                        "stoch_rsi_k": latest_stoch_k,
                        "distance_to_ema21_pct": distance_to_mid_pct,
                        "profit_target_pct": self.params["profit_target_pct"],
                    },
                )

            # ------------------------------------------------------------------
            # 5. SELL signal — overbought StochRSI in a downtrend or overbought
            # ------------------------------------------------------------------
            if latest_stoch_k > stoch_sell_threshold:
                # Strength based on how overbought
                strength = max(
                    0.3,
                    min(
                        1.0,
                        (latest_stoch_k - stoch_sell_threshold)
                        / (100.0 - stoch_sell_threshold),
                    ),
                )
                reason = (
                    f"Overbought: StochRSI K={latest_stoch_k:.1f} > "
                    f"{stoch_sell_threshold}. "
                )
                if downtrend:
                    reason += (
                        f"Downtrend confirmed: EMA9({latest_ema_fast:.2f}) < "
                        f"EMA21({latest_ema_mid:.2f}) < EMA50({latest_ema_slow:.2f})."
                    )
                    strength = min(1.0, strength + 0.15)
                else:
                    reason += "Consider taking profits."

                bot_logger.info(
                    f"[MA_Pullback] SELL signal for {pair}: {reason}"
                )
                return StrategySignal(
                    pair=pair,
                    action="SELL",
                    strategy=self.name,
                    strength=strength,
                    reason=reason,
                    metadata={
                        "ema_fast": latest_ema_fast,
                        "ema_mid": latest_ema_mid,
                        "ema_slow": latest_ema_slow,
                        "stoch_rsi_k": latest_stoch_k,
                        "downtrend": downtrend,
                    },
                )

            # No actionable signal
            return None

        except Exception as e:
            bot_logger.error(f"[MA_Pullback] Analysis error for {pair}: {e}")
            return None
