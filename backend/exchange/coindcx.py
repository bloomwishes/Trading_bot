"""
AutoTrader Pro - CoinDCX Exchange Wrapper
Full REST API client with HMAC-SHA256 signing and rate limiting.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pandas as pd
import requests

from backend.utils.logger import bot_logger


class CoinDCXClient:
    """Wrapper around the CoinDCX REST API.

    Docs: https://docs.coindcx.com/
    Base URL: https://api.coindcx.com
    """

    BASE_URL = "https://api.coindcx.com"
    MAX_REQUESTS_PER_SECOND = 10

    # CoinDCX interval mapping
    _INTERVAL_MAP: Dict[str, str] = {
        "1m": "1m",
        "5m": "5m",
        "15m": "15m",
        "30m": "30m",
        "1h": "1h",
        "2h": "2h",
        "4h": "4h",
        "1d": "1d",
        "1w": "1w",
    }

    def __init__(self, api_key: str, api_secret: str) -> None:
        self.api_key = api_key
        self.api_secret = api_secret
        self._session = requests.Session()
        self._last_request_ts: float = 0.0
        self._request_count_window: List[float] = []

    # ── Request helpers ────────────────────────────────────────────────
    def _rate_limit(self) -> None:
        """Simple sliding-window rate limiter: max 10 req/s."""
        now = time.monotonic()
        # Purge timestamps older than 1 second
        self._request_count_window = [
            ts for ts in self._request_count_window if now - ts < 1.0
        ]
        if len(self._request_count_window) >= self.MAX_REQUESTS_PER_SECOND:
            sleep_time = 1.0 - (now - self._request_count_window[0])
            if sleep_time > 0:
                time.sleep(sleep_time)
        self._request_count_window.append(time.monotonic())

    def _sign(self, body: dict) -> Dict[str, str]:
        """Create HMAC-SHA256 signature headers for authenticated endpoints."""
        json_body = json.dumps(body, separators=(",", ":"))
        signature = hmac.new(
            self.api_secret.encode("utf-8"),
            json_body.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return {
            "Content-Type": "application/json",
            "X-AUTH-APIKEY": self.api_key,
            "X-AUTH-SIGNATURE": signature,
        }

    def _public_get(self, path: str, params: Optional[dict] = None) -> Any:
        """Unauthenticated GET request."""
        self._rate_limit()
        url = f"{self.BASE_URL}{path}"
        try:
            resp = self._session.get(url, params=params, timeout=15)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            bot_logger.error(f"CoinDCX GET {path} failed: {exc}")
            raise

    def _private_post(self, path: str, body: dict) -> Any:
        """Authenticated POST request with HMAC-SHA256 signature."""
        self._rate_limit()
        url = f"{self.BASE_URL}{path}"
        headers = self._sign(body)
        try:
            resp = self._session.post(
                url, data=json.dumps(body, separators=(",", ":")),
                headers=headers, timeout=15,
            )
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            bot_logger.error(f"CoinDCX POST {path} failed: {exc}")
            raise

    # ── Market data (public) ───────────────────────────────────────────
    def get_markets(self) -> List[Dict[str, Any]]:
        """Return all available trading pairs."""
        try:
            data = self._public_get("/exchange/v1/markets_details")
            return data
        except Exception as exc:
            bot_logger.error(f"CoinDCX get_markets error: {exc}")
            return []

    def get_ticker(self, pair: str) -> Dict[str, Any]:
        """Return latest ticker for *pair* (e.g. 'BTC/INR' → 'BTCINR').

        Returns dict with keys: last_price, bid, ask, volume, change_24h
        """
        symbol = pair.replace("/", "").upper()
        try:
            tickers = self._public_get("/exchange/ticker")
            for t in tickers:
                market = t.get("market", "").upper()
                if market == symbol:
                    return {
                        "last_price": float(t.get("last_price", 0)),
                        "bid": float(t.get("bid", 0)),
                        "ask": float(t.get("ask", 0)),
                        "volume": float(t.get("volume", 0)),
                        "change_24h": float(t.get("change_24_hour", 0)),
                    }
            bot_logger.warning(f"CoinDCX ticker not found for {pair}")
            return {"last_price": 0, "bid": 0, "ask": 0, "volume": 0, "change_24h": 0}
        except Exception as exc:
            bot_logger.error(f"CoinDCX get_ticker({pair}) error: {exc}")
            return {"last_price": 0, "bid": 0, "ask": 0, "volume": 0, "change_24h": 0}

    # Public market-data lives on a separate host from the trading API.
    PUBLIC_BASE_URL = "https://public.coindcx.com"

    def get_candles(
        self,
        pair: str,
        interval: str = "15m",
        limit: int = 100,
    ) -> pd.DataFrame:
        """Fetch OHLCV candles and return a DataFrame.

        Columns: timestamp, open, high, low, close, volume

        Note: raises on failure so ExchangeManager can fall back to Binance.
        Callers (e.g. TradingEngine) are responsible for catching exceptions.
        """
        base, _, quote = pair.replace("-", "/").partition("/")
        if not quote:
            # No separator found; assume last 3 chars are the quote currency
            base, quote = pair[:-3], pair[-3:]
        prefix = "I" if quote.upper() == "INR" else "B"
        market_pair = f"{prefix}-{base.upper()}_{quote.upper()}"
        mapped_interval = self._INTERVAL_MAP.get(interval, interval)

        self._rate_limit()
        candle_url = f"{self.PUBLIC_BASE_URL}/market_data/candles"
        resp = self._session.get(
            candle_url,
            params={
                "pair": market_pair,
                "interval": mapped_interval,
                "limit": str(limit),
            },
            timeout=15,
        )
        resp.raise_for_status()
        raw = resp.json()

        if isinstance(raw, list) and len(raw) > 0:
            df = pd.DataFrame(raw)
            df = df.rename(columns={"time": "timestamp"})
            for col in ["timestamp", "open", "high", "low", "close", "volume"]:
                if col not in df.columns:
                    df[col] = 0.0
            df = df[["timestamp", "open", "high", "low", "close", "volume"]]
            for col in ["open", "high", "low", "close", "volume"]:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
            # CoinDCX returns candles newest-first; re-sort ascending.
            df = df.sort_values("timestamp").reset_index(drop=True)
            return df

        # Return empty frame if nothing came back (not an error, just no data)
        return pd.DataFrame(
            columns=["timestamp", "open", "high", "low", "close", "volume"]
        )

    # ── Account data (private) ─────────────────────────────────────────
    def get_balances(self) -> Dict[str, Dict[str, float]]:
        """Return {currency: {available, locked}} for every non-zero balance."""
        try:
            body: dict = {"timestamp": int(time.time() * 1000)}
            data = self._private_post("/exchange/v1/users/balances", body)
            result: Dict[str, Dict[str, float]] = {}
            for item in data:
                currency = item.get("currency", "").upper()
                available = float(item.get("balance", 0))
                locked = float(item.get("locked_balance", 0))
                if available > 0 or locked > 0:
                    result[currency] = {"available": available, "locked": locked}
            return result
        except Exception as exc:
            bot_logger.error(f"CoinDCX get_balances error: {exc}")
            return {}

    # ── Order management (private) ─────────────────────────────────────
    def place_order(
        self,
        pair: str,
        side: str,
        quantity: float,
        price: Optional[float] = None,
        order_type: str = "market",
    ) -> Dict[str, Any]:
        """Place a market or limit order.

        Returns the order dict from CoinDCX.
        """
        symbol = pair.replace("/", "").upper()
        body: Dict[str, Any] = {
            "market": f"B-{symbol}",
            "side": side.lower(),
            "order_type": "market_order" if order_type == "market" else "limit_order",
            "total_quantity": quantity,
            "timestamp": int(time.time() * 1000),
        }
        if price is not None and order_type != "market":
            body["price_per_unit"] = price

        try:
            data = self._private_post("/exchange/v1/orders/create", body)
            bot_logger.info(
                f"CoinDCX order placed: {side.upper()} {quantity} {pair} "
                f"type={order_type} → id={data.get('id', 'N/A')}"
            )
            return data
        except Exception as exc:
            bot_logger.error(f"CoinDCX place_order error: {exc}")
            return {"error": str(exc)}

    def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order by its ID."""
        try:
            body = {
                "id": order_id,
                "timestamp": int(time.time() * 1000),
            }
            self._private_post("/exchange/v1/orders/cancel", body)
            bot_logger.info(f"CoinDCX order cancelled: {order_id}")
            return True
        except Exception as exc:
            bot_logger.error(f"CoinDCX cancel_order({order_id}) error: {exc}")
            return False

    def get_order_status(self, order_id: str) -> Dict[str, Any]:
        """Fetch current status of an order."""
        try:
            body = {
                "id": order_id,
                "timestamp": int(time.time() * 1000),
            }
            data = self._private_post("/exchange/v1/orders/status", body)
            return data
        except Exception as exc:
            bot_logger.error(f"CoinDCX get_order_status({order_id}) error: {exc}")
            return {"error": str(exc)}
