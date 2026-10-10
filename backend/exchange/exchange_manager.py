"""
AutoTrader Pro - Exchange Manager
Abstraction layer that tries CoinDCX first and falls back to Binance.
Includes 60-second market-data caching.
"""

from __future__ import annotations

from datetime import datetime, timezone
import threading
import time
from typing import Any, Dict, List, Optional

import pandas as pd

from backend.config import settings
from backend.exchange.coindcx import CoinDCXClient
from backend.exchange.binance_fallback import BinanceFallbackClient
from backend.utils.logger import bot_logger


class ExchangeManager:
    """Unified exchange gateway.

    * All calls attempt CoinDCX first.
    * On any exception the call is retried through the Binance fallback.
    * Ticker and market-list results are cached for 60 s to reduce API load.
    """

    DEFAULT_CANDLE_TTL: int = int(getattr(settings, "CANDLE_CACHE_TTL_SEC", 15))
    DEFAULT_MARKET_TTL: int = int(getattr(settings, "MARKET_DATA_CACHE_TTL_SEC", 15))
    CACHE_TTL: int = 15  # backward-compatibility constant

    def __init__(self, candle_ttl: Optional[int] = None) -> None:
        self.candle_ttl: int = candle_ttl or self.DEFAULT_CANDLE_TTL
        self.market_ttl: int = self.DEFAULT_MARKET_TTL
        self.CACHE_TTL: int = self.candle_ttl

        self._coindcx = CoinDCXClient(
            api_key=settings.COINDCX_API_KEY,
            api_secret=settings.COINDCX_API_SECRET,
        )
        self._binance = BinanceFallbackClient(
            api_key=settings.BINANCE_API_KEY,
            api_secret=settings.BINANCE_API_SECRET,
        )

        # Simple in-memory cache: key → (mono_timestamp, data, utc_iso_fetch_time)
        self._cache: Dict[str, tuple[float, Any, str]] = {}
        self._cache_lock = threading.Lock()
        self._key_locks: Dict[str, threading.Lock] = {}
        self._key_locks_lock = threading.Lock()

    def _get_key_lock(self, key: str) -> threading.Lock:
        with self._key_locks_lock:
            if key not in self._key_locks:
                self._key_locks[key] = threading.Lock()
            return self._key_locks[key]

    # ── Cache helpers ──────────────────────────────────────────────────
    def _cache_get_entry(self, key: str, ttl: Optional[int] = None) -> Optional[tuple[float, Any, str]]:
        max_age = ttl if ttl is not None else self.candle_ttl
        with self._cache_lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            ts, data, fetch_time = entry
            if time.monotonic() - ts > max_age:
                del self._cache[key]
                return None
            return entry

    def _cache_set_entry(self, key: str, data: Any) -> str:
        fetch_time = datetime.now(timezone.utc).isoformat()
        with self._cache_lock:
            self._cache[key] = (time.monotonic(), data, fetch_time)
        return fetch_time

    def _cache_get(self, key: str) -> Any | None:
        entry = self._cache_get_entry(key)
        return entry[1] if entry is not None else None

    def _cache_set(self, key: str, data: Any) -> None:
        self._cache_set_entry(key, data)

    # ── Dual-exchange dispatch ─────────────────────────────────────────
    def _try_primary_then_fallback(
        self,
        method_name: str,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Call *method_name* on CoinDCX; if it raises, retry on Binance."""
        try:
            result = getattr(self._coindcx, method_name)(*args, **kwargs)
            bot_logger.debug(f"ExchangeManager: {method_name} served by CoinDCX")
            return result
        except Exception as exc:
            bot_logger.warning(
                f"ExchangeManager: CoinDCX.{method_name} failed ({exc}), "
                "falling back to Binance"
            )
            try:
                result = getattr(self._binance, method_name)(*args, **kwargs)
                bot_logger.debug(
                    f"ExchangeManager: {method_name} served by Binance fallback"
                )
                return result
            except Exception as fb_exc:
                bot_logger.error(
                    f"ExchangeManager: Binance.{method_name} also failed: {fb_exc}"
                )
                raise

    # ── Public API (same signature as individual wrappers) ─────────────
    def get_markets(self) -> List[Dict[str, Any]]:
        cached = self._cache_get("markets")
        if cached is not None:
            return cached
        data = self._try_primary_then_fallback("get_markets")
        self._cache_set("markets", data)
        return data

    def get_ticker(self, pair: str) -> Dict[str, Any]:
        cache_key = f"ticker:{pair}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached
        data = self._try_primary_then_fallback("get_ticker", pair)
        self._cache_set(cache_key, data)
        return data

    def get_candles_with_meta(
        self,
        pair: str,
        interval: str = "15m",
        limit: int = 100,
        ttl: Optional[int] = None,
    ) -> tuple[pd.DataFrame, Dict[str, Any]]:
        """Fetch OHLCV candles with freshness metadata and single-flight concurrency protection."""
        effective_ttl = ttl if ttl is not None else self.candle_ttl
        cache_key = f"candles:{pair}:{interval}:{limit}"

        # 1. Fast path: check cache without acquiring key lock
        entry = self._cache_get_entry(cache_key, ttl=effective_ttl)
        if entry is not None:
            ts, data, fetch_time = entry
            age = time.monotonic() - ts
            df_copy = data.copy() if hasattr(data, "copy") else data
            return df_copy, {
                "is_cache_hit": True,
                "cache_age_seconds": round(age, 2),
                "fetch_timestamp": fetch_time,
                "cache_ttl": effective_ttl,
            }

        # 2. Slow path: single-flight lock per key to prevent duplicate exchange calls
        key_lock = self._get_key_lock(cache_key)
        with key_lock:
            # Double check if another thread fetched it while we waited
            entry = self._cache_get_entry(cache_key, ttl=effective_ttl)
            if entry is not None:
                ts, data, fetch_time = entry
                age = time.monotonic() - ts
                df_copy = data.copy() if hasattr(data, "copy") else data
                return df_copy, {
                    "is_cache_hit": True,
                    "cache_age_seconds": round(age, 2),
                    "fetch_timestamp": fetch_time,
                    "cache_ttl": effective_ttl,
                }

            # Only one thread executes the physical exchange fetch
            data = self._try_primary_then_fallback("get_candles", pair, interval, limit)
            fetch_time = self._cache_set_entry(cache_key, data)
            df_copy = data.copy() if hasattr(data, "copy") else data
            return df_copy, {
                "is_cache_hit": False,
                "cache_age_seconds": 0.0,
                "fetch_timestamp": fetch_time,
                "cache_ttl": effective_ttl,
            }

    def get_candles(
        self,
        pair: str,
        interval: str = "15m",
        limit: int = 100,
        ttl: Optional[int] = None,
    ) -> pd.DataFrame:
        df, _ = self.get_candles_with_meta(pair, interval, limit, ttl=ttl)
        return df

    def get_balances(self) -> Dict[str, Dict[str, float]]:
        return self._try_primary_then_fallback("get_balances")

    def place_order(
        self,
        pair: str,
        side: str,
        quantity: float,
        price: Optional[float] = None,
        order_type: str = "market",
    ) -> Dict[str, Any]:
        return self._try_primary_then_fallback(
            "place_order", pair, side, quantity, price, order_type
        )

    def cancel_order(self, order_id: str) -> bool:
        return self._try_primary_then_fallback("cancel_order", order_id)

    def get_order_status(self, order_id: str) -> Dict[str, Any]:
        return self._try_primary_then_fallback("get_order_status", order_id)

    # ── Convenience ────────────────────────────────────────────────────
    def get_current_prices(self, pairs: Optional[List[str]] = None) -> Dict[str, float]:
        """Return {pair: last_price} for the given pairs (default: watched pairs)."""
        if pairs is None:
            pairs = settings.WATCHED_PAIRS
        prices: Dict[str, float] = {}
        for pair in pairs:
            ticker = self.get_ticker(pair)
            prices[pair] = ticker.get("last_price", 0.0)
        return prices

    def clear_cache(self) -> None:
        """Flush the entire in-memory cache."""
        self._cache.clear()
        bot_logger.debug("ExchangeManager cache cleared")


# ---------------------------------------------------------------------------
# Module-level singleton (lazy; created on first import)
# ---------------------------------------------------------------------------
exchange_manager = ExchangeManager()
