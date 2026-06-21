"""
AutoTrader Pro - Binance Fallback Exchange Wrapper
Uses ccxt to provide the same interface as the CoinDCX client.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

import ccxt
import pandas as pd

from backend.utils.logger import bot_logger


class BinanceFallbackClient:
    """Binance exchange wrapper via ccxt.

    Exposes the exact same public interface as CoinDCXClient so the two
    can be swapped transparently by ExchangeManager.

    Pair conversion: CoinDCX uses INR pairs, but Binance may not list
    them.  When the requested pair ends with "/INR" and is unavailable,
    the wrapper automatically tries the equivalent "/USDT" pair.
    """

    # Approximate INR/USDT rate (refreshed dynamically when possible)
    _INR_USDT_RATE: float = 83.0

    def __init__(self, api_key: str, api_secret: str) -> None:
        self.api_key = api_key
        self.api_secret = api_secret
        self._exchange = ccxt.binance(
            {
                "apiKey": api_key,
                "secret": api_secret,
                "enableRateLimit": True,
                "options": {"defaultType": "spot"},
            }
        )
        self._markets_loaded = False

    # ── Pair helpers ───────────────────────────────────────────────────
    def _ensure_markets(self) -> None:
        if not self._markets_loaded:
            try:
                self._exchange.load_markets()
                self._markets_loaded = True
            except Exception as exc:
                bot_logger.error(f"Binance load_markets failed: {exc}")

    def _resolve_pair(self, pair: str) -> str:
        """If the pair is not available on Binance, substitute /INR → /USDT."""
        self._ensure_markets()
        if pair in self._exchange.markets:
            return pair
        if pair.endswith("/INR"):
            usdt_pair = pair.replace("/INR", "/USDT")
            if usdt_pair in self._exchange.markets:
                return usdt_pair
        return pair  # let ccxt raise if truly unsupported

    def _to_inr(self, value: float, pair: str, resolved: str) -> float:
        """Convert a USDT value back to INR when a substitution was made."""
        if pair != resolved and resolved.endswith("/USDT"):
            return value * self._INR_USDT_RATE
        return value

    # ── Market data ────────────────────────────────────────────────────
    def get_markets(self) -> List[Dict[str, Any]]:
        """Return all available trading pairs."""
        try:
            self._ensure_markets()
            result: List[Dict[str, Any]] = []
            for symbol, market in self._exchange.markets.items():
                result.append(
                    {
                        "symbol": symbol,
                        "base": market.get("base", ""),
                        "quote": market.get("quote", ""),
                        "active": market.get("active", True),
                    }
                )
            return result
        except Exception as exc:
            bot_logger.error(f"Binance get_markets error: {exc}")
            return []

    def get_ticker(self, pair: str) -> Dict[str, Any]:
        """Fetch latest ticker data.

        Returns dict with: last_price, bid, ask, volume, change_24h
        """
        resolved = self._resolve_pair(pair)
        try:
            ticker = self._exchange.fetch_ticker(resolved)
            last = float(ticker.get("last", 0) or 0)
            bid = float(ticker.get("bid", 0) or 0)
            ask = float(ticker.get("ask", 0) or 0)
            volume = float(ticker.get("baseVolume", 0) or 0)
            change = float(ticker.get("percentage", 0) or 0)

            return {
                "last_price": self._to_inr(last, pair, resolved),
                "bid": self._to_inr(bid, pair, resolved),
                "ask": self._to_inr(ask, pair, resolved),
                "volume": volume,
                "change_24h": change,
            }
        except Exception as exc:
            bot_logger.error(f"Binance get_ticker({pair}) error: {exc}")
            return {"last_price": 0, "bid": 0, "ask": 0, "volume": 0, "change_24h": 0}

    def get_candles(
        self,
        pair: str,
        interval: str = "15m",
        limit: int = 100,
    ) -> pd.DataFrame:
        """Fetch OHLCV candles via ccxt.

        Returns DataFrame with columns: timestamp, open, high, low, close, volume
        """
        resolved = self._resolve_pair(pair)
        try:
            ohlcv = self._exchange.fetch_ohlcv(resolved, timeframe=interval, limit=limit)
            if not ohlcv:
                return pd.DataFrame(
                    columns=["timestamp", "open", "high", "low", "close", "volume"]
                )

            df = pd.DataFrame(
                ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"]
            )
            # Convert prices to INR if substituted
            if pair != resolved and resolved.endswith("/USDT"):
                for col in ["open", "high", "low", "close"]:
                    df[col] = df[col] * self._INR_USDT_RATE

            for col in ["open", "high", "low", "close", "volume"]:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

            return df
        except Exception as exc:
            bot_logger.error(f"Binance get_candles({pair}) error: {exc}")
            return pd.DataFrame(
                columns=["timestamp", "open", "high", "low", "close", "volume"]
            )

    # ── Account data ───────────────────────────────────────────────────
    def get_balances(self) -> Dict[str, Dict[str, float]]:
        """Return {currency: {available, locked}}."""
        try:
            balance = self._exchange.fetch_balance()
            result: Dict[str, Dict[str, float]] = {}
            for currency, info in balance.get("total", {}).items():
                total = float(info) if info else 0.0
                free = float(balance.get("free", {}).get(currency, 0) or 0)
                used = float(balance.get("used", {}).get(currency, 0) or 0)
                if total > 0:
                    result[currency.upper()] = {"available": free, "locked": used}
            return result
        except Exception as exc:
            bot_logger.error(f"Binance get_balances error: {exc}")
            return {}

    # ── Order management ───────────────────────────────────────────────
    def place_order(
        self,
        pair: str,
        side: str,
        quantity: float,
        price: Optional[float] = None,
        order_type: str = "market",
    ) -> Dict[str, Any]:
        """Place a market or limit order through Binance."""
        resolved = self._resolve_pair(pair)
        try:
            # Adjust price for USDT conversion if applicable
            adjusted_price = price
            if (
                price is not None
                and pair != resolved
                and resolved.endswith("/USDT")
            ):
                adjusted_price = price / self._INR_USDT_RATE

            if order_type == "market":
                order = self._exchange.create_market_order(
                    resolved, side.lower(), quantity
                )
            else:
                order = self._exchange.create_limit_order(
                    resolved, side.lower(), quantity, adjusted_price
                )

            bot_logger.info(
                f"Binance order placed: {side.upper()} {quantity} {pair} "
                f"type={order_type} → id={order.get('id', 'N/A')}"
            )
            return order
        except Exception as exc:
            bot_logger.error(f"Binance place_order error: {exc}")
            return {"error": str(exc)}

    def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order."""
        try:
            # ccxt needs the symbol; we iterate open orders to find it
            open_orders = self._exchange.fetch_open_orders()
            for o in open_orders:
                if str(o.get("id")) == str(order_id):
                    self._exchange.cancel_order(order_id, o.get("symbol"))
                    bot_logger.info(f"Binance order cancelled: {order_id}")
                    return True
            bot_logger.warning(f"Binance order {order_id} not found in open orders")
            return False
        except Exception as exc:
            bot_logger.error(f"Binance cancel_order({order_id}) error: {exc}")
            return False

    def get_order_status(self, order_id: str) -> Dict[str, Any]:
        """Fetch order status."""
        try:
            open_orders = self._exchange.fetch_open_orders()
            for o in open_orders:
                if str(o.get("id")) == str(order_id):
                    return o
            # Try closed orders
            closed_orders = self._exchange.fetch_closed_orders()
            for o in closed_orders:
                if str(o.get("id")) == str(order_id):
                    return o
            return {"error": "Order not found"}
        except Exception as exc:
            bot_logger.error(f"Binance get_order_status({order_id}) error: {exc}")
            return {"error": str(exc)}
