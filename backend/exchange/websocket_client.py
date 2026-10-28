"""
AutoTrader Pro - CoinDCX WebSocket Real-Time Client
====================================================
Connects to CoinDCX WebSocket streaming service (wss://stream.coindcx.com)
using Socket.IO (EIO=4) protocol over websockets.

Streams:
  - Tickers (latest prices, 24h change, volume)
  - Order Book (depth-update-20, top 20 bids/asks)
  - Trades (real-time executions)
  - Klines / Candlesticks (1m, 5m, 15m)

Features:
  - Exponential backoff reconnection (1s -> 2s -> 4s -> 8s -> 16s -> max 30s)
  - Thread-safe data stores for concurrent access by REST / strategies
  - Callback dispatch for async/sync listeners
  - Clean start_in_thread() runner for synchronous application lifecycle
"""

from __future__ import annotations

import asyncio
from collections import deque
import inspect
import json
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

import websockets

from backend.utils.logger import bot_logger


def _normalize_pair(pair: str) -> str:
    """Normalize pair representation (e.g., 'BTC_INR', 'BTCINR', 'I-BTC_INR' -> 'BTC/INR')."""
    p = pair.strip().upper()
    if "/" in p:
        return p
    if p.startswith("I-") or p.startswith("B-"):
        p = p[2:]
    if "_" in p:
        base, quote = p.split("_", 1)
        return f"{base}/{quote}"
    if p.endswith("INR"):
        return f"{p[:-3]}/INR"
    if p.endswith("USDT"):
        return f"{p[:-4]}/USDT"
    return p


def _to_coindcx_channel(pair: str) -> str:
    """Convert pair string (e.g. 'BTC/INR') to CoinDCX market identifier (e.g. 'I-BTC_INR')."""
    base, _, quote = pair.replace("-", "/").partition("/")
    if not quote:
        base, quote = pair[:-3], pair[-3:]
    prefix = "I" if quote.upper() == "INR" else "B"
    return f"{prefix}-{base.upper()}_{quote.upper()}"


