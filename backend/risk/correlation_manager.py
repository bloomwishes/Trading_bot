"""
AutoTrader Pro - Correlation Manager
====================================
Maintains rolling cross-asset price correlation matrix to guard against
correlated over-exposure. Prevents stacking multiple concurrent positions
in highly correlated cryptocurrencies in the same direction.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple, Any
import numpy as np
import pandas as pd

from backend.utils.logger import bot_logger


class CorrelationManager:
    """
    Manages pairwise Pearson correlation coefficients across monitored pairs
    and enforces maximum correlated position limits.
    """

    def __init__(
        self,
        max_correlated_positions: int = 2,
        correlation_threshold: float = 0.7,
        lookback_candles: int = 60,
    ) -> None:
        self.max_correlated_positions: int = max_correlated_positions
        self.correlation_threshold: float = correlation_threshold
        self.lookback_candles: int = lookback_candles
        # Matrix stored as nested dictionary: matrix[pair1][pair2] = correlation_float
        self.matrix: Dict[str, Dict[str, float]] = {}
        self._init_default_matrix()

    def _init_default_matrix(self) -> None:
        """Seed baseline crypto market correlations as sensible defaults."""
        pairs = ["BTC/INR", "ETH/INR", "SOL/INR", "XRP/INR", "BNB/INR"]
        default_corr = {
            "BTC/INR": {"BTC/INR": 1.00, "ETH/INR": 0.85, "SOL/INR": 0.78, "XRP/INR": 0.65, "BNB/INR": 0.75},
            "ETH/INR": {"BTC/INR": 0.85, "ETH/INR": 1.00, "SOL/INR": 0.82, "XRP/INR": 0.62, "BNB/INR": 0.78},
            "SOL/INR": {"BTC/INR": 0.78, "ETH/INR": 0.82, "SOL/INR": 1.00, "XRP/INR": 0.68, "BNB/INR": 0.74},
            "XRP/INR": {"BTC/INR": 0.65, "ETH/INR": 0.62, "SOL/INR": 0.68, "XRP/INR": 1.00, "BNB/INR": 0.66},
            "BNB/INR": {"BTC/INR": 0.75, "ETH/INR": 0.78, "SOL/INR": 0.74, "XRP/INR": 0.66, "BNB/INR": 1.00},
        }
        self.matrix = default_corr

    def update_correlation_matrix(self, price_history: Dict[str, Any]) -> None:
        """
        Compute rolling Pearson correlation matrix across all watched pairs.

        Args:
            price_history: Dict mapping pair symbol (e.g. 'BTC/INR') to a list or
                           pandas Series of recent closing prices (up to 60 candles).
        """
        if not price_history or len(price_history) < 2:
            return

        try:
            # Build aligned DataFrame of closes
            series_dict = {}
            for pair, closes in price_history.items():
                if isinstance(closes, pd.Series):
                    series_dict[pair] = closes.tail(self.lookback_candles)
                elif isinstance(closes, (list, tuple)) and len(closes) > 0:
                    series_dict[pair] = pd.Series(closes[-self.lookback_candles:])
                elif hasattr(closes, "to_list"):
                    series_dict[pair] = pd.Series(closes.to_list()[-self.lookback_candles:])

            if len(series_dict) < 2:
                return

            df = pd.DataFrame(series_dict).dropna()
            if df.empty or len(df) < 5:
                return

            # Compute Pearson correlation
            corr_df = df.corr(method="pearson").fillna(0.0)

            new_matrix: Dict[str, Dict[str, float]] = {}
            for col1 in corr_df.columns:
                new_matrix[col1] = {}
                for col2 in corr_df.columns:
                    new_matrix[col1][col2] = round(float(corr_df.loc[col1, col2]), 4)

            self.matrix = new_matrix
            bot_logger.debug(
                f"[CorrelationManager] Updated correlation matrix across {len(self.matrix)} pairs"
            )
        except Exception as exc:
            bot_logger.warning(f"[CorrelationManager] Failed to update correlation matrix: {exc}")

    def get_correlation(self, pair1: str, pair2: str) -> float:
        """Get correlation coefficient between pair1 and pair2 (defaulting to 0.0)."""
        p1 = pair1.upper()
        p2 = pair2.upper()
        if p1 == p2:
            return 1.0
        return self.matrix.get(p1, {}).get(p2, self.matrix.get(p2, {}).get(p1, 0.0))

    def check_correlation(
        self,
        new_signal: Any,
        open_positions: List[Dict[str, Any]],
        correlation_matrix: Optional[Dict[str, Dict[str, float]]] = None,
    ) -> Tuple[bool, str]:
        """
        Validate whether adding this signal violates correlated exposure constraints.

        Rule:
          When a BUY signal arrives, check correlation with existing LONG positions.
          When a SELL signal arrives, check correlation with existing SHORT positions.
          If |correlation| >= threshold AND already have max_correlated_positions -> REJECT.
        """
        pair = str(getattr(new_signal, "pair", "")).upper()
        action = str(getattr(new_signal, "action", "BUY")).upper()
        target_dir = "LONG" if action == "BUY" else "SHORT"

        matrix = correlation_matrix or self.matrix
        correlated_count = 0
        correlated_pairs: List[str] = []

        for pos in open_positions:
            pos_pair = str(pos.get("pair", "")).upper()
            if not pos_pair or pos_pair == pair:
                continue

            # Determine existing position direction
            pos_side = str(pos.get("side", pos.get("direction", "BUY"))).upper()
            pos_dir = "LONG" if pos_side in ("BUY", "LONG") else "SHORT"

            # We only care about positions in the same direction
            if pos_dir != target_dir:
                continue

            # Check correlation
            r = matrix.get(pair, {}).get(pos_pair, matrix.get(pos_pair, {}).get(pair, 0.0))
            if abs(r) >= self.correlation_threshold:
                correlated_count += 1
                correlated_pairs.append(f"{pos_pair} (r={r:.2f})")

        if correlated_count >= self.max_correlated_positions:
            reason = (
                f"Correlation limit reached: {pair} has {correlated_count} correlated "
                f"{target_dir} positions ({', '.join(correlated_pairs)}) >= max {self.max_correlated_positions} "
                f"(threshold={self.correlation_threshold})"
            )
            bot_logger.info(f"[CorrelationManager] REJECT: {reason}")
            return False, reason

        return True, "OK"

    def get_matrix_dict(self) -> Dict[str, Dict[str, float]]:
        """Return correlation matrix as a serializable dict."""
        return self.matrix


# Global module singleton
correlation_manager = CorrelationManager()
