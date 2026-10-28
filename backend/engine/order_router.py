"""
AutoTrader Pro - Smart Order Router
===================================
Analyzes market microstructure and order book liquidity depth to determine
optimal order execution plans:
  - Small orders (< 5% of top-of-book depth): Immediate Market Order
  - Medium orders (5 - 20% of depth): Limit Order at Mid-Price
  - Large orders (> 20% of depth): TWAP (Time-Weighted Average Price) split
    into 3 to 5 chunks spaced 30 seconds apart, each placed as Limit orders
    with an automated Market order fallback upon timeout.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Dict, Any

from backend.engine.strategy_base import StrategySignal
from backend.utils.logger import bot_logger


@dataclass
class OrderPlan:
    """
    Specification for a single executable order slice or chunk.

    Attributes:
        order_type: "MARKET", "LIMIT", "STOP_LIMIT"
        quantity: Amount of asset to trade
        price: Price for limit orders (None for market orders)
        delay_seconds: Pre-execution delay (for TWAP scheduling)
        timeout_seconds: Time to wait for fill before fallback/cancel
        fallback: Order type to fall back to upon timeout (e.g. "MARKET")
    """
    order_type: str
    quantity: float
    price: Optional[float] = None
    delay_seconds: float = 0.0
    timeout_seconds: float = 15.0
    fallback: str = "MARKET"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "order_type": self.order_type,
            "quantity": round(self.quantity, 6),
            "price": round(self.price, 4) if self.price is not None else None,
            "delay_seconds": self.delay_seconds,
            "timeout_seconds": self.timeout_seconds,
            "fallback": self.fallback,
        }


class SmartOrderRouter:
    """
    Routes trade signals through optimal execution paths based on real-time
    order book liquidity and notional volume.
    """

    def __init__(
        self,
        small_threshold_pct: float = 0.05,
        medium_threshold_pct: float = 0.20,
        twap_chunk_interval_sec: float = 30.0,
        default_limit_timeout_sec: float = 15.0,
        default_twap_timeout_sec: float = 25.0,
    ) -> None:
        self.small_threshold_pct = small_threshold_pct
        self.medium_threshold_pct = medium_threshold_pct
        self.twap_chunk_interval_sec = twap_chunk_interval_sec
        self.default_limit_timeout_sec = default_limit_timeout_sec
        self.default_twap_timeout_sec = default_twap_timeout_sec

    def _extract_liquidity_and_prices(
        self,
        order_book: Optional[Dict[str, Any]],
        side: str,
    ) -> tuple[float, float, float, float]:
        """
        Extract top-of-book depth liquidity, best bid, best ask, and mid price.

        Returns:
            (top_liquidity, best_bid, best_ask, mid_price)
        """
        if not order_book:
            return 0.0, 0.0, 0.0, 0.0

        bids = order_book.get("bids", [])
        asks = order_book.get("asks", [])

        best_bid = float(bids[0][0]) if bids and len(bids[0]) > 0 else 0.0
        best_ask = float(asks[0][0]) if asks and len(asks[0]) > 0 else 0.0

        if best_bid > 0 and best_ask > 0:
            mid_price = (best_bid + best_ask) / 2.0
        elif best_ask > 0:
            mid_price = best_ask
        else:
            mid_price = best_bid

        # Calculate relevant side liquidity across top levels (up to 5 levels)
        if side.upper() == "BUY":
            # For BUY orders, we are consuming asks
            target_levels = asks[:5] if asks else []
        else:
            # For SELL orders, we are consuming bids
            target_levels = bids[:5] if bids else []

        top_liquidity = sum(float(lvl[1]) for lvl in target_levels if len(lvl) > 1)
        return top_liquidity, best_bid, best_ask, mid_price

    def route(
        self,
        signal: StrategySignal,
        market_state: Dict[str, Any],
        quantity: Optional[float] = None,
    ) -> List[OrderPlan]:
        """
        Analyze order size against top-of-book liquidity and generate execution plan(s).

        Args:
            signal: Trading signal containing pair, action, strategy, metadata.
            market_state: Dict containing order_book, ticker, current_price, etc.
            quantity: Trade quantity in base currency (if None, read from market_state).

        Returns:
            List of OrderPlan instances to execute.
        """
        side = signal.action.upper()
        if side not in ("BUY", "SELL"):
            return []

        # Determine target quantity
        qty = quantity or market_state.get("quantity") or market_state.get("position_size")
        if qty is None or qty <= 0:
            notional = market_state.get("notional") or market_state.get("amount_inr", 0.0)
            curr_p = market_state.get("current_price", 0.0)
            if notional > 0 and curr_p > 0:
                qty = notional / curr_p
            else:
                qty = 0.0

        if qty <= 0:
            bot_logger.warning(f"[SmartOrderRouter] Cannot route order with zero quantity for {signal.pair}")
            return []

        # Check order book data
        order_book = market_state.get("order_book")
        curr_price = float(market_state.get("current_price") or 0.0)

        # Fallback 1: No order book data available -> default to immediate MARKET order
        if not order_book:
            bot_logger.debug(
                f"[SmartOrderRouter] No order book for {signal.pair}. Routing as direct MARKET order."
            )
            return [
                OrderPlan(
                    order_type="MARKET",
                    quantity=qty,
                    price=None,
                    delay_seconds=0.0,
                    timeout_seconds=10.0,
                    fallback="MARKET",
                )
            ]

        top_liquidity, best_bid, best_ask, mid_price = self._extract_liquidity_and_prices(
            order_book, side
        )

        # If mid_price is unavailable, fallback to current_price
        if mid_price <= 0:
            mid_price = curr_price

        # Fallback 2: Liquidity depth is zero or invalid -> default to MARKET order
        if top_liquidity <= 0:
            bot_logger.debug(
                f"[SmartOrderRouter] Zero order book liquidity on {signal.pair}. Routing as MARKET order."
            )
            return [
                OrderPlan(
                    order_type="MARKET",
                    quantity=qty,
                    price=None,
                    delay_seconds=0.0,
                    timeout_seconds=10.0,
                    fallback="MARKET",
                )
            ]

        liquidity_ratio = qty / top_liquidity
        bot_logger.info(
            f"[SmartOrderRouter] {signal.pair} {side} Qty={qty:.6f} vs TopLiquidity={top_liquidity:.4f} "
            f"(ratio={liquidity_ratio:.2%})"
        )

        # ── Case 1: Small order (< 5% of top-of-book depth) ───────────────────
        if liquidity_ratio < self.small_threshold_pct:
            bot_logger.debug(
                f"[SmartOrderRouter] Small order ({liquidity_ratio:.2%} < {self.small_threshold_pct:.0%}). "
                "Routing immediate MARKET order."
            )
            return [
                OrderPlan(
                    order_type="MARKET",
                    quantity=qty,
                    price=None,
                    delay_seconds=0.0,
                    timeout_seconds=10.0,
                    fallback="MARKET",
                )
            ]

        # ── Case 2: Medium order (5% - 20% of top-of-book depth) ──────────────
        elif liquidity_ratio <= self.medium_threshold_pct:
            # Place limit order at mid-price to capture the spread without moving the book
            limit_price = mid_price if mid_price > 0 else curr_price
            bot_logger.info(
                f"[SmartOrderRouter] Medium order ({liquidity_ratio:.2%}). "
                f"Routing LIMIT order @ mid-price ₹{limit_price:.2f} (timeout={self.default_limit_timeout_sec}s)."
            )
            return [
                OrderPlan(
                    order_type="LIMIT",
                    quantity=qty,
                    price=limit_price,
                    delay_seconds=0.0,
                    timeout_seconds=self.default_limit_timeout_sec,
                    fallback="MARKET",
                )
            ]

        # ── Case 3: Large order (> 20% of top-of-book depth) ───────────────────
        else:
            # TWAP: Split into 3 to 5 chunks spaced 30 seconds apart
            if liquidity_ratio > 0.50:
                num_chunks = 5
            elif liquidity_ratio > 0.35:
                num_chunks = 4
            else:
                num_chunks = 3

            chunk_qty = round(qty / num_chunks, 6)
            plans: List[OrderPlan] = []

            # Pricing: For BUY, limit at best bid (or mid price); for SELL, limit at best ask
            if side == "BUY":
                limit_p = best_bid if best_bid > 0 else (mid_price if mid_price > 0 else curr_price)
            else:
                limit_p = best_ask if best_ask > 0 else (mid_price if mid_price > 0 else curr_price)

            remaining_qty = qty
            for i in range(num_chunks):
                # Ensure the last chunk captures exact rounding difference
                this_qty = remaining_qty if i == num_chunks - 1 else chunk_qty
                remaining_qty -= this_qty

                plans.append(
                    OrderPlan(
                        order_type="LIMIT",
                        quantity=round(this_qty, 6),
                        price=round(limit_p, 4),
                        delay_seconds=i * self.twap_chunk_interval_sec,
                        timeout_seconds=self.default_twap_timeout_sec,
                        fallback="MARKET",
                    )
                )

            bot_logger.info(
                f"[SmartOrderRouter] Large order ({liquidity_ratio:.2%}). "
                f"Routing TWAP with {num_chunks} chunks spaced {self.twap_chunk_interval_sec}s apart @ ₹{limit_p:.2f}."
            )
            return plans
