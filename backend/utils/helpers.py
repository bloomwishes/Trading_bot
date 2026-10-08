"""
AutoTrader Pro - Helper Utilities
Pure-function helpers used across the codebase.
"""

from __future__ import annotations

import asyncio
import functools
import json
import locale
import time
from datetime import datetime
from typing import Any, Callable, Optional, TypeVar

T = TypeVar("T")


# ═══════════════════════════════════════════════════════════════════════════
# Currency formatting (INR)
# ═══════════════════════════════════════════════════════════════════════════
def format_inr(amount: float) -> str:
    """Format a float as an INR string: ₹10,000.00

    Uses Indian comma grouping (lakh / crore style is not applied here;
    standard international grouping is used for simplicity and readability).
    """
    try:
        formatted = f"{amount:,.2f}"
    except (TypeError, ValueError):
        formatted = "0.00"
    return f"₹{formatted}"


# ═══════════════════════════════════════════════════════════════════════════
# PnL helpers
# ═══════════════════════════════════════════════════════════════════════════
def calculate_pnl(
    entry_price: float,
    current_price: float,
    quantity: float,
    side: str,
) -> float:
    """Return absolute PnL in INR.

    For BUY  : pnl = (current - entry) * qty
    For SELL : pnl = (entry - current) * qty   (short)
    """
    if side.upper() == "BUY":
        return (current_price - entry_price) * quantity
    else:
        return (entry_price - current_price) * quantity


def calculate_pnl_pct(
    entry_price: float,
    current_price: float,
    side: str,
) -> float:
    """Return PnL as a percentage of entry price.

    Positive  = profit, negative = loss.
    """
    if entry_price == 0:
        return 0.0
    if side.upper() == "BUY":
        return ((current_price - entry_price) / entry_price) * 100.0
    else:
        return ((entry_price - current_price) / entry_price) * 100.0


# ═══════════════════════════════════════════════════════════════════════════
# Timestamps
# ═══════════════════════════════════════════════════════════════════════════
def timestamp_now() -> datetime:
    """Return the current UTC timestamp."""
    return datetime.utcnow()


# ═══════════════════════════════════════════════════════════════════════════
# JSON helpers
# ═══════════════════════════════════════════════════════════════════════════
def safe_json_loads(text: Optional[str], default: Any = None) -> Any:
    """Safely parse a JSON string, returning *default* on any failure."""
    if text is None:
        return default
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError, ValueError):
        return default


# ═══════════════════════════════════════════════════════════════════════════
# Retry decorator with exponential back-off
# ═══════════════════════════════════════════════════════════════════════════
def retry_with_backoff(
    func: Optional[Callable[..., T]] = None,
    *,
    max_retries: int = 3,
    base_delay: float = 1.0,
) -> Callable[..., T]:
    """Decorator that retries *func* up to *max_retries* times with
    exponential back-off.

    Can be used with or without arguments::

        @retry_with_backoff
        def do_something(): ...

        @retry_with_backoff(max_retries=5, base_delay=0.5)
        def do_something(): ...
    """

    def decorator(fn: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(fn)
        def sync_wrapper(*args: Any, **kwargs: Any) -> T:
            last_exc: Exception | None = None
            for attempt in range(1, max_retries + 1):
                try:
                    return fn(*args, **kwargs)
                except Exception as exc:
                    last_exc = exc
                    if attempt < max_retries:
                        delay = base_delay * (2 ** (attempt - 1))
                        time.sleep(delay)
            raise last_exc  # type: ignore[misc]

        @functools.wraps(fn)
        async def async_wrapper(*args: Any, **kwargs: Any) -> T:
            last_exc: Exception | None = None
            for attempt in range(1, max_retries + 1):
                try:
                    return await fn(*args, **kwargs)
                except Exception as exc:
                    last_exc = exc
                    if attempt < max_retries:
                        delay = base_delay * (2 ** (attempt - 1))
                        await asyncio.sleep(delay)
            raise last_exc  # type: ignore[misc]

        if asyncio.iscoroutinefunction(fn):
            return async_wrapper  # type: ignore[return-value]
        return sync_wrapper  # type: ignore[return-value]

    if func is not None:
        # Called without arguments: @retry_with_backoff
        return decorator(func)
    # Called with arguments: @retry_with_backoff(max_retries=5)
    return decorator  # type: ignore[return-value]
