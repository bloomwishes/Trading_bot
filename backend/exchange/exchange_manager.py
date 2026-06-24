"""
AutoTrader Pro - Exchange Manager
Abstraction layer that tries CoinDCX first and falls back to Binance.
Includes 60-second market-data caching.
"""

from __future__ import annotations

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

    CACHE_TTL: int = 10  # seconds

    def __init__(self) -> None:
        self._coindcx = CoinDCXClient(
            api_key=settings.COINDCX_API_KEY,
            api_secret=settings.COINDCX_API_SECRET,
        )
        self._binance = BinanceFallbackClient(
            api_key=settings.BINANCE_API_KEY,
            api_secret=settings.BINANCE_API_SECRET,
        )

        # Simple in-memory cache: key → (timestamp, data)
        self._cache: Dict[str, tuple[float, Any]] = {}

    # ── Cache helpers ──────────────────────────────────────────────────
    def _cache_get(self, key: str) -> Any | None:
        entry = self._cache.get(key)
        if entry is None:
            return None
        ts, data = entry
        if time.monotonic() - ts > self.CACHE_TTL:
            del self._cache[key]
            return None
        return data

    def _cache_set(self, key: str, data: Any) -> None:
        self._cache[key] = (time.monotonic(), data)

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

    def get_candles(
        self,
        pair: str,
        interval: str = "15m",
        limit: int = 100,
    ) -> pd.DataFrame:
        cache_key = f"candles:{pair}:{interval}:{limit}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached
        data = self._try_primary_then_fallback("get_candles", pair, interval, limit)
        self._cache_set(cache_key, data)
        return data

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
