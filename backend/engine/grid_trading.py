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

        # Persisted state per pair: {pair: {"levels": [], "centre": 0.0, "active_orders": {}, "hit_levels": set()}}
        self.grids: Dict[str, Dict[str, Any]] = {}

    def _get_grid_state(self, pair: str) -> Dict[str, Any]:
        """Get or initialize grid state for a specific pair."""
        if pair not in self.grids:
            self.grids[pair] = {
                "levels": [],
                "centre": 0.0,
                "active_orders": {},
                "hit_levels": set(),
            }
        return self.grids[pair]

    # ------------------------------------------------------------------
    # Grid management
    # ------------------------------------------------------------------
    def setup_grid(self, current_price: float, pair: str) -> List[float]:
        """
        Create evenly-spaced grid levels around `current_price` for `pair`.

        Returns the full sorted list of levels.
        """
        spacing_pct = self.params["grid_spacing_pct"]
        num_levels = self.params["num_levels"]

        levels: List[float] = []
        for i in range(-num_levels, num_levels + 1):
            level = current_price * (1 + i * spacing_pct / 100.0)
            levels.append(round(level, 2))

        levels.sort()
        state = self._get_grid_state(pair)
        state["levels"] = levels
        state["centre"] = current_price
        state["hit_levels"] = set()

        # Initialise active orders map
        state["active_orders"] = {}
        for idx, level in enumerate(levels):
            side = "BUY" if level < current_price else ("SELL" if level > current_price else "CENTRE")
            state["active_orders"][idx] = {
                "level": level,
                "side": side,
                "status": "PENDING",
            }

        bot_logger.info(
            f"[Grid_Trading] Grid created for {pair}: centre=₹{current_price:.2f}, "
            f"{len(levels)} levels from ₹{levels[0]:.2f} to ₹{levels[-1]:.2f}, "
            f"spacing={spacing_pct}%"
        )
        return levels

    def _needs_rebalance(self, current_price: float, pair: str) -> bool:
        """Check whether the price has moved far enough to require a grid rebuild."""
        state = self._get_grid_state(pair)
        centre = state["centre"]
        if centre == 0:
            return True
        distance_pct = abs(current_price - centre) / centre * 100
        return distance_pct > self.params["rebalance_threshold_pct"]

    def check_grid_hit(self, current_price: float, pair: str) -> Optional[StrategySignal]:
        """
        Check whether the current price has hit any un-triggered grid level.
        """
        state = self._get_grid_state(pair)
        levels = state["levels"]
        if not levels:
            return None

        tolerance_pct = 0.1  # price must be within 0.1% of level
        capital = self.params["capital_per_grid"]

        best_signal: Optional[StrategySignal] = None
        best_distance = float("inf")

        for idx, order_info in state["active_orders"].items():
            if order_info["status"] != "PENDING":
                continue
            if idx in state["hit_levels"]:
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
                    f"Grid level hit for {pair}: ₹{level:.2f} ({action}). "
                    f"Price ₹{current_price:.2f}, grid centre ₹{state['centre']:.2f}. "
                    f"Allocated ₹{capital:.0f} per level."
                )

                grid_half_range = (
                    levels[-1] - levels[0]
                ) / 2 if len(levels) > 1 else 1
                distance_from_centre = abs(level - state["centre"])
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
                        "grid_centre": state["centre"],
                        "quantity": quantity,
                        "capital_per_grid": capital,
                        "total_grid_levels": len(levels),
                        "grid_levels": levels.copy(),
                    },
                )
                # Mark level as hit
                state["hit_levels"].add(idx)
                state["active_orders"][idx]["status"] = "TRIGGERED"

        return best_signal

    # ------------------------------------------------------------------
    # Main analysis
    # ------------------------------------------------------------------
    def analyze(self, df: pd.DataFrame, pair: str) -> Optional[StrategySignal]:
        """
        Check grid state and return a signal if a level has been hit.
        """
        if df is None or len(df) < 2:
            return None

        try:
            current_price = float(df["close"].iloc[-1])

            if current_price <= 0:
                return None

            state = self._get_grid_state(pair)

            # ------------------------------------------------------------------
            # 1. Initial grid setup or rebalance
            # ------------------------------------------------------------------
            if not state["levels"] or self._needs_rebalance(current_price, pair):
                if state["levels"]:
                    bot_logger.info(
                        f"[Grid_Trading] Rebalancing grid for {pair}. "
                        f"Price ₹{current_price:.2f} moved "
                        f"{abs(current_price - state['centre']) / state['centre'] * 100:.1f}% "
                        f"from centre ₹{state['centre']:.2f}"
                    )
                self.setup_grid(current_price, pair)
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
    def get_grid_status(self, pair: Optional[str] = None) -> Dict[str, Any]:
        """Return a snapshot of the grid state for a pair (or all grids)."""
        if pair:
            state = self._get_grid_state(pair)
            return {
                "centre": state["centre"],
                "levels": state["levels"].copy(),
                "active_orders": {
                    k: v.copy() for k, v in state["active_orders"].items()
                },
                "hit_levels": list(state["hit_levels"]),
                "params": self.params.copy(),
            }
        return {
            p: {
                "centre": s["centre"],
                "levels": s["levels"].copy(),
                "active_orders": {k: v.copy() for k, v in s["active_orders"].items()},
                "hit_levels": list(s["hit_levels"]),
            } for p, s in self.grids.items()
        }

    def reset_grid(self):
        """Tear down all grids (next analyze() will rebuild them)."""
        self.grids.clear()
        bot_logger.info("[Grid_Trading] All grids reset")