class CoinDCXWebSocketClient:
    """Real-time WebSocket client for CoinDCX exchange.

    Maintains a persistent connection to wss://stream.coindcx.com with
    automatic reconnection, channel subscription management, and
    thread-safe caches for ticker, order book, and trade data.
    """

    DEFAULT_STREAM_URL = (
        "wss://stream.coindcx.com/socket.io/?EIO=4&transport=websocket"
    )

    def __init__(
        self,
        stream_url: Optional[str] = None,
        pairs: Optional[List[str]] = None,
    ) -> None:
        """Initialize the WebSocket client.

        Args:
            stream_url: Custom WebSocket URL or defaults to CoinDCX stream.
            pairs: Initial list of trading pairs to watch (e.g. ['BTC/INR']).
        """
        self.stream_url = stream_url or self.DEFAULT_STREAM_URL
        self._watched_pairs: Set[str] = set(
            _normalize_pair(p) for p in (pairs or [])
        )

        # Connection lifecycle
        self._is_running: bool = False
        self._connected: bool = False
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._connect_task: Optional[asyncio.Task] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None

        # Exponential backoff parameters
        self._reconnect_delay: float = 1.0
        self._min_reconnect_delay: float = 1.0
        self._max_reconnect_delay: float = 30.0
        self._backoff_factor: float = 2.0

        # Heartbeat tracking
        self._last_message_ts: float = 0.0
        self._ping_interval: float = 25.0
        self._last_ping_ts: float = 0.0

        # Thread-safe data stores
        self._lock = threading.Lock()
        self._order_books: Dict[str, Dict[str, Any]] = {}
        self._tickers: Dict[str, Dict[str, Any]] = {}
        self._recent_trades: Dict[str, deque] = {}
        self._klines: Dict[str, Dict[str, Any]] = {}

        # Event callbacks: event_name -> list of callable(pair, payload)
        self._callbacks: Dict[str, List[Callable]] = {
            "order_book": [],
            "ticker": [],
            "trade": [],
            "kline": [],
            "connect": [],
            "disconnect": [],
            "error": [],
        }

    # ── Properties ─────────────────────────────────────────────────────
    def _is_ws_open(self) -> bool:
        """Check whether current WebSocket instance is active and open."""
        if self._ws is None:
            return False
        if hasattr(self._ws, "state"):
            state = self._ws.state
            return (
                getattr(state, "name", "") == "OPEN"
                or getattr(state, "value", None) == 1
            )
        if hasattr(self._ws, "closed"):
            return not self._ws.closed
        return getattr(self._ws, "close_code", None) is None

    @property
    def is_connected(self) -> bool:
        """Return True if WebSocket connection is live and active."""
        return self._connected and self._is_ws_open()

    @property
    def last_message_age(self) -> float:
        """Return elapsed seconds since the last received WebSocket message."""
        if self._last_message_ts <= 0:
            return 999999.0
        return max(0.0, time.monotonic() - self._last_message_ts)

    @property
    def subscribed_pairs(self) -> List[str]:
        """Return list of currently subscribed trading pairs."""
        with self._lock:
            return sorted(list(self._watched_pairs))

    # ── Callback Registration ──────────────────────────────────────────
    def register_callback(
        self, event_type: str, callback: Callable[..., Any]
    ) -> None:
        """Register a callback function for a specific event type.

        Supported event types: 'order_book', 'ticker', 'trade', 'kline',
                               'connect', 'disconnect', 'error'
        """
        if event_type in self._callbacks:
            if callback not in self._callbacks[event_type]:
                self._callbacks[event_type].append(callback)
        else:
            bot_logger.warning(
                f"CoinDCXWebSocketClient: Unknown event type '{event_type}'"
            )

    def unregister_callback(
        self, event_type: str, callback: Callable[..., Any]
    ) -> None:
        """Unregister a previously registered callback."""
        if event_type in self._callbacks and callback in self._callbacks[event_type]:
            self._callbacks[event_type].remove(callback)

    def _dispatch_event(self, event_type: str, *args: Any, **kwargs: Any) -> None:
        """Dispatch event callbacks across both sync and async functions safely."""
        callbacks = list(self._callbacks.get(event_type, []))
        for cb in callbacks:
            try:
                if inspect.iscoroutinefunction(cb):
                    if self._loop and self._loop.is_running():
                        asyncio.run_coroutine_threadsafe(
                            cb(*args, **kwargs), self._loop
                        )
                else:
                    cb(*args, **kwargs)
            except Exception as exc:
                bot_logger.error(
                    f"Error in WebSocket callback for {event_type}: {exc}"
                )

    # ── Channel Subscription Management ───────────────────────────────
    def subscribe_pair(self, pair: str) -> None:
        """Add a trading pair to active subscription list."""
        norm_pair = _normalize_pair(pair)
        with self._lock:
            if norm_pair in self._watched_pairs:
                return
            self._watched_pairs.add(norm_pair)

        bot_logger.info(f"WebSocket client subscribing to pair: {norm_pair}")
        if self.is_connected and self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(
                self._send_channel_subscriptions([norm_pair]), self._loop
            )

    def unsubscribe_pair(self, pair: str) -> None:
        """Remove a trading pair from active subscription list."""
        norm_pair = _normalize_pair(pair)
        with self._lock:
            if norm_pair not in self._watched_pairs:
                return
            self._watched_pairs.remove(norm_pair)
            self._order_books.pop(norm_pair, None)
            self._tickers.pop(norm_pair, None)

        bot_logger.info(f"WebSocket client unsubscribed from pair: {norm_pair}")

    async def _send_channel_subscriptions(self, pairs: List[str]) -> None:
        """Emit Socket.IO join packets for the specified pairs."""
        if not self._is_ws_open():
            return

        for pair in pairs:
            channel = _to_coindcx_channel(pair)
            join_market = f'42{json.dumps(["join", {"channelName": channel}])}'
            try:
                await self._ws.send(join_market)
                bot_logger.info(f"CoinDCX WS subscribed to market: {channel} ({pair})")
            except Exception as e:
                bot_logger.warning(f"CoinDCX WS join {channel} failed: {e}")

    # ── Core Async Connection Loop ─────────────────────────────────────
    async def run_forever(self) -> None:
        """Main connection and message processing loop with auto-reconnect."""
        self._is_running = True
        bot_logger.info("Starting CoinDCX WebSocket client run loop...")

        while self._is_running:
            try:
                bot_logger.info(
                    f"Connecting to CoinDCX WebSocket at {self.stream_url}..."
                )
                async with websockets.connect(
                    self.stream_url,
                    open_timeout=10,
                    ping_interval=None,  # Handled via Socket.IO 2->3 pings
                ) as ws:
                    self._ws = ws
                    self._connected = True
                    self._reconnect_delay = self._min_reconnect_delay
                    self._last_message_ts = time.monotonic()
                    bot_logger.info("CoinDCX WebSocket connection established.")
                    self._dispatch_event("connect")

                    # Step 1: Read Engine.IO handshake packet '0{...}'
                    handshake_msg = await ws.recv()
                    self._last_message_ts = time.monotonic()
                    if handshake_msg.startswith("0"):
                        try:
                            hs_data = json.loads(handshake_msg[1:])
                            self._ping_interval = float(
                                hs_data.get("pingInterval", 25000)
                            ) / 1000.0
                        except Exception:
                            pass

                    # Step 2: Send Socket.IO connect packet '40'
                    await ws.send("40")

                    # Step 3: Wait for connect ack '40{...}'
                    ack_msg = await ws.recv()
                    self._last_message_ts = time.monotonic()

                    # Step 4: Subscribe to all watched pairs
                    with self._lock:
                        pairs_to_sub = list(self._watched_pairs)
                    await self._send_channel_subscriptions(pairs_to_sub)

                    # Step 5: Process incoming message frames
                    while self._is_running:
                        try:
                            msg = await asyncio.wait_for(
                                ws.recv(), timeout=self._ping_interval + 15.0
                            )
                            self._last_message_ts = time.monotonic()
                            await self._handle_raw_message(msg)
                        except asyncio.TimeoutError:
                            bot_logger.warning(
                                "CoinDCX WebSocket recv timeout, checking connection..."
                            )
                            # Probe with Socket.IO ping packet '2'
                            await ws.send("2")
                        except websockets.ConnectionClosed as cc:
                            bot_logger.warning(
                                f"CoinDCX WebSocket connection closed: {cc}"
                            )
                            break

            except Exception as exc:
                bot_logger.error(f"CoinDCX WebSocket connection error: {exc}")
                self._dispatch_event("error", exc)
            finally:
                self._connected = False
                self._ws = None
                self._dispatch_event("disconnect")

            if self._is_running:
                bot_logger.info(
                    f"Reconnecting CoinDCX WebSocket in {self._reconnect_delay:.1f}s..."
                )
                await asyncio.sleep(self._reconnect_delay)
                self._reconnect_delay = min(
                    self._reconnect_delay * self._backoff_factor,
                    self._max_reconnect_delay,
                )

        bot_logger.info("CoinDCX WebSocket client run loop stopped.")

    async def _handle_raw_message(self, raw_msg: str | bytes) -> None:
        """Parse raw Socket.IO message frames and route to appropriate parsers."""
        if isinstance(raw_msg, bytes):
            try:
                raw_msg = raw_msg.decode("utf-8")
            except Exception:
                return

        # Engine.IO ping packet '2' -> reply with pong packet '3'
        if raw_msg == "2":
            if self._is_ws_open():
                await self._ws.send("3")
            return

        if raw_msg == "3":
            # Pong response received
            return

        # Socket.IO Event frame starts with '42'
        if raw_msg.startswith("42"):
            try:
                payload = json.loads(raw_msg[2:])
                if not isinstance(payload, list) or len(payload) < 2:
                    return

                event_name = str(payload[0])
                event_data = payload[1]
                self._process_socket_event(event_name, event_data)
            except Exception as exc:
                bot_logger.debug(f"Failed to parse Socket.IO event: {exc}")

    def _process_socket_event(self, event_name: str, event_data: Any) -> None:
        """Route parsed event data to data caches and callback triggers."""
        # Some event payloads are JSON-encoded strings inside the dictionary
        parsed_data = event_data
        if isinstance(event_data, dict) and "data" in event_data:
            data_val = event_data["data"]
            if isinstance(data_val, str):
                try:
                    parsed_data = json.loads(data_val)
                except Exception:
                    parsed_data = event_data

        # Determine target pair / channel
        channel_id = ""
        if isinstance(event_data, dict):
            channel_id = event_data.get("channel", "")
        if not channel_id and isinstance(parsed_data, dict):
            channel_id = parsed_data.get("channel", "") or parsed_data.get(
                "s", ""
            )

        pair = _normalize_pair(channel_id) if channel_id else ""

        # 1. Order book depth updates (depth-update, depth-update-10, depth-update-20)
        if "depth" in event_name or event_name in (
            "depth-update-20",
            "depth-update",
            "depth-update-10",
        ):
            self._handle_depth_update(pair, parsed_data)

        # 2. Trade executions
        elif event_name in ("new-trade", "trade", "trades"):
            self._handle_trade_update(pair, parsed_data)

        # 3. Ticker updates
        elif "ticker" in event_name or event_name in (
            "currentPrices",
            "price-change",
        ):
            self._handle_ticker_update(pair, parsed_data)

        # 4. Candlestick / Kline updates
        elif "kline" in event_name or "candle" in event_name:
            self._handle_kline_update(pair, parsed_data)

    def _handle_depth_update(self, pair: str, data: Dict[str, Any]) -> None:
        """Process real-time depth update and update order book cache."""
        raw_bids = data.get("b", [])
        raw_asks = data.get("a", [])
        pts = data.get("pts") or int(time.time() * 1000)

        # Symbol resolution fallback
        if not pair:
            sym = data.get("s", "")
            if sym:
                pair = _normalize_pair(sym)

        if not pair:
            return

        bids: List[List[float]] = []
        for item in raw_bids:
            try:
                bids.append([float(item[0]), float(item[1])])
            except (IndexError, ValueError, TypeError):
                continue

        asks: List[List[float]] = []
        for item in raw_asks:
            try:
                asks.append([float(item[0]), float(item[1])])
            except (IndexError, ValueError, TypeError):
                continue

        # Sort: bids descending, asks ascending
        bids.sort(key=lambda x: x[0], reverse=True)
        asks.sort(key=lambda x: x[0])

        order_book_entry = {
            "bids": bids[:20],
            "asks": asks[:20],
            "timestamp": pts,
            "received_at": time.time(),
        }

        with self._lock:
            self._order_books[pair] = order_book_entry

            # Also update best bid and ask in ticker cache if present
            if bids and asks:
                best_bid = bids[0][0]
                best_ask = asks[0][0]
                ticker_entry = self._tickers.get(pair, {})
                ticker_entry["bid"] = best_bid
                ticker_entry["ask"] = best_ask
                ticker_entry["timestamp"] = pts
                self._tickers[pair] = ticker_entry

        self._dispatch_event("order_book", pair, order_book_entry)

    def _handle_trade_update(self, pair: str, data: Any) -> None:
        """Process real-time trade event and update trade cache."""
        trades_list = data if isinstance(data, list) else [data]
        pts = int(time.time() * 1000)

        for tr in trades_list:
            if not isinstance(tr, dict):
                continue
            t_pair = pair or _normalize_pair(tr.get("s", ""))
            if not t_pair:
                continue

            price = float(tr.get("p", tr.get("price", 0.0)))
            qty = float(tr.get("q", tr.get("quantity", 0.0)))
            trade_ts = tr.get("T", tr.get("timestamp", pts))

            trade_entry = {
                "pair": t_pair,
                "price": price,
                "quantity": qty,
                "timestamp": trade_ts,
                "side": tr.get("m", True) and "sell" or "buy",
            }

            with self._lock:
                if t_pair not in self._recent_trades:
                    self._recent_trades[t_pair] = deque(maxlen=200)
                self._recent_trades[t_pair].append(trade_entry)

                # Update latest price in ticker
                if price > 0:
                    ticker = self._tickers.setdefault(t_pair, {})
                    ticker["last_price"] = price
                    ticker["timestamp"] = trade_ts

            self._dispatch_event("trade", t_pair, trade_entry)

    def _handle_ticker_update(self, pair: str, data: Dict[str, Any]) -> None:
        """Process real-time ticker data."""
        if not pair:
            sym = data.get("s", data.get("market", ""))
            if sym:
                pair = _normalize_pair(sym)

        if not pair:
            return

        last_price = float(data.get("last_price", data.get("c", 0.0)))
        bid = float(data.get("bid", data.get("b", 0.0)))
        ask = float(data.get("ask", data.get("a", 0.0)))
        vol = float(data.get("volume", data.get("v", 0.0)))
        chg = float(data.get("change_24h", data.get("P", 0.0)))

        ticker_entry = {
            "last_price": last_price,
            "bid": bid,
            "ask": ask,
            "volume": vol,
            "change_24h": chg,
            "timestamp": int(time.time() * 1000),
        }

        with self._lock:
            existing = self._tickers.get(pair, {})
            existing.update({k: v for k, v in ticker_entry.items() if v != 0.0})
            self._tickers[pair] = existing

        self._dispatch_event("ticker", pair, ticker_entry)

    def _handle_kline_update(self, pair: str, data: Dict[str, Any]) -> None:
        """Process real-time kline/candle update."""
        interval = data.get("interval", "15m")
        key = f"{pair}:{interval}"
        with self._lock:
            self._klines[key] = {
                "timestamp": data.get("t", data.get("time")),
                "open": float(data.get("o", data.get("open", 0.0))),
                "high": float(data.get("h", data.get("high", 0.0))),
                "low": float(data.get("l", data.get("low", 0.0))),
                "close": float(data.get("c", data.get("close", 0.0))),
                "volume": float(data.get("v", data.get("volume", 0.0))),
            }
        self._dispatch_event("kline", pair, interval, self._klines[key])

    # ── Thread-Safe Synchronous Query Methods ──────────────────────────
    def get_order_book(
        self, pair: str, max_age_seconds: float = 15.0
    ) -> Optional[Dict[str, Any]]:
        """Return cached top-20 order book if fresh.

        Args:
            pair: Standard pair identifier (e.g. 'BTC/INR').
            max_age_seconds: Maximum allowed age of cached depth before deemed stale.

        Returns:
            Dict with 'bids', 'asks', 'timestamp', or None if stale/missing.
        """
        norm_pair = _normalize_pair(pair)
        with self._lock:
            entry = self._order_books.get(norm_pair)
            if not entry:
                return None
            age = time.time() - entry.get("received_at", 0)
            if age > max_age_seconds:
                return None
            return {
                "bids": list(entry["bids"]),
                "asks": list(entry["asks"]),
                "timestamp": entry["timestamp"],
            }

    def get_ticker(
        self, pair: str, max_age_seconds: float = 30.0
    ) -> Optional[Dict[str, Any]]:
        """Return cached ticker for *pair* if fresh."""
        norm_pair = _normalize_pair(pair)
        with self._lock:
            ticker = self._tickers.get(norm_pair)
            if not ticker or "last_price" not in ticker:
                return None
            return dict(ticker)

    def get_recent_trades(
        self, pair: str, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Return list of recently recorded trades for *pair*."""
        norm_pair = _normalize_pair(pair)
        with self._lock:
            q = self._recent_trades.get(norm_pair)
            if not q:
                return []
            trades = list(q)
            return trades[-limit:]

    # ── Thread Execution Wrappers ──────────────────────────────────────
    def start_in_thread(self) -> threading.Thread:
        """Start the WebSocket client in a dedicated background daemon thread.

        Provides a clean bridge for synchronous environments like BotScheduler.
        """
        if self._thread and self._thread.is_alive():
            bot_logger.debug("CoinDCX WebSocket thread is already running.")
            return self._thread

        def _thread_target() -> None:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            try:
                self._loop.run_until_complete(self.run_forever())
            except Exception as e:
                bot_logger.error(f"WebSocket client loop crashed: {e}")
            finally:
                self._loop.close()

        self._thread = threading.Thread(
            target=_thread_target, name="CoinDCX-WebSocket-Client", daemon=True
        )
        self._thread.start()
        bot_logger.info(
            "CoinDCX WebSocket client background thread initiated."
        )
        return self._thread

    def stop(self) -> None:
        """Signal the WebSocket client to stop and close active connections."""
        self._is_running = False
        if self._ws and self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self._ws.close(), self._loop)
        bot_logger.info("CoinDCX WebSocket client stop requested.")

    def stop_thread(self, timeout: float = 3.0) -> None:
        """Stop WebSocket and join background thread."""
        self.stop()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
