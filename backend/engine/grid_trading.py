"""
AutoTrader Pro - Grid Trading Strategy
========================================
Strategy 5: Places a grid of buy and sell orders at evenly-spaced price
levels around the current market price. Profits are captured as price
oscillates within the grid. When price escapes the grid range, the grid
is rebalanced around the new price.

Grid mechanics:
  - N levels ABOVE current price → SELL zones
  - N levels BELOW current price → BUY zones
  - Each level is spaced by grid_spacing_pct
  - Rebalance when price is > rebalance_threshold_pct from grid centre
"""

from typing import Optional, List, Dict, Any

import pandas as pd

from backend.engine.strategy_base import StrategyBase, StrategySignal
from backend.utils.logger import bot_logger


class GridTradingStrategy(StrategyBase):
    """
    Grid Trading — profit from sideways volatility.

    Default Parameters:
        grid_spacing_pct (float): Distance between grid levels as a
            percentage of the centre price (default 1.0).
        num_levels (int): Number of levels ABOVE and BELOW centre
            (total grid = 2 * num_levels + 1). Default 5.
        capital_per_grid (float): Capital (₹) allocated per grid level
            for position sizing (default 1000).
        rebalance_threshold_pct (float): If price moves this far from
            the grid centre, the grid is torn down and rebuilt
            (default 5.0%).

    Instance State:
        grid_levels (list): Sorted list of price levels.
        grid_centre (float): The price around which the grid was built.
        active_orders (dict): Mapping of level-index → order status.
        hit_levels (set): Levels that have already been triggered in
            the current grid to avoid duplicate signals.
    """

    DEFAULT_PARAMS = {
        "grid_spacing_pct": 1.0,
        "num_levels": 5,
        "capital_per_grid": 1000,
        "rebalance_threshold_pct": 5.0,
    }

    def __init__(self, params: dict = None):
        merged = {**self.DEFAULT_PARAMS, **(params or {})}
        super().__init__(name="Grid_Trading", default_params=merged)

        # Instance state — persisted across analyze() calls
        self.grid_levels: List[float] = []
        self.grid_centre: float = 0.0
        self.active_orders: Dict[int, Dict[str, Any]] = {}
        self.hit_levels: set = set()

    # ------------------------------------------------------------------
    # Grid management
    # ------------------------------------------------------------------
    def setup_grid(self, current_price: float) -> List[float]:
        """
        Create evenly-spaced grid levels around `current_price`.

        Returns the full sorted list of levels.

        Example with num_levels=3, spacing=1%, price=10000:
          [9700, 9800, 9900, 10000, 10100, 10200, 10300]
        """
        spacing_pct = self.params["grid_spacing_pct"]
        num_levels = self.params["num_levels"]

        levels: List[float] = []
        for i in range(-num_levels, num_levels + 1):
            level = current_price * (1 + i * spacing_pct / 100.0)
            levels.append(round(level, 2))

        levels.sort()
        self.grid_levels = levels
        self.grid_centre = current_price
        self.hit_levels = set()

        # Initialise active orders map
        self.active_orders = {}
        for idx, level in enumerate(levels):
            side = "BUY" if level < current_price else ("SELL" if level > current_price else "CENTRE")
            self.active_orders[idx] = {
                "level": level,
                "side": side,
                "status": "PENDING",
            }

        bot_logger.info(
            f"[Grid_Trading] Grid created: centre=₹{current_price:.2f}, "
            f"{len(levels)} levels from ₹{levels[0]:.2f} to ₹{levels[-1]:.2f}, "
            f"spacing={spacing_pct}%"
        )
        return levels

    def _needs_rebalance(self, current_price: float) -> bool:
        """Check whether the price has moved far enough to require a grid rebuild."""
        if self.grid_centre == 0:
            return True
        distance_pct = abs(current_price - self.grid_centre) / self.grid_centre * 100
        return distance_pct > self.params["rebalance_threshold_pct"]

    def check_grid_hit(self, current_price: float, pair: str) -> Optional[StrategySignal]:
        """
        Check whether the current price has hit any un-triggered grid level.

        A level is "hit" when the price crosses it (within a small tolerance
        of 0.1% to account for micro-fluctuations).

        Returns the highest-priority signal (closest level hit), or None.
        """
        if not self.grid_levels:
            return None

        tolerance_pct = 0.1  # price must be within 0.1% of level
        capital = self.params["capital_per_grid"]

        best_signal: Optional[StrategySignal] = None
        best_distance = float("inf")

        for idx, order_info in self.active_orders.items():
            if order_info["status"] != "PENDING":
                continue
            if idx in self.hit_levels:
                continue
            if order_info["side"] == "CENTRE":
                continue

            level = order_info["level"]
            distance_pct = abs(current_price - level) / level * 100

            if distance_pct <= tolerance_pct and distance_pct < best_distance:
                best_distance = distance_pct
                action = order_info["side"]
                quantity = capital / current_price if current_price > 0 else 0

                reason = (
                    f"Grid level hit: ₹{level:.2f} ({action}). "
                    f"Price ₹{current_price:.2f}, grid centre ₹{self.grid_centre:.2f}. "
                    f"Allocated ₹{capital:.0f} per level."
                )

                # Strength based on how close to the centre the level is
                # Levels closer to centre are lower-risk entries
                grid_half_range = (
                    self.grid_levels[-1] - self.grid_levels[0]
                ) / 2 if len(self.grid_levels) > 1 else 1
                distance_from_centre = abs(level - self.grid_centre)
                strength = max(
                    0.3,
                    min(1.0, 0.5 + 0.5 * (1 - distance_from_centre / grid_half_range)),
                )

                best_signal = StrategySignal(
                    pair=pair,
                    action=action,
                    strategy=self.name,
                    strength=strength,
                    reason=reason,
                    metadata={
                        "grid_level": level,
                        "grid_level_index": idx,
                        "grid_centre": self.grid_centre,
                        "quantity": quantity,
                        "capital_per_grid": capital,
                        "total_grid_levels": len(self.grid_levels),
                        "grid_levels": self.grid_levels.copy(),
                    },
                )
                # Mark level as hit
                self.hit_levels.add(idx)
                self.active_orders[idx]["status"] = "TRIGGERED"

        return best_signal

    # ------------------------------------------------------------------
    # Main analysis
    # ------------------------------------------------------------------
    def analyze(self, df: pd.DataFrame, pair: str) -> Optional[StrategySignal]:
        """
        Check grid state and return a signal if a level has been hit.

        On first call (or after rebalance), the grid is created.

        Args:
            df: OHLCV DataFrame.
            pair: Trading pair string.

        Returns:
            StrategySignal if a grid level is triggered, else None.
        """
        if df is None or len(df) < 2:
            return None

        try:
            current_price = float(df["close"].iloc[-1])

            if current_price <= 0:
                return None

            # ------------------------------------------------------------------
            # 1. Initial grid setup or rebalance
            # ------------------------------------------------------------------
            if not self.grid_levels or self._needs_rebalance(current_price):
                if self.grid_levels:
                    bot_logger.info(
                        f"[Grid_Trading] Rebalancing grid for {pair}. "
                        f"Price ₹{current_price:.2f} moved "
                        f"{abs(current_price - self.grid_centre) / self.grid_centre * 100:.1f}% "
                        f"from centre ₹{self.grid_centre:.2f}"
                    )
                self.setup_grid(current_price)
                # After setup, price is at centre — no levels hit yet
                return None

            # ------------------------------------------------------------------
            # 2. Check for grid level hits
            # ------------------------------------------------------------------
            signal = self.check_grid_hit(current_price, pair)

            if signal is not None:
                bot_logger.info(
                    f"[Grid_Trading] {signal.action} signal for {pair}: "
                    f"{signal.reason}"
                )

            return signal

        except Exception as e:
            bot_logger.error(
                f"[Grid_Trading] Analysis error for {pair}: {e}"
            )
            return None

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------
    def get_grid_status(self) -> Dict[str, Any]:
        """Return a snapshot of the current grid state for dashboards."""
        return {
            "centre": self.grid_centre,
            "levels": self.grid_levels.copy(),
            "active_orders": {
                k: v.copy() for k, v in self.active_orders.items()
            },
            "hit_levels": list(self.hit_levels),
            "params": self.params.copy(),
        }

    def reset_grid(self):
        """Tear down the current grid (next analyze() will rebuild it)."""
        self.grid_levels = []
        self.grid_centre = 0.0
        self.active_orders = {}
        self.hit_levels = set()
        bot_logger.info("[Grid_Trading] Grid reset")
