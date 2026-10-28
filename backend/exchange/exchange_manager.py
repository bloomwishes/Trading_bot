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
from backend.exchange.websocket_client import CoinDCXWebSocketClient
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

    def __init__(
        self,
        candle_ttl: Optional[int] = None,
        auto_start_ws: bool = True,
    ) -> None:
        self.candle_ttl: int = candle_ttl or self.DEFAULT_CANDLE_TTL
        self.market_ttl: int = self.DEFAULT_MARKET_TTL
        self.CACHE_TTL: int = self.candle_ttl
        self.watched_pairs: List[str] = list(
            getattr(settings, "WATCHED_PAIRS", ["BTC/INR", "ETH/INR", "SOL/INR", "XRP/INR", "BNB/INR"])
        )

        self._coindcx = CoinDCXClient(
            api_key=settings.COINDCX_API_KEY,
            api_secret=settings.COINDCX_API_SECRET,
        )
        self._binance = BinanceFallbackClient(
            api_key=settings.BINANCE_API_KEY,
            api_secret=settings.BINANCE_API_SECRET,
        )

        # Real-time WebSocket Client
        self._ws = CoinDCXWebSocketClient(pairs=self.watched_pairs)
        if auto_start_ws:
            try:
                self._ws.start_in_thread()
            except Exception as e:
                bot_logger.warning(f"Could not auto-start WebSocket client: {e}")

        # Simple in-memory cache: key → (mono_timestamp, data, utc_iso_fetch_time)
        self._cache: Dict[str, tuple[float, Any, str]] = {}
        self._cache_lock = threading.Lock()
        self._key_locks: Dict[str, threading.Lock] = {}
        self._key_locks_lock = threading.Lock()

    @property
    def is_ws_connected(self) -> bool:
        """Return True if WebSocket feed is currently live."""
        return self._ws.is_connected if self._ws else False

    def start_websocket(self) -> None:
        """Start the real-time WebSocket client thread if not running."""
        if self._ws:
            self._ws.start_in_thread()

    def stop_websocket(self) -> None:
        """Gracefully stop the WebSocket client."""
        if self._ws:
            self._ws.stop_thread()

    def subscribe_pair(self, pair: str) -> None:
        """Dynamically add pair to watchlist and WebSocket subscription."""
        if pair not in self.watched_pairs:
            self.watched_pairs.append(pair)
        if self._ws:
            self._ws.subscribe_pair(pair)

    def unsubscribe_pair(self, pair: str) -> None:
        """Dynamically remove pair from watchlist and WebSocket subscription."""
        if pair in self.watched_pairs:
            self.watched_pairs.remove(pair)
        if self._ws:
            self._ws.unsubscribe_pair(pair)

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
        """Return latest ticker for *pair*.

        Checks WebSocket real-time feed first, falls back to REST cache.
        """
        # 1. Real-time WebSocket feed
        if self._ws and self._ws.is_connected:
            ws_ticker = self._ws.get_ticker(pair, max_age_seconds=15.0)
            if ws_ticker and ws_ticker.get("last_price", 0) > 0:
                return ws_ticker

        # 2. REST cache fallback
        cache_key = f"ticker:{pair}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached
        data = self._try_primary_then_fallback("get_ticker", pair)
        self._cache_set(cache_key, data)
        return data

    def get_order_book(self, pair: str, limit: int = 20) -> Dict[str, Any]:
        """Fetch top bids and asks (top 20) with quantities.

        Uses real-time WebSocket feed if connected and fresh, falls back to REST.
        """
        # 1. Try WebSocket feed
        if self._ws and self._ws.is_connected:
            ws_ob = self._ws.get_order_book(pair, max_age_seconds=15.0)
            if (
                ws_ob
                and len(ws_ob.get("bids", [])) > 0
                and len(ws_ob.get("asks", [])) > 0
            ):
                return {
                    "bids": ws_ob["bids"][:limit],
                    "asks": ws_ob["asks"][:limit],
                    "timestamp": ws_ob.get("timestamp"),
                    "source": "websocket",
                }

        # 2. REST API fallback with concurrency lock
        cache_key = f"orderbook:{pair}:{limit}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        key_lock = self._get_key_lock(cache_key)
        with key_lock:
            cached = self._cache_get(cache_key)
            if cached is not None:
                return cached

            data = self._try_primary_then_fallback("get_order_book", pair, limit)
            data["source"] = "rest"
            self._cache_set_entry(cache_key, data)
            return data

    def get_order_book_imbalance(self, pair: str) -> float:
        """Calculate Order Book Imbalance between top-20 bids and asks.

        Formula:
            (Bid_Volume - Ask_Volume) / (Bid_Volume + Ask_Volume)

        Returns:
            Float between -1.0 (all sell pressure) and +1.0 (all buy pressure).
        """
        try:
            ob = self.get_order_book(pair, limit=20)
            bids = ob.get("bids", [])
            asks = ob.get("asks", [])
            if not bids and not asks:
                return 0.0

            bid_vol = sum(float(b[1]) for b in bids)
            ask_vol = sum(float(a[1]) for a in asks)
            total_vol = bid_vol + ask_vol
            if total_vol <= 0:
                return 0.0

            imbalance = (bid_vol - ask_vol) / total_vol
            return round(max(-1.0, min(1.0, imbalance)), 4)
        except Exception as exc:
            bot_logger.error(
                f"ExchangeManager: Error computing order book imbalance for {pair}: {exc}"
            )
            return 0.0

    def get_spread_pct(self, pair: str) -> float:
        """Calculate bid-ask spread as a percentage: ((ask - bid) / ask) * 100."""
        try:
            ob = self.get_order_book(pair, limit=1)
            bids = ob.get("bids", [])
            asks = ob.get("asks", [])
            if bids and asks:
                best_bid = float(bids[0][0])
                best_ask = float(asks[0][0])
                if best_ask > 0 and best_bid > 0 and best_ask >= best_bid:
                    return round(((best_ask - best_bid) / best_ask) * 100.0, 4)

            # Fallback to ticker bid/ask
            ticker = self.get_ticker(pair)
            bid = float(ticker.get("bid", 0.0))
            ask = float(ticker.get("ask", 0.0))
            if ask > 0 and bid > 0 and ask >= bid:
                return round(((ask - bid) / ask) * 100.0, 4)
            return 0.0
        except Exception as exc:
            bot_logger.error(
                f"ExchangeManager: Error computing spread percentage for {pair}: {exc}"
            )
            return 0.0

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

    def round_quantity(self, pair: str, quantity: float) -> float:
        """Round order quantity to active exchange precision and step size."""
        if hasattr(self._coindcx, "round_quantity"):
            return self._coindcx.round_quantity(pair, quantity)
        return round(float(quantity), 6)

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
exchange_manager = ExchangeManager(auto_start_ws=False)
