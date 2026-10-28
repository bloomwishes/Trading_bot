"""
AutoTrader Pro - High-Frequency Scalping Strategy
=================================================
Ultra-short duration scalping based on microstructural order book imbalance,
VWAP deviations, momentum direction, and bid-ask spread limits.

Entry Logic:
  - BUY: ob_imbalance > 0.6
         AND price <= VWAP * 1.001
         AND momentum > 0
         AND RSI < 60
         AND spread_pct < 0.1%
  - SELL: ob_imbalance < -0.6
          AND price >= VWAP * 0.999
          AND momentum < 0
          AND RSI > 40
          AND spread_pct < 0.1%

Risk Parameters:
  - Take Profit: 0.4% (configurable 0.3% - 0.5%)
  - Stop Loss: 0.2% from entry
  - Max Hold Duration: 300 seconds (5 minutes)
"""

from __future__ import annotations

from typing import Optional, Dict, Any
import pandas as pd

from backend.engine.strategy_base import StrategyBase, StrategySignal
from backend.engine.indicators import (
    calculate_vwap,
    calculate_momentum,
    calculate_rsi,
)
from backend.utils.logger import bot_logger


class ScalpingStrategy(StrategyBase):
    """
    Order book microstructure scalping strategy for liquid crypto pairs.
    """

    DEFAULT_PARAMS: Dict[str, Any] = {
        "min_imbalance": 0.6,
        "max_spread_pct": 0.001,  # 0.1% (0.001 in decimal, 0.1 in percent)
        "tp_pct": 0.004,          # 0.4% take profit
        "sl_pct": 0.002,          # 0.2% stop loss
        "max_hold_seconds": 300,  # 5 minutes maximum trade life
        "rsi_period": 14,
        "mom_period": 10,
    }

    def __init__(
        self,
        name: str = "Scalping",
        exchange_manager: Optional[Any] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Initialize the scalping strategy with optional exchange manager handle."""
        merged = {**self.DEFAULT_PARAMS, **(params or {})}
        super().__init__(name=name, default_params=merged)
        self.exchange_manager = exchange_manager

    def set_exchange_manager(self, exchange_manager: Any) -> None:
        """Set or update the active ExchangeManager instance."""
        self.exchange_manager = exchange_manager

    def analyze(self, df: pd.DataFrame, pair: str) -> Optional[StrategySignal]:
        """
        Analyze candle and order book metrics to detect micro-scalping entries.

        Args:
            df: OHLCV DataFrame with columns [timestamp, open, high, low, close, volume].
            pair: Trading pair symbol (e.g. 'BTC/INR').

        Returns:
            StrategySignal if scalping setup is active, else None.
        """
        if df is None or len(df) < 15:
            return None

        min_imbalance = float(self.params.get("min_imbalance", 0.6))
        raw_spread_max = float(self.params.get("max_spread_pct", 0.001))
        # Handle decimal (0.001) vs percentage (0.1) representations
        spread_max_pct = raw_spread_max * 100.0 if raw_spread_max < 0.05 else raw_spread_max
        tp_pct = float(self.params.get("tp_pct", 0.004))
        sl_pct = float(self.params.get("sl_pct", 0.002))
        max_hold_sec = int(self.params.get("max_hold_seconds", 300))
        rsi_period = int(self.params.get("rsi_period", 14))
        mom_period = int(self.params.get("mom_period", 10))

        try:
            # 1. Fetch Order Book Imbalance and Bid-Ask Spread from ExchangeManager
            ob_imbalance = 0.0
            spread_pct = 0.0

            if self.exchange_manager:
                if hasattr(self.exchange_manager, "get_order_book_imbalance"):
                    try:
                        ob_imbalance = float(self.exchange_manager.get_order_book_imbalance(pair))
                    except Exception as e:
                        bot_logger.debug(f"[{self.name}] Could not get order book imbalance for {pair}: {e}")

                if hasattr(self.exchange_manager, "get_spread_pct"):
                    try:
                        spread_pct = float(self.exchange_manager.get_spread_pct(pair))
                    except Exception as e:
                        bot_logger.debug(f"[{self.name}] Could not get spread percentage for {pair}: {e}")

            # Spread filter: must be tight (< 0.1%)
            if spread_pct > spread_max_pct:
                bot_logger.debug(
                    f"[{self.name}] Spread for {pair} ({spread_pct:.4f}%) exceeds max ({spread_max_pct:.4f}%)"
                )
                return None

            # 2. Compute technical indicators
            close_p = float(df["close"].iloc[-1])
            vwap_series = calculate_vwap(df)
            mom_series = calculate_momentum(df, period=mom_period)
            rsi_series = calculate_rsi(df, period=rsi_period)

            if vwap_series.empty or mom_series.empty or rsi_series.empty:
                return None

            curr_vwap = float(vwap_series.dropna().iloc[-1])
            curr_mom = float(mom_series.dropna().iloc[-1])
            curr_rsi = float(rsi_series.dropna().iloc[-1])

            if curr_vwap <= 0:
                return None

            # 3. BUY Entry Criteria:
            # ob_imbalance > 0.6 AND price <= VWAP * 1.001 AND momentum > 0 AND RSI < 60 AND spread_pct < 0.1%
            is_buy = (
                ob_imbalance > min_imbalance
                and close_p <= (curr_vwap * 1.001)
                and curr_mom > 0.0
                and curr_rsi < 60.0
                and spread_pct <= spread_max_pct
            )

            if is_buy:
                take_profit_price = close_p * (1.0 + tp_pct)
                stop_loss_price = close_p * (1.0 - sl_pct)

                imbalance_factor = max(0.0, min(1.0, (ob_imbalance - min_imbalance) / (1.0 - min_imbalance)))
                strength = round(min(0.95, max(0.55, 0.60 + 0.25 * imbalance_factor + 0.10 * (curr_mom > 0))), 4)

                reason = (
                    f"Scalping BUY: Orderbook Imbalance={ob_imbalance:+.2f} > {min_imbalance}, "
                    f"Price ({close_p:.2f}) <= VWAP*1.001 ({curr_vwap * 1.001:.2f}), "
                    f"Mom={curr_mom:.2f} > 0, RSI={curr_rsi:.1f} < 60, Spread={spread_pct:.3f}%"
                )

                metadata = {
                    "take_profit_price": round(take_profit_price, 2),
                    "stop_loss_price": round(stop_loss_price, 2),
                    "max_hold_seconds": max_hold_sec,
                    "order_book_imbalance": round(ob_imbalance, 4),
                    "spread_pct": round(spread_pct, 4),
                    "vwap": round(curr_vwap, 2),
                    "momentum": round(curr_mom, 2),
                    "rsi": round(curr_rsi, 2),
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

            # 4. SELL Entry Criteria:
            # ob_imbalance < -0.6 AND price >= VWAP * 0.999 AND momentum < 0 AND RSI > 40 AND spread_pct < 0.1%
            is_sell = (
                ob_imbalance < -min_imbalance
                and close_p >= (curr_vwap * 0.999)
                and curr_mom < 0.0
                and curr_rsi > 40.0
                and spread_pct <= spread_max_pct
            )

            if is_sell:
                take_profit_price = close_p * (1.0 - tp_pct)
                stop_loss_price = close_p * (1.0 + sl_pct)

                imbalance_factor = max(0.0, min(1.0, (-ob_imbalance - min_imbalance) / (1.0 - min_imbalance)))
                strength = round(min(0.95, max(0.55, 0.60 + 0.25 * imbalance_factor + 0.10 * (curr_mom < 0))), 4)

                reason = (
                    f"Scalping SELL: Orderbook Imbalance={ob_imbalance:+.2f} < -{min_imbalance}, "
                    f"Price ({close_p:.2f}) >= VWAP*0.999 ({curr_vwap * 0.999:.2f}), "
                    f"Mom={curr_mom:.2f} < 0, RSI={curr_rsi:.1f} > 40, Spread={spread_pct:.3f}%"
                )

                metadata = {
                    "take_profit_price": round(take_profit_price, 2),
                    "stop_loss_price": round(stop_loss_price, 2),
                    "max_hold_seconds": max_hold_sec,
                    "order_book_imbalance": round(ob_imbalance, 4),
                    "spread_pct": round(spread_pct, 4),
                    "vwap": round(curr_vwap, 2),
                    "momentum": round(curr_mom, 2),
                    "rsi": round(curr_rsi, 2),
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
