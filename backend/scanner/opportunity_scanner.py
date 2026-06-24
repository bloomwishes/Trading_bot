"""
AutoTrader Pro - Opportunity Scanner
=====================================
Scans all available INR trading pairs for high-probability setups
using a composite scoring system based on RSI, volume spikes,
price momentum, and Bollinger Band squeezes.

Opportunities are scored 0-100, sorted by score, and the top results
are persisted to the database. Optionally, the scanner can auto-generate
trade signals for top-scoring pairs.
"""

import json
from typing import List, Dict, Any, Optional

import pandas as pd

from backend.config import settings
from backend.database import SessionLocal
from backend.models import Opportunity
from backend.utils.logger import bot_logger
from backend.utils.helpers import timestamp_now
from backend.exchange.exchange_manager import ExchangeManager
from backend.engine.indicators import (
    calculate_rsi,
    calculate_volume_sma,
    calculate_bollinger_bands,
)


class OpportunityScanner:
    """
    Market opportunity scanner that ranks trading pairs by composite score.

    Scoring Criteria (each worth 25 points, total 0-100):
      1. RSI extremes — oversold (< 30) or overbought (> 70).
      2. Volume spike — current volume > 3× 20-period average.
      3. Price momentum — > 2% move in the latest candle period.
      4. Bollinger squeeze — bandwidth < 0.02 (imminent breakout).

    Attributes:
        exchange_manager (ExchangeManager): Used to fetch pairs and candles.
        auto_trade (bool): If True and top score > 75, a trade signal dict
            is generated.
        auto_trade_threshold (int): Score above which auto-trade kicks in.
    """

    def __init__(
        self,
        exchange_manager: Optional[ExchangeManager] = None,
        auto_trade: bool = False,
        auto_trade_threshold: int = 75,
    ):
        self.exchange_manager = exchange_manager or ExchangeManager()
        self.auto_trade = auto_trade
        self.auto_trade_threshold = auto_trade_threshold

    # ------------------------------------------------------------------
    # Main scanning pipeline
    # ------------------------------------------------------------------
    def scan_all_pairs(self) -> List[Dict[str, Any]]:
        """
        Scan every INR pair on the exchange and score them.

        Returns:
            Top 10 opportunities as a list of dicts, sorted by score
            descending. Each dict contains:
              pair, score, rsi, rsi_score, volume_ratio, volume_score,
              momentum_pct, momentum_score, bandwidth, squeeze_score,
              current_price, recommendation, timestamp.
        """
        opportunities: List[Dict[str, Any]] = []

        # ------------------------------------------------------------------
        # 1. Get all available pairs
        # ------------------------------------------------------------------
        try:
            all_pairs = self._get_inr_pairs()
        except Exception as e:
            bot_logger.error(f"[Scanner] Failed to get trading pairs: {e}")
            return []

        if not all_pairs:
            bot_logger.warning("[Scanner] No INR pairs found")
            return []

        bot_logger.info(
            f"[Scanner] Scanning {len(all_pairs)} INR pairs..."
        )

        # ------------------------------------------------------------------
        # 2. Score each pair
        # ------------------------------------------------------------------
        for pair in all_pairs:
            try:
                opp = self._score_pair(pair)
                if opp is not None:
                    opportunities.append(opp)
            except Exception as e:
                bot_logger.error(
                    f"[Scanner] Error scoring {pair}: {e}"
                )

        # ------------------------------------------------------------------
        # 3. Sort and take top 10
        # ------------------------------------------------------------------
        opportunities.sort(key=lambda x: x["score"], reverse=True)
        top_opportunities = opportunities[:10]

        # ------------------------------------------------------------------
        # 4. Persist to database
        # ------------------------------------------------------------------
        self._save_opportunities(top_opportunities)

        # ------------------------------------------------------------------
        # 5. Auto-trade top opportunity if enabled and score is high enough
        # ------------------------------------------------------------------
        if (
            self.auto_trade
            and top_opportunities
            and top_opportunities[0]["score"] >= self.auto_trade_threshold
        ):
            top = top_opportunities[0]
            top["auto_trade_signal"] = {
                "pair": top["pair"],
                "action": top.get("recommendation", "BUY"),
                "score": top["score"],
                "reason": (
                    f"Auto-trade triggered: score {top['score']}/100 "
                    f"exceeds threshold {self.auto_trade_threshold}"
                ),
            }
            bot_logger.info(
                f"[Scanner] Auto-trade signal generated for "
                f"{top['pair']} (score={top['score']})"
            )

        if top_opportunities:
            best = top_opportunities[0]
            bot_logger.info(
                f"[Scanner] Scan complete. Top: {best['pair']} "
                f"(score={best['score']}). Scanned {len(all_pairs)} pairs, "
                f"scored {len(opportunities)}."
            )

        return top_opportunities

    # ------------------------------------------------------------------
    # Per-pair scoring
    # ------------------------------------------------------------------
    def _score_pair(self, pair: str) -> Optional[Dict[str, Any]]:
        """
        Fetch candle data for a pair and compute its composite score.

        Returns an opportunity dict or None if data is insufficient.
        """
        df = self.exchange_manager.get_candles(
            pair=pair, interval="15m", limit=50
        )
        if df is None or len(df) < 25:
            return None

        latest_close = float(df["close"].iloc[-1])
        if latest_close <= 0:
            return None

        total_score = 0
        detail: Dict[str, Any] = {
            "pair": pair,
            "current_price": latest_close,
            "timestamp": timestamp_now(),
        }

        # ---- Criterion 1: RSI extremes (25 points) ----
        rsi = calculate_rsi(df, period=14)
        latest_rsi = float(rsi.iloc[-1]) if not rsi.empty and not pd.isna(rsi.iloc[-1]) else 50.0
        detail["rsi"] = round(latest_rsi, 2)

        rsi_score = 0
        if latest_rsi < 30:
            # More oversold = higher score
            rsi_score = int(25 * (30 - latest_rsi) / 30)
            detail["rsi_condition"] = "OVERSOLD"
        elif latest_rsi > 70:
            rsi_score = int(25 * (latest_rsi - 70) / 30)
            detail["rsi_condition"] = "OVERBOUGHT"
        else:
            detail["rsi_condition"] = "NEUTRAL"

        rsi_score = min(25, max(0, rsi_score))
        detail["rsi_score"] = rsi_score
        total_score += rsi_score

        # ---- Criterion 2: Volume spike (25 points) ----
        vol_sma = calculate_volume_sma(df, period=20)
        latest_volume = float(df["volume"].iloc[-1])
        latest_vol_sma = (
            float(vol_sma.iloc[-1])
            if not vol_sma.empty and not pd.isna(vol_sma.iloc[-1])
            else 0
        )

        volume_ratio = (
            latest_volume / latest_vol_sma if latest_vol_sma > 0 else 0
        )
        detail["volume_ratio"] = round(volume_ratio, 2)

        volume_score = 0
        if volume_ratio > 3.0:
            # 3x = 25 points base, scale up for even higher ratios
            volume_score = min(25, int(25 * min(volume_ratio / 3.0, 1.0)))
            detail["volume_condition"] = "SPIKE"
        else:
            detail["volume_condition"] = "NORMAL"

        detail["volume_score"] = volume_score
        total_score += volume_score

        # ---- Criterion 3: Price momentum (25 points) ----
        prev_close = float(df["close"].iloc[-2]) if len(df) >= 2 else latest_close
        momentum_pct = (
            (latest_close - prev_close) / prev_close * 100
            if prev_close > 0
            else 0
        )
        detail["momentum_pct"] = round(momentum_pct, 4)

        momentum_score = 0
        if abs(momentum_pct) > 2.0:
            momentum_score = min(25, int(25 * min(abs(momentum_pct) / 2.0, 1.0)))
            detail["momentum_condition"] = "STRONG_UP" if momentum_pct > 0 else "STRONG_DOWN"
        else:
            detail["momentum_condition"] = "FLAT"

        detail["momentum_score"] = momentum_score
        total_score += momentum_score

        # ---- Criterion 4: Bollinger squeeze (25 points) ----
        _, _, _, bandwidth = calculate_bollinger_bands(df, period=20, std_dev=2)
        latest_bw = (
            float(bandwidth.iloc[-1])
            if not bandwidth.empty and not pd.isna(bandwidth.iloc[-1])
            else 1.0
        )
        detail["bandwidth"] = round(latest_bw, 6)

        squeeze_score = 0
        if latest_bw < 0.02:
            squeeze_score = min(25, int(25 * (0.02 - latest_bw) / 0.02))
            detail["squeeze_condition"] = "SQUEEZE"
        else:
            detail["squeeze_condition"] = "NORMAL"

        detail["squeeze_score"] = squeeze_score
        total_score += squeeze_score

        # ---- Composite ----
        detail["score"] = min(100, max(0, total_score))

        # Recommendation based on predominant signal
        if latest_rsi < 30 and momentum_pct > 0:
            detail["recommendation"] = "BUY"
        elif latest_rsi > 70 and momentum_pct < 0:
            detail["recommendation"] = "SELL"
        elif detail["score"] >= 50 and momentum_pct > 0:
            detail["recommendation"] = "BUY"
        elif detail["score"] >= 50 and momentum_pct < 0:
            detail["recommendation"] = "SELL"
        else:
            detail["recommendation"] = "WATCH"

        return detail

    # ------------------------------------------------------------------
    # Pair discovery
    # ------------------------------------------------------------------
    def _get_inr_pairs(self) -> List[str]:
        """
        Get all INR-denominated trading pairs from the exchange.

        Falls back to a static list if the exchange call fails.
        """
        try:
            # ExchangeManager doesn't expose a clean "list INR pairs" call
            # that's reliable across both CoinDCX and the Binance fallback,
            # so we scan the configured watchlist directly.
            return getattr(settings, "WATCHED_PAIRS", [
                "BTC/INR", "ETH/INR", "SOL/INR", "XRP/INR",
                "DOGE/INR", "ADA/INR", "MATIC/INR", "DOT/INR",
                "AVAX/INR", "LINK/INR",
            ])
        except Exception:
            return [
                "BTC/INR", "ETH/INR", "SOL/INR", "XRP/INR",
                "DOGE/INR",
            ]

    # ------------------------------------------------------------------
    # Database persistence
    # ------------------------------------------------------------------
    def _save_opportunities(self, opportunities: List[Dict[str, Any]]):
        """Save scored opportunities to the database."""
        if not opportunities:
            return

        db = SessionLocal()
        try:
            for opp in opportunities:
                db_opp = Opportunity(
                    pair=opp["pair"],
                    score=opp["score"],
                    scanner_data=json.dumps(opp, default=str),
                    created_at=opp.get("timestamp", timestamp_now()),
                )
                db.add(db_opp)
            db.commit()
        except Exception as e:
            db.rollback()
            bot_logger.error(
                f"[Scanner] Failed to save opportunities to DB: {e}"
            )
        finally:
            db.close()

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------
    def get_latest_opportunities(
        self, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Retrieve the most recent opportunities from the database.

        Args:
            limit: Maximum number of results to return.

        Returns:
            List of opportunity dicts.
        """
        db = SessionLocal()
        try:
            rows = (
                db.query(Opportunity)
                .order_by(Opportunity.created_at.desc())
                .limit(limit)
                .all()
            )
            results = []
            for row in rows:
                try:
                    details = json.loads(row.scanner_data) if getattr(row, "scanner_data", None) else {}
                except (json.JSONDecodeError, TypeError):
                    details = {}
                results.append(
                    {
                        "id": row.id,
                        "pair": row.pair,
                        "score": row.score,
                        "rsi": details.get("rsi", 0),
                        "volume_ratio": details.get("volume_ratio", 0),
                        "momentum_pct": details.get("momentum_pct", 0),
                        "bandwidth": details.get("bandwidth", 0),
                        "recommendation": details.get("recommendation", "WATCH"),
                        "details": details,
                        "created_at": str(row.created_at),
                    }
                )
            return results
        except Exception as e:
            bot_logger.error(
                f"[Scanner] Failed to query opportunities: {e}"
            )
            return []
        finally:
            db.close()
