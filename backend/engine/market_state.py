"""
AutoTrader Pro - Enriched Market State & Builder
================================================
Defines the unified `MarketState` dataclass and `MarketStateBuilder` that
aggregates exchange price data, order book dynamics, technical indicators,
structural market regime, and macro crypto sentiment.

Replaces fragmented, redundant data fetches and calculations across individual
strategies with a single cohesive, high-performance data pipeline.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import threading
import time
from typing import Any, Dict, List, Optional

import pandas as pd
import requests

from backend.engine.indicators import (
    calculate_adx,
    calculate_atr,
    calculate_bollinger_bands,
    calculate_ema,
    calculate_keltner_channel,
    calculate_macd,
    calculate_momentum,
    calculate_obv,
    calculate_rsi,
    calculate_sma,
    calculate_stoch_rsi,
    calculate_supertrend,
    calculate_volume_sma,
    calculate_vwap,
    calculate_williams_r,
    detect_swing_highs,
    detect_swing_lows,
)
from backend.engine.regime_detector import regime_detector
from backend.exchange.exchange_manager import exchange_manager
from backend.utils.logger import bot_logger


# ---------------------------------------------------------------------------
# Macro Sentiment Fetcher (Fear & Greed + CoinGecko Global)
# ---------------------------------------------------------------------------
class ExternalSentimentFetcher:
    """Fetches and caches macro sentiment from Alternative.me and CoinGecko.

    Runs asynchronous/background refreshes with a 5-minute TTL so queries
    never block caller threads.
    """

    FNG_URL_PRIMARY = "https://api.alternative.me/fng/?limit=1"
    FNG_URL_FALLBACK = "https://api.alternative.me/fcc/"
    COINGECKO_GLOBAL_URL = "https://api.coingecko.com/api/v3/global"
    CACHE_TTL_SECONDS = 300.0  # 5 minutes

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._last_fetch_ts: float = 0.0
        self._is_fetching: bool = False
        self._cached_sentiment: Dict[str, Any] = {
            "fear_greed_index": 50,
            "fear_greed_label": "Neutral",
            "btc_dominance": 55.0,
            "total_market_cap_change_24h": 0.0,
            "sentiment_score": 0.0,
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }

    def _refresh_in_background(self) -> None:
        """Spawn daemon thread to update sentiment cache without blocking."""
        with self._lock:
            if self._is_fetching:
                return
            self._is_fetching = True

        def _worker() -> None:
            try:
                data = self._fetch_live()
                with self._lock:
                    self._cached_sentiment.update(data)
                    self._cached_sentiment["last_updated"] = datetime.now(
                        timezone.utc
                    ).isoformat()
                    self._last_fetch_ts = time.monotonic()
            except Exception as exc:
                bot_logger.error(f"ExternalSentimentFetcher background update error: {exc}")
            finally:
                with self._lock:
                    self._is_fetching = False

        t = threading.Thread(
            target=_worker, name="SentimentFetcher-Worker", daemon=True
        )
        t.start()

    def _fetch_live(self) -> Dict[str, Any]:
        """Directly query remote sentiment APIs."""
        fng_val = 50
        fng_label = "Neutral"

        # 1. Alternative.me Fear & Greed Index
        try:
            resp = requests.get(self.FNG_URL_PRIMARY, timeout=6)
            if resp.status_code == 200:
                data = resp.json().get("data", [])
                if data:
                    fng_val = int(data[0].get("value", 50))
                    fng_label = str(data[0].get("value_classification", "Neutral"))
            else:
                # Fallback URL attempt
                resp_fb = requests.get(self.FNG_URL_FALLBACK, timeout=6)
                if resp_fb.status_code == 200:
                    fb_data = resp_fb.json().get("data", [])
                    if fb_data:
                        fng_val = int(fb_data[0].get("value", 50))
                        fng_label = str(fb_data[0].get("value_classification", "Neutral"))
        except Exception as exc:
            bot_logger.warning(f"Failed to fetch Fear & Greed index: {exc}")

        # 2. CoinGecko Global Market Data
        btc_dom = 55.0
        mcap_chg_24h = 0.0
        try:
            resp_cg = requests.get(self.COINGECKO_GLOBAL_URL, timeout=6)
            if resp_cg.status_code == 200:
                cg_data = resp_cg.json().get("data", {})
                btc_dom = float(
                    cg_data.get("market_cap_percentage", {}).get("btc", 55.0)
                )
                mcap_chg_24h = float(
                    cg_data.get("market_cap_change_percentage_24h_usd", 0.0)
                )
        except Exception as exc:
            bot_logger.warning(f"Failed to fetch CoinGecko global stats: {exc}")

        # Normalized sentiment score between -1.0 and +1.0
        # (fng_val in [0, 100] -> -1.0 to +1.0)
        sentiment_score = round((fng_val - 50.0) / 50.0, 4)

        return {
            "fear_greed_index": fng_val,
            "fear_greed_label": fng_label,
            "btc_dominance": round(btc_dom, 2),
            "total_market_cap_change_24h": round(mcap_chg_24h, 2),
            "sentiment_score": sentiment_score,
        }

    def get_sentiment(self) -> Dict[str, Any]:
        """Return the latest cached sentiment stats, triggering background refresh if stale."""
        now = time.monotonic()
        if (
            self._last_fetch_ts == 0.0
            or now - self._last_fetch_ts > self.CACHE_TTL_SECONDS
        ):
            self._refresh_in_background()

        with self._lock:
            return dict(self._cached_sentiment)


# Singleton Sentiment Fetcher
sentiment_fetcher = ExternalSentimentFetcher()


# ---------------------------------------------------------------------------
# Enriched Market State Dataclass
# ---------------------------------------------------------------------------
@dataclass
class MarketState:
    """Comprehensive snapshot of market conditions for a single trading pair.

    Encapsulates price, raw OHLCV bars, calculated indicators, structural regime,
    order book micro-structure, volume analysis, and macro crypto sentiment.
    """

    pair: str
    timestamp: str
    price: float
    candles: pd.DataFrame  # OHLCV
    indicators: Dict[str, Any]  # All computed indicators
    regime: str  # From MarketRegimeDetector (e.g. TRENDING_UP)
    order_book_imbalance: float  # -1.0 to +1.0
    spread_pct: float  # Bid-Ask spread %
    volume_ratio: float  # Current bar volume / 20-period avg
    sentiment_score: Optional[float] = None  # Macro sentiment: -1.0 to +1.0
    regime_confidence: float = 0.5
    regime_details: Optional[Dict[str, Any]] = None

    def to_dict(
        self, include_candles: bool = False, candle_limit: int = 10
    ) -> Dict[str, Any]:
        """Convert MarketState to a JSON-serializable dictionary.

        Args:
            include_candles: If True, includes candle records in the output.
            candle_limit: Number of recent candles to serialize if enabled.
        """
        candles_payload: Any = None
        if include_candles and self.candles is not None and not self.candles.empty:
            tail_df = self.candles.tail(candle_limit).copy()
            # Convert timestamp to ISO string if needed
            if "timestamp" in tail_df.columns:
                tail_df["timestamp"] = tail_df["timestamp"].astype(str)
            candles_payload = tail_df.to_dict(orient="records")

        return {
            "pair": self.pair,
            "timestamp": self.timestamp,
            "price": self.price,
            "regime": self.regime,
            "regime_confidence": self.regime_confidence,
            "order_book_imbalance": self.order_book_imbalance,
            "spread_pct": self.spread_pct,
            "volume_ratio": self.volume_ratio,
            "sentiment_score": self.sentiment_score,
            "indicators": self.indicators,
            "regime_details": self.regime_details or {},
            "candles_count": len(self.candles) if self.candles is not None else 0,
            "candles": candles_payload,
        }


# ---------------------------------------------------------------------------
# Market State Builder
# ---------------------------------------------------------------------------
class MarketStateBuilder:
    """Builds a complete, enriched `MarketState` instance for any given pair."""

    @staticmethod
    def build(
        pair: str,
        interval: str = "15m",
        candle_limit: int = 100,
        exchange: Optional[Any] = None,
    ) -> MarketState:
        """Fetch all data components and construct an enriched MarketState.

        Args:
            pair: Standard pair identifier (e.g. 'BTC/INR').
            interval: Candlestick resolution ('1m', '5m', '15m', '1h', etc.).
            candle_limit: Number of lookback candles to fetch for indicator calculations.
            exchange: Optional ExchangeManager instance (defaults to module singleton).

        Returns:
            Fully populated MarketState object.
        """
        mgr = exchange or exchange_manager
        timestamp_str = datetime.now(timezone.utc).isoformat()

        # 1. Fetch OHLCV candles
        df, _ = mgr.get_candles_with_meta(pair, interval=interval, limit=candle_limit)

        # 2. Latest market price
        current_price = 0.0
        if df is not None and not df.empty and "close" in df.columns:
            current_price = float(df["close"].iloc[-1])

        if current_price <= 0.0:
            ticker = mgr.get_ticker(pair)
            current_price = float(ticker.get("last_price", 0.0))

        # 3. Compute indicators dictionary
        indicators: Dict[str, Any] = {}

        if df is not None and not df.empty and len(df) >= 20:
            try:
                # EMAs
                ema_9 = calculate_ema(df, 9)
                ema_21 = calculate_ema(df, 21)
                ema_50 = calculate_ema(df, 50)
                ema_200 = calculate_ema(df, 200)

                # SMAs
                sma_20 = calculate_sma(df, 20)
                sma_50 = calculate_sma(df, 50)

                # RSI & StochRSI
                rsi = calculate_rsi(df, 14)
                stoch_k, stoch_d = calculate_stoch_rsi(df, 14)

                # Bollinger Bands
                bb_u, bb_m, bb_l, bb_w = calculate_bollinger_bands(df, 20, 2)

                # ATR
                atr = calculate_atr(df, 14)

                # Volume SMA
                vol_sma = calculate_volume_sma(df, 20)

                # MACD
                macd_line, macd_sig, macd_hist = calculate_macd(df, 12, 26, 9)

                # ADX
                adx, plus_di, minus_di = calculate_adx(df, 14)

                # Supertrend
                st_line, st_dir = calculate_supertrend(df, 10, 3.0)

                # VWAP & OBV
                vwap = calculate_vwap(df)
                obv = calculate_obv(df)

                # Williams %R
                williams = calculate_williams_r(df, 14)

                # Keltner Channel
                kc_u, kc_m, kc_l = calculate_keltner_channel(df, 20, 1.5)

                # Momentum
                mom = calculate_momentum(df, 10)

                # Swing Highs & Lows
                swing_h = detect_swing_highs(df, window=5)
                swing_l = detect_swing_lows(df, window=5)

                def _last_val(s: pd.Series, default: float = 0.0) -> float:
                    if s is not None and not s.dropna().empty:
                        return round(float(s.dropna().iloc[-1]), 4)
                    return default

                indicators = {
                    "ema_9": _last_val(ema_9),
                    "ema_21": _last_val(ema_21),
                    "ema_50": _last_val(ema_50),
                    "ema_200": _last_val(ema_200),
                    "sma_20": _last_val(sma_20),
                    "sma_50": _last_val(sma_50),
                    "rsi": _last_val(rsi),
                    "stoch_rsi_k": _last_val(stoch_k),
                    "stoch_rsi_d": _last_val(stoch_d),
                    "bb_upper": _last_val(bb_u),
                    "bb_middle": _last_val(bb_m),
                    "bb_lower": _last_val(bb_l),
                    "bb_width": _last_val(bb_w),
                    "atr": _last_val(atr),
                    "volume_sma": _last_val(vol_sma),
                    "macd": _last_val(macd_line),
                    "macd_signal": _last_val(macd_sig),
                    "macd_histogram": _last_val(macd_hist),
                    "adx": _last_val(adx),
                    "plus_di": _last_val(plus_di),
                    "minus_di": _last_val(minus_di),
                    "supertrend": _last_val(st_line),
                    "supertrend_direction": int(_last_val(st_dir, default=1.0)),
                    "vwap": _last_val(vwap),
                    "obv": _last_val(obv),
                    "williams_r": _last_val(williams),
                    "keltner_upper": _last_val(kc_u),
                    "keltner_middle": _last_val(kc_m),
                    "keltner_lower": _last_val(kc_l),
                    "momentum": _last_val(mom),
                    "last_swing_high": swing_h[-1][1] if swing_h else None,
                    "last_swing_low": swing_l[-1][1] if swing_l else None,
                }
            except Exception as e:
                bot_logger.error(f"Error computing indicators for {pair}: {e}")

        # 4. Market Regime Detection
        regime_res = regime_detector.detect(pair, df)
        regime_label = regime_res.get("regime", "NEUTRAL")
        regime_confidence = regime_res.get("confidence", 0.5)

        # 5. Order Book Imbalance & Spread
        order_book_imbalance = mgr.get_order_book_imbalance(pair)
        spread_pct = mgr.get_spread_pct(pair)

        # 6. Volume Ratio (Current volume / 20-period volume SMA)
        volume_ratio = 1.0
        if df is not None and not df.empty and "volume" in df.columns:
            curr_vol = float(df["volume"].iloc[-1])
            vol_sma_val = indicators.get("volume_sma", 0.0)
            if vol_sma_val > 0:
                volume_ratio = round(curr_vol / vol_sma_val, 2)

        # 7. Macro Sentiment Score
        sentiment_data = sentiment_fetcher.get_sentiment()
        sentiment_score = sentiment_data.get("sentiment_score", 0.0)

        return MarketState(
            pair=pair,
            timestamp=timestamp_str,
            price=current_price,
            candles=df,
            indicators=indicators,
            regime=regime_label,
            regime_confidence=regime_confidence,
            regime_details=regime_res,
            order_book_imbalance=order_book_imbalance,
            spread_pct=spread_pct,
            volume_ratio=volume_ratio,
            sentiment_score=sentiment_score,
        )
