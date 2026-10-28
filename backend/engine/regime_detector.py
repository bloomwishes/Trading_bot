"""
AutoTrader Pro - Market Regime Detector
=========================================
Classifies cryptocurrency market regimes into discrete structural states:
  - TRENDING_UP: ADX > 25 AND +DI > -DI
  - TRENDING_DOWN: ADX > 25 AND -DI > +DI
  - RANGING: ADX < 20 AND Bollinger Bandwidth < 0.03
  - HIGH_VOLATILITY: ATR > 2x 20-period SMA of ATR OR Bollinger Bandwidth > 0.06
  - NEUTRAL: Transitional / sideways market between defined criteria

Provides an event subscription model allowing strategies to receive
immediate notifications when a pair shifts from one regime to another.
"""

from __future__ import annotations

import inspect
import threading
from typing import Any, Callable, Dict, List, Optional

import pandas as pd

from backend.engine.indicators import (
    calculate_adx,
    calculate_atr,
    calculate_bollinger_bands,
)
from backend.utils.logger import bot_logger


class MarketRegime:
    """Enumeration of market regimes."""

    TRENDING_UP = "TRENDING_UP"
    TRENDING_DOWN = "TRENDING_DOWN"
    RANGING = "RANGING"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    NEUTRAL = "NEUTRAL"


