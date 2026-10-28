"""
AutoTrader Pro - Mean Reversion Strategy
========================================
Exploits statistical price extremes in ranging or low-trend market regimes.

Entry Logic:
  - BUY: Price touches or crosses below lower Bollinger Band
         AND RSI(14) < rsi_oversold (30)
         AND StochRSI %K < 20
         AND ADX < adx_max (20)
  - SELL: Price touches or crosses above upper Bollinger Band
          AND RSI(14) > rsi_overbought (70)
          AND StochRSI %K > 80
          AND ADX < adx_max (20)

Risk Boundaries:
  - Exit Target: Middle Bollinger Band (SMA 20)
  - Stop Loss: 0.5x Bollinger Bandwidth beyond entry band
"""

from __future__ import annotations

from typing import Optional, Dict, Any
import pandas as pd

from backend.engine.strategy_base import StrategyBase, StrategySignal
from backend.engine.indicators import (
    calculate_bollinger_bands,
    calculate_rsi,
    calculate_stoch_rsi,
    calculate_adx,
)
from backend.utils.logger import bot_logger


class MeanReversionStrategy(StrategyBase):
    """
    Mean Reversion Strategy using Bollinger Bands, RSI, StochRSI, and ADX filter.
    """

    DEFAULT_PARAMS: Dict[str, Any] = {
        "bb_period": 20,
        "bb_std": 2.0,
        "rsi_period": 14,
        "rsi_oversold": 30.0,
        "rsi_overbought": 70.0,
        "stoch_k_oversold": 20.0,
        "stoch_k_overbought": 80.0,
        "adx_period": 14,
        "adx_max": 20.0,
    }

    def __init__(
        self,
        name: str = "Mean_Reversion",
        params: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Initialize the Mean Reversion strategy."""
        merged = {**self.DEFAULT_PARAMS, **(params or {})}
        super().__init__(name=name, default_params=merged)

    def analyze(self, df: pd.DataFrame, pair: str) -> Optional[StrategySignal]:
        """
        Analyze candle data and generate a Mean Reversion signal if conditions are met.

        Args:
            df: OHLCV DataFrame with columns [timestamp, open, high, low, close, volume].
            pair: Trading pair symbol (e.g. 'BTC/INR').

        Returns:
            StrategySignal if entry threshold is satisfied, else None.
        """
        if df is None or len(df) < 35:
            return None

        bb_period = int(self.params.get("bb_period", 20))
        bb_std = float(self.params.get("bb_std", 2.0))
        rsi_period = int(self.params.get("rsi_period", 14))
        rsi_oversold = float(self.params.get("rsi_oversold", 30.0))
        rsi_overbought = float(self.params.get("rsi_overbought", 70.0))
        stoch_k_oversold = float(self.params.get("stoch_k_oversold", 20.0))
        stoch_k_overbought = float(self.params.get("stoch_k_overbought", 80.0))
        adx_period = int(self.params.get("adx_period", 14))
        adx_max = float(self.params.get("adx_max", 20.0))

        try:
            # 1. Calculate indicators
            upper_bb, mid_bb, lower_bb, _ = calculate_bollinger_bands(
                df, period=bb_period, std_dev=int(bb_std) if bb_std.is_integer() else bb_std
            )
            rsi_series = calculate_rsi(df, period=rsi_period)
            stoch_k, _ = calculate_stoch_rsi(df, period=rsi_period)
            adx_series, _, _ = calculate_adx(df, period=adx_period)

            if (
                upper_bb.empty
                or mid_bb.empty
                or lower_bb.empty
                or rsi_series.empty
                or stoch_k.empty
                or adx_series.empty
            ):
                return None

            close_p = float(df["close"].iloc[-1])
            low_p = float(df["low"].iloc[-1])
            high_p = float(df["high"].iloc[-1])

            curr_upper = float(upper_bb.dropna().iloc[-1])
            curr_mid = float(mid_bb.dropna().iloc[-1])
            curr_lower = float(lower_bb.dropna().iloc[-1])
            curr_rsi = float(rsi_series.dropna().iloc[-1])
            curr_k = float(stoch_k.dropna().iloc[-1])
            curr_adx = float(adx_series.dropna().iloc[-1])

            bb_width = curr_upper - curr_lower
            if bb_width <= 0:
                return None

            # 2. Check BUY condition (Oversold extreme in low-trend / ranging regime)
            is_buy = (
                (close_p <= curr_lower or low_p <= curr_lower)
                and curr_rsi < rsi_oversold
                and curr_k < stoch_k_oversold
                and curr_adx < adx_max
            )

            if is_buy:
                take_profit_price = curr_mid
                stop_loss_price = curr_lower - (0.5 * bb_width)

                # Confidence scales with depth of oversold extension and low ADX
                rsi_factor = max(0.0, min(1.0, (rsi_oversold - curr_rsi) / rsi_oversold))
                stoch_factor = max(0.0, min(1.0, (stoch_k_oversold - curr_k) / stoch_k_oversold))
                adx_factor = max(0.0, min(1.0, (adx_max - curr_adx) / adx_max))

                strength = round(
                    min(0.95, max(0.55, 0.60 + 0.15 * rsi_factor + 0.15 * stoch_factor + 0.10 * adx_factor)),
                    4,
                )

                reason = (
                    f"Mean Reversion BUY: Price ({close_p:.2f}) pierced lower band ({curr_lower:.2f}), "
                    f"RSI={curr_rsi:.1f} < {rsi_oversold}, StochK={curr_k:.1f} < {stoch_k_oversold}, "
                    f"ADX={curr_adx:.1f} < {adx_max}"
                )

                metadata = {
                    "take_profit_price": round(take_profit_price, 2),
                    "stop_loss_price": round(stop_loss_price, 2),
                    "bb_middle": round(curr_mid, 2),
                    "bb_upper": round(curr_upper, 2),
                    "bb_lower": round(curr_lower, 2),
                    "bb_width": round(bb_width, 2),
                    "rsi": round(curr_rsi, 2),
                    "stoch_k": round(curr_k, 2),
                    "adx": round(curr_adx, 2),
                }

                bot_logger.info(f"[{self.name}] {pair} -> BUY signal (strength={strength:.2f})")
                return StrategySignal(
                    pair=pair,
                    action="BUY",
                    strategy=self.name,
                    strength=strength,
                    reason=reason,
                    metadata=metadata,
                )

            # 3. Check SELL condition (Overbought extreme in low-trend / ranging regime)
            is_sell = (
                (close_p >= curr_upper or high_p >= curr_upper)
                and curr_rsi > rsi_overbought
                and curr_k > stoch_k_overbought
                and curr_adx < adx_max
            )

            if is_sell:
                take_profit_price = curr_mid
                stop_loss_price = curr_upper + (0.5 * bb_width)

                rsi_factor = max(0.0, min(1.0, (curr_rsi - rsi_overbought) / (100.0 - rsi_overbought)))
                stoch_factor = max(0.0, min(1.0, (curr_k - stoch_k_overbought) / (100.0 - stoch_k_overbought)))
                adx_factor = max(0.0, min(1.0, (adx_max - curr_adx) / adx_max))

                strength = round(
                    min(0.95, max(0.55, 0.60 + 0.15 * rsi_factor + 0.15 * stoch_factor + 0.10 * adx_factor)),
                    4,
                )

                reason = (
                    f"Mean Reversion SELL: Price ({close_p:.2f}) pierced upper band ({curr_upper:.2f}), "
                    f"RSI={curr_rsi:.1f} > {rsi_overbought}, StochK={curr_k:.1f} > {stoch_k_overbought}, "
                    f"ADX={curr_adx:.1f} < {adx_max}"
                )

                metadata = {
                    "take_profit_price": round(take_profit_price, 2),
                    "stop_loss_price": round(stop_loss_price, 2),
                    "bb_middle": round(curr_mid, 2),
                    "bb_upper": round(curr_upper, 2),
                    "bb_lower": round(curr_lower, 2),
                    "bb_width": round(bb_width, 2),
                    "rsi": round(curr_rsi, 2),
                    "stoch_k": round(curr_k, 2),
                    "adx": round(curr_adx, 2),
                }

                bot_logger.info(f"[{self.name}] {pair} -> SELL signal (strength={strength:.2f})")
                return StrategySignal(
                    pair=pair,
                    action="SELL",
                    strategy=self.name,
                    strength=strength,
                    reason=reason,
                    metadata=metadata,
                )

            return None

        except Exception as exc:
            bot_logger.error(f"[{self.name}] Analysis error on {pair}: {exc}")
            return None