class MarketRegimeDetector:
    """Detects and monitors market regimes for cryptocurrency pairs."""

    def __init__(self) -> None:
        """Initialize detector with state tracking and subscription listeners."""
        self._last_regimes: Dict[str, str] = {}
        self._subscribers: List[Callable[[str, str, str, Dict[str, Any]], None]] = []
        self._lock = threading.Lock()

    def subscribe(
        self,
        callback: Callable[[str, str, str, Dict[str, Any]], None],
    ) -> None:
        """Subscribe a callback to regime transition events.

        Callback signature:
            callback(pair: str, old_regime: str, new_regime: str, details: dict)
        """
        with self._lock:
            if callback not in self._subscribers:
                self._subscribers.append(callback)

    def unsubscribe(
        self,
        callback: Callable[[str, str, str, Dict[str, Any]], None],
    ) -> None:
        """Unsubscribe a callback."""
        with self._lock:
            if callback in self._subscribers:
                self._subscribers.remove(callback)

    def _notify_regime_change(
        self, pair: str, old_regime: str, new_regime: str, details: Dict[str, Any]
    ) -> None:
        """Broadcast regime transition to all subscribers."""
        with self._lock:
            subs = list(self._subscribers)

        bot_logger.info(
            f"MarketRegimeDetector: Regime change for {pair}: {old_regime} -> {new_regime} "
            f"(confidence={details.get('confidence', 0):.2f})"
        )

        for sub in subs:
            try:
                if inspect.iscoroutinefunction(sub):
                    import asyncio
                    try:
                        loop = asyncio.get_running_loop()
                        asyncio.ensure_future(
                            sub(pair, old_regime, new_regime, details), loop=loop
                        )
                    except RuntimeError:
                        asyncio.run(sub(pair, old_regime, new_regime, details))
                else:
                    sub(pair, old_regime, new_regime, details)
            except Exception as exc:
                bot_logger.error(
                    f"Error in regime change subscriber callback: {exc}"
                )

    def get_last_regime(self, pair: str) -> Optional[str]:
        """Return the most recently recorded regime for *pair*."""
        with self._lock:
            return self._last_regimes.get(pair)

    def detect(self, pair: str, df: pd.DataFrame) -> Dict[str, Any]:
        """Classify current market regime from OHLCV candles.

        Classification Criteria:
          1. HIGH_VOLATILITY: ATR > 2x its 20-period SMA OR BB Bandwidth > 0.06
          2. TRENDING_UP: ADX > 25 AND +DI > -DI
          3. TRENDING_DOWN: ADX > 25 AND -DI > +DI
          4. RANGING: ADX < 20 AND BB Bandwidth < 0.03
          5. NEUTRAL: Transitional / Consolidation between thresholds

        Args:
            pair: Ticker pair identifier (e.g. 'BTC/INR').
            df: OHLCV DataFrame with required columns [timestamp, open, high, low, close, volume].

        Returns:
            Dict containing:
              - pair: str
              - regime: str
              - confidence: float (0.0 to 1.0)
              - adx: float
              - bb_width: float
              - atr_ratio: float (ATR / 20-period ATR SMA)
              - plus_di: float
              - minus_di: float
        """
        default_res = {
            "pair": pair,
            "regime": MarketRegime.NEUTRAL,
            "confidence": 0.5,
            "adx": 0.0,
            "bb_width": 0.0,
            "atr_ratio": 1.0,
            "plus_di": 0.0,
            "minus_di": 0.0,
        }

        if df is None or df.empty or len(df) < 35:
            bot_logger.warning(
                f"MarketRegimeDetector: Insufficient candles for {pair} (has {len(df) if df is not None else 0})"
            )
            return default_res

        try:
            # 1. ADX, +DI, -DI (period=14)
            adx_series, plus_di_series, minus_di_series = calculate_adx(df, period=14)
            adx = (
                float(adx_series.dropna().iloc[-1])
                if not adx_series.dropna().empty
                else 0.0
            )
            plus_di = (
                float(plus_di_series.dropna().iloc[-1])
                if not plus_di_series.dropna().empty
                else 0.0
            )
            minus_di = (
                float(minus_di_series.dropna().iloc[-1])
                if not minus_di_series.dropna().empty
                else 0.0
            )

            # 2. Bollinger Bandwidth (period=20, std=2) -> normalized (upper - lower) / middle
            upper_series, middle_series, lower_series, _ = calculate_bollinger_bands(
                df, period=20, std_dev=2
            )
            if not middle_series.dropna().empty and float(middle_series.dropna().iloc[-1]) > 0:
                u = float(upper_series.dropna().iloc[-1])
                m = float(middle_series.dropna().iloc[-1])
                l = float(lower_series.dropna().iloc[-1])
                bb_width = (u - l) / m
            else:
                bb_width = 0.0

            # 3. ATR & 20-period SMA of ATR
            atr_series = calculate_atr(df, period=14)
            if not atr_series.dropna().empty:
                current_atr = float(atr_series.dropna().iloc[-1])
                atr_sma_20 = atr_series.rolling(20, min_periods=10).mean()
                avg_atr = (
                    float(atr_sma_20.dropna().iloc[-1])
                    if not atr_sma_20.dropna().empty
                    else current_atr
                )
                atr_ratio = current_atr / avg_atr if avg_atr > 0 else 1.0
            else:
                atr_ratio = 1.0

            # ── Regime Classification Logic ──────────────────────────────
            regime = MarketRegime.NEUTRAL
            confidence = 0.50

            # Condition Flags
            is_high_vol = atr_ratio > 2.0 or bb_width > 0.06
            is_trending_up = adx > 25.0 and plus_di > minus_di
            is_trending_down = adx > 25.0 and minus_di > plus_di
            is_ranging = adx < 20.0 and bb_width < 0.03

            if is_high_vol:
                regime = MarketRegime.HIGH_VOLATILITY
                # Confidence based on excess volatility
                vol_score = max((atr_ratio - 1.0) / 2.0, (bb_width - 0.03) / 0.05)
                confidence = round(min(0.99, max(0.60, 0.60 + vol_score * 0.35)), 2)

            elif is_trending_up:
                regime = MarketRegime.TRENDING_UP
                # Confidence scales with ADX strength and DI divergence
                adx_factor = min(1.0, (adx - 20.0) / 30.0)
                di_spread = min(1.0, max(0.0, (plus_di - minus_di) / 25.0))
                confidence = round(min(0.99, 0.55 + 0.30 * adx_factor + 0.15 * di_spread), 2)

            elif is_trending_down:
                regime = MarketRegime.TRENDING_DOWN
                adx_factor = min(1.0, (adx - 20.0) / 30.0)
                di_spread = min(1.0, max(0.0, (minus_di - plus_di) / 25.0))
                confidence = round(min(0.99, 0.55 + 0.30 * adx_factor + 0.15 * di_spread), 2)

            elif is_ranging:
                regime = MarketRegime.RANGING
                # Confidence scales with compression (lower ADX & narrower BB)
                adx_compression = min(1.0, max(0.0, (20.0 - adx) / 10.0))
                bb_compression = min(1.0, max(0.0, (0.03 - bb_width) / 0.02))
                confidence = round(min(0.95, 0.60 + 0.20 * adx_compression + 0.20 * bb_compression), 2)

            else:
                # Transitional state (e.g. ADX 20-25 or mild volatility)
                regime = MarketRegime.NEUTRAL
                confidence = 0.50

            result = {
                "pair": pair,
                "regime": regime,
                "confidence": confidence,
                "adx": round(adx, 2),
                "bb_width": round(bb_width, 4),
                "atr_ratio": round(atr_ratio, 2),
                "plus_di": round(plus_di, 2),
                "minus_di": round(minus_di, 2),
            }

            # Check for regime change and trigger notifications
            with self._lock:
                old_regime = self._last_regimes.get(pair)
                self._last_regimes[pair] = regime

            if old_regime is not None and old_regime != regime:
                self._notify_regime_change(pair, old_regime, regime, result)

            return result

        except Exception as exc:
            bot_logger.error(
                f"MarketRegimeDetector: Failed to detect regime for {pair}: {exc}"
            )
            return default_res


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
regime_detector = MarketRegimeDetector()
