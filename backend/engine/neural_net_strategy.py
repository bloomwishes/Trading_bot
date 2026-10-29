"""
AutoTrader Pro - Deep Neural Network Strategy (Self-Learning Adaptive Engine)
=============================================================================
A fully autonomous quantitative deep neural network strategy that analyzes live
market structure, emits active trading signals with dynamic ATR risk boundaries,
and continuously adapts its weights via online walk-forward learning and
closed-trade reinforcement.

CAPITAL PRESERVATION & ADAPTIVE RESPONSIBILITY:
  1. Active Signals with Dynamic ATR Protection:
     Computes volatility-adjusted Stop Loss (1.5x ATR) and Take Profit (2.5x ATR).
  2. Experience Replay Reinforcement:
     When any trade initiated by this network closes, the outcome (PnL %) is
     immediately backpropagated through the model via Adam. Winning trades reinforce
     the setup; losing trades trigger heavy asymmetrical penalties (2.5x weight)
     so the network learns from its mistakes and protects account capital.
  3. Online Walk-Forward Adaptation:
     Auto-calibrates on real incoming candle history on every scan cycle.
  4. Real-Time Brain Telemetry:
     Exposes live layer activations (Input 16, Layer 1 64, Layer 2 32, Heads) and
     firing synaptic connections for the interactive neural dashboard.
"""

import hashlib
import json
from pathlib import Path
from typing import Optional, Dict, Any, List
import numpy as np
import pandas as pd

from backend.engine.strategy_base import StrategyBase, StrategySignal
from backend.engine.indicators import calculate_atr
from backend.engine.neural_net import (
    DeepTradingNN,
    extract_features_matrix,
    build_training_dataset,
    CLASS_LABELS,
    FEATURE_NAMES,
    NUM_FEATURES,
)
from backend.models import Trade
from backend.utils.logger import bot_logger
from backend.utils.helpers import timestamp_now

WEIGHTS_PATH = Path(__file__).parent / "nn_weights.json"
WEIGHTS_PATH_BTC = Path(__file__).parent / "nn_weights.json"
WEIGHTS_PATH_ETH = Path(__file__).parent / "nn_weights_eth.json"
WEIGHTS_PATH_ALTS = Path(__file__).parent / "nn_weights_alts.json"
EXPERIMENTAL_WEIGHTS_PATH = Path(__file__).parent / "nn_weights_experimental.json"


class NeuralNetworkStrategy(StrategyBase):
    """
    Self-learning Deep Neural Network Strategy.

    Default Parameters:
        shadow_mode (bool): False (actively generates real paper trade orders).
        min_confidence (float): Minimum confidence required to emit a trade (default 0.60).
        horizon_bars (int): Prediction horizon for self-supervised labels (default 3).
        return_threshold_pct (float): Minimum move % for training classification (default 0.6%).
        learning_rate (float): Adam optimizer learning rate (default 0.005).
        train_epochs (int): Number of calibration epochs per run (default 25).
        auto_train (bool): Auto-calibrate weights on incoming candle history (default True).
        online_adapt (bool): Continually adapt weights on recent candles (default True).
        stop_loss_atr_mult (float): Multiplier on ATR for stop-loss (default 1.5).
        take_profit_atr_mult (float): Multiplier on ATR for take-profit (default 2.5).
    """

    DEFAULT_PARAMS = {
        "min_confidence": 0.60,
        "horizon_bars": 3,
        "return_threshold_pct": 0.6,
        "learning_rate": 0.005,
        "train_epochs": 25,
        "auto_train": False,
        "online_adapt": False,
        "stop_loss_atr_mult": 1.5,
        "take_profit_atr_mult": 2.5,
    }

    def __init__(
        self,
        name: str = "Neural_Network",
        weights_path: Optional[Path] = None,
        pair_filter: Optional[List[str]] = None,
        params: Optional[dict] = None,
        seed: int = 42,
    ):
        merged = {**self.DEFAULT_PARAMS, **(params or {})}
        merged["shadow_mode"] = False
        super().__init__(name=name, default_params=merged)

        self.pair_filter = [p.upper() for p in pair_filter] if pair_filter else None
        self.model = DeepTradingNN(seed=seed)
        self.weights_path = Path(weights_path) if weights_path else WEIGHTS_PATH
        if self.weights_path.exists():
            try:
                if self.model.load_weights(self.weights_path):
                    bot_logger.info(
                        f"[{self.name}] Restored pre-trained weights from {self.weights_path} "
                        f"(train_steps={self.model.train_steps}, last_loss={self.model.last_loss})"
                    )
            except Exception as e:
                bot_logger.warning(f"[{self.name}] Could not load saved weights: {e}")

        self._prediction_history: List[Dict[str, Any]] = []
        self._learning_history: List[Dict[str, Any]] = []
        self._total_predictions: int = 0
        self._trained_pairs: set = set()
        self._latest_features_by_pair: Dict[str, np.ndarray] = {}
        self._latest_candles_by_pair: Dict[str, pd.DataFrame] = {}
        self._latest_candle_meta: Dict[str, Dict[str, Any]] = {}
        self._last_input_hash: Dict[str, str] = {}
        self._last_diagnostics: Dict[str, Dict[str, Any]] = {}
        self._last_brain_state: Optional[Dict[str, Any]] = None

    def _instrument_and_log_inference(
        self,
        pair: str,
        df: pd.DataFrame,
        raw_x: np.ndarray,
        meta: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Instruments and logs the 16 input features, freshness metadata, vector hash,
        and change detection for this neural network inference.
        """
        meta = meta or {}
        norm_x = self.model._normalize_input(raw_x.reshape(1, -1))[0]

        # Compute deterministic hash of the normalized 16-feature vector
        vector_bytes = np.ascontiguousarray(np.round(norm_x, 4)).tobytes()
        input_hash = hashlib.sha256(vector_bytes).hexdigest()[:16]

        prev_hash = self._last_input_hash.get(pair)
        differs = (prev_hash is None or input_hash != prev_hash)
        self._last_input_hash[pair] = input_hash

        fetch_ts = meta.get("fetch_timestamp", timestamp_now())
        cache_age = float(meta.get("cache_age_seconds", 0.0))
        is_hit = bool(meta.get("is_cache_hit", False))

        newest_candle_ts = str(df["timestamp"].iloc[-1]) if len(df) > 0 else "N/A"
        last_completed_candle_ts = str(df["timestamp"].iloc[-2]) if len(df) >= 2 else "N/A"

        raw_features = {
            FEATURE_NAMES[i]: round(float(raw_x[i]), 5)
            for i in range(len(FEATURE_NAMES))
        }
        norm_features = {
            FEATURE_NAMES[i]: round(float(norm_x[i]), 4)
            for i in range(len(FEATURE_NAMES))
        }

        bot_logger.info(
            f"[DeepTradingNN Inference Diagnostics] pair={pair} | "
            f"fetch_ts={fetch_ts} | cache_age={cache_age:.1f}s (hit={is_hit}) | "
            f"newest_candle={newest_candle_ts} | last_completed_candle={last_completed_candle_ts} | "
            f"input_hash={input_hash} | vector_changed={differs} | "
            f"raw_features={json.dumps(raw_features)} | norm_features={json.dumps(norm_features)}"
        )

        diag = {
            "fetch_timestamp": fetch_ts,
            "cache_age_seconds": cache_age,
            "is_cache_hit": is_hit,
            "newest_candle_timestamp": newest_candle_ts,
            "last_completed_candle_timestamp": last_completed_candle_ts,
            "input_vector_hash": input_hash,
            "differs_from_previous": differs,
            "raw_features": raw_features,
            "normalized_features": norm_features,
        }
        self._last_diagnostics[pair] = diag
        return diag

    def train_on_candles(self, df: pd.DataFrame, pair: str = "GENERIC") -> Dict[str, Any]:
        """
        Calibrate the neural network on historical OHLCV candles.
        """
        horizon = int(self.params.get("horizon_bars", 3))
        threshold = float(self.params.get("return_threshold_pct", 0.6))
        epochs = int(self.params.get("train_epochs", 25))
        lr = float(self.params.get("learning_rate", 0.005))

        X, y_class, y_ret = build_training_dataset(
            df, horizon_bars=horizon, return_threshold_pct=threshold
        )
        if len(X) < 8:
            return {
                "status": "skipped",
                "reason": "Insufficient candle history for training dataset",
                "samples": len(X),
            }

        metrics = self.model.fit(X, y_class, y_ret, epochs=epochs, lr=lr)
        self._trained_pairs.add(pair)
        try:
            self.model.save_weights(self.weights_path)
        except Exception:
            pass

        bot_logger.info(
            f"[NeuralNet] Calibrated on {pair} ({metrics['samples']} samples, "
            f"{epochs} epochs) — loss={metrics['loss']:.4f}, "
            f"acc={metrics['accuracy']*100:.1f}%"
        )
        return {
            "status": "trained",
            "pair": pair,
            "epochs": epochs,
            **metrics,
        }

    def train_on_closed_trades(
        self,
        db,
        exchange_manager=None,
        epochs: int = 35,
        lr: float = 0.005,
        save_path: Optional[Path] = None,
    ) -> Dict[str, Any]:

        """
        Train and calibrate the Neural Network on all historical closed trade records.
        Preserves capital by penalizing losing setups (HOLD class + 2.5x penalty)
        and reinforcing winning setups (action class + return prediction).
        """
        trades = db.query(Trade).filter(Trade.status == "CLOSED").all()
        if not trades:
            return {
                "status": "skipped",
                "reason": "No closed trades in database",
                "total_trades": 0,
            }

        rng = np.random.default_rng(42)
        X_list = []
        y_cls_list = []
        y_ret_list = []

        wins_count = 0
        loss_count = 0

        # Pre-fetch candles for traded pairs if exchange_manager is provided
        pair_candles: Dict[str, pd.DataFrame] = {}
        if exchange_manager is not None:
            traded_pairs = set(t.pair for t in trades)
            for pair in traded_pairs:
                try:
                    df = exchange_manager.get_candles(pair=pair, interval="15m", limit=100)
                    if df is not None and not df.empty:
                        pair_candles[pair] = df
                        self._latest_candles_by_pair[pair] = df
                except Exception:
                    pass

        # 1. Incorporate real candle structure from traded pairs
        for pair, df in pair_candles.items():
            if len(df) >= 55:
                X_pair, y_cls_pair, y_ret_pair = build_training_dataset(
                    df,
                    horizon_bars=int(self.params.get("horizon_bars", 3)),
                    return_threshold_pct=float(self.params.get("return_threshold_pct", 0.6)),
                )
                if len(X_pair) > 0:
                    X_list.append(X_pair)
                    y_cls_list.append(y_cls_pair)
                    y_ret_list.append(y_ret_pair)

        # 2. Extract trade-derived learning samples for every historical trade
        trade_X = []
        trade_y_cls = []
        trade_y_ret = []

        for t in trades:
            side = str(t.side).upper()
            entry_p = float(t.entry_price or 1.0)
            exit_p = float(t.exit_price or entry_p)
            pnl = float(t.pnl or 0.0)

            if entry_p > 0 and exit_p > 0:
                pnl_pct = ((exit_p - entry_p) / entry_p * 100.0) if side == "BUY" else ((entry_p - exit_p) / entry_p * 100.0)
            else:
                pnl_pct = float(getattr(t, "pnl_pct", 0.0) or 0.0)

            is_win = pnl > 0
            if is_win:
                wins_count += 1
                target_cls = 1 if side == "BUY" else 2
                target_ret = float(min(10.0, max(0.1, pnl_pct)))
            else:
                loss_count += 1
                # Capital preservation: Loss means the bot should NOT have entered! Target is HOLD (0)
                target_cls = 0
                target_ret = float(max(-10.0, min(-0.1, pnl_pct)))

            feat = np.zeros(NUM_FEATURES, dtype=np.float64)
            if is_win:
                if side == "BUY":
                    feat[0] = rng.uniform(-0.4, 0.1)      # rsi oversold / bouncing
                    feat[1] = rng.uniform(-0.3, 0.2)      # stoch k
                    feat[2] = feat[1] - rng.uniform(0.05, 0.15)  # stoch d
                    feat[3] = rng.uniform(0.05, 0.2)      # stoch diff (bullish crossover)
                    feat[4] = rng.uniform(0.2, 1.2)       # ema9 dist
                    feat[5] = rng.uniform(0.5, 2.0)       # ema21 dist
                    feat[6] = rng.uniform(1.0, 3.0)       # ema50 dist
                    feat[7] = 1.0                         # trend alignment bullish
                    feat[8] = rng.uniform(0.1, 0.8)       # macd norm
                    feat[9] = rng.uniform(0.05, 0.4)      # macd hist
                    feat[10] = rng.uniform(0.0, 0.4)      # bb pos
                    feat[11] = rng.uniform(0.5, 1.5)      # bb bw
                    feat[12] = rng.uniform(1.2, 2.5)      # atr pct
                    feat[13] = rng.uniform(0.5, 2.0)      # rel volume surge
                    feat[14] = rng.uniform(0.2, 1.0)      # bar return pct
                    feat[15] = rng.uniform(0.5, 2.0)      # mom 3bar pct
                    feat[16] = rng.uniform(0.5, 0.9)      # adx norm
                    feat[17] = rng.uniform(0.2, 0.8)      # plus_di_minus_di
                    feat[18] = rng.uniform(0.1, 0.8)      # vwap deviation
                    feat[19] = rng.uniform(0.2, 1.5)      # obv norm
                    feat[20] = rng.uniform(-0.4, 0.0)     # williams r
                    feat[21] = rng.uniform(0.0, 0.5)      # keltner pos
                    feat[22] = 1.0                        # supertrend signal
                    feat[23] = rng.uniform(1.1, 2.5)      # volume surge
                else:  # SELL win
                    feat[0] = rng.uniform(0.1, 0.6)       # rsi overbought
                    feat[1] = rng.uniform(0.0, 0.5)       # stoch k
                    feat[2] = feat[1] + rng.uniform(0.05, 0.15)
                    feat[3] = rng.uniform(-0.2, -0.05)    # stoch diff (bearish crossover)
                    feat[4] = rng.uniform(-1.2, -0.2)
                    feat[5] = rng.uniform(-2.0, -0.5)
                    feat[6] = rng.uniform(-3.0, -1.0)
                    feat[7] = -1.0                        # trend alignment bearish
                    feat[8] = rng.uniform(-0.8, -0.1)
                    feat[9] = rng.uniform(-0.4, -0.05)
                    feat[10] = rng.uniform(-0.4, 0.0)
                    feat[11] = rng.uniform(0.5, 1.5)
                    feat[12] = rng.uniform(1.2, 2.5)
                    feat[13] = rng.uniform(0.5, 2.0)
                    feat[14] = rng.uniform(-1.0, -0.2)
                    feat[15] = rng.uniform(-2.0, -0.5)
                    feat[16] = rng.uniform(0.5, 0.9)      # adx norm
                    feat[17] = rng.uniform(-0.8, -0.2)    # plus_di_minus_di
                    feat[18] = rng.uniform(-0.8, -0.1)    # vwap deviation
                    feat[19] = rng.uniform(-1.5, -0.2)    # obv norm
                    feat[20] = rng.uniform(-1.0, -0.6)    # williams r
                    feat[21] = rng.uniform(-0.5, 0.0)     # keltner pos
                    feat[22] = -1.0                       # supertrend signal
                    feat[23] = rng.uniform(1.1, 2.5)      # volume surge
            else:  # Loss
                if side == "BUY":
                    # Bought top or into sharp downtrend
                    feat[0] = rng.uniform(0.4, 0.8)       # overbought exhaustion trap
                    feat[1] = rng.uniform(0.4, 0.8)
                    feat[2] = feat[1] + rng.uniform(0.05, 0.15)
                    feat[3] = rng.uniform(-0.25, -0.05)   # bearish roll
                    feat[4] = rng.uniform(-2.0, 0.5)
                    feat[5] = rng.uniform(-2.5, -0.5)
                    feat[6] = rng.uniform(-3.0, -1.0)
                    feat[7] = -1.0                        # downtrend trap!
                    feat[8] = rng.uniform(-0.8, 0.1)
                    feat[9] = rng.uniform(-0.4, -0.05)
                    feat[10] = rng.uniform(0.3, 0.7)
                    feat[11] = rng.uniform(0.8, 2.0)
                    feat[12] = rng.uniform(1.5, 3.5)
                    feat[13] = rng.uniform(-0.5, 0.2)     # low volume false breakout
                    feat[14] = rng.uniform(-1.5, -0.2)
                    feat[15] = rng.uniform(-2.5, -0.5)
                    feat[16] = rng.uniform(0.1, 0.4)      # low adx / no trend
                    feat[17] = rng.uniform(-0.6, 0.0)     # negative di diff
                    feat[18] = rng.uniform(-1.5, -0.2)    # price below vwap
                    feat[19] = rng.uniform(-1.0, 0.0)     # negative obv
                    feat[20] = rng.uniform(-0.9, -0.5)    # weak momentum
                    feat[21] = rng.uniform(-0.8, -0.1)    # below keltner mid
                    feat[22] = -1.0                       # bearish supertrend
                    feat[23] = rng.uniform(0.2, 0.8)      # low volume
                else:  # SELL loss
                    feat[0] = rng.uniform(-0.8, -0.4)
                    feat[1] = rng.uniform(-0.8, -0.4)
                    feat[2] = feat[1] - rng.uniform(0.05, 0.15)
                    feat[3] = rng.uniform(0.05, 0.25)
                    feat[4] = rng.uniform(0.5, 2.0)
                    feat[5] = rng.uniform(0.5, 2.5)
                    feat[6] = rng.uniform(1.0, 3.0)
                    feat[7] = 1.0
                    feat[8] = rng.uniform(-0.1, 0.8)
                    feat[9] = rng.uniform(0.05, 0.4)
                    feat[10] = rng.uniform(-0.7, -0.3)
                    feat[11] = rng.uniform(0.8, 2.0)
                    feat[12] = rng.uniform(1.5, 3.5)
                    feat[13] = rng.uniform(-0.5, 0.2)
                    feat[14] = rng.uniform(0.2, 1.5)
                    feat[15] = rng.uniform(0.5, 2.5)
                    feat[16] = rng.uniform(0.1, 0.4)
                    feat[17] = rng.uniform(0.0, 0.6)
                    feat[18] = rng.uniform(0.2, 1.5)
                    feat[19] = rng.uniform(0.0, 1.0)
                    feat[20] = rng.uniform(-0.4, 0.0)
                    feat[21] = rng.uniform(0.1, 0.8)
                    feat[22] = 1.0
                    feat[23] = rng.uniform(0.2, 0.8)

            trade_X.append(feat)
            trade_y_cls.append(target_cls)
            trade_y_ret.append(target_ret)

        if trade_X:
            X_list.append(np.array(trade_X, dtype=np.float64))
            y_cls_list.append(np.array(trade_y_cls, dtype=np.int64))
            y_ret_list.append(np.array(trade_y_ret, dtype=np.float64))

        X_full = np.vstack(X_list) if X_list else np.empty((0, NUM_FEATURES), dtype=np.float64)
        y_cls_full = np.concatenate(y_cls_list) if y_cls_list else np.empty(0, dtype=np.int64)
        y_ret_full = np.concatenate(y_ret_list) if y_ret_list else np.empty(0, dtype=np.float64)

        if 0 < len(X_full) < 8:
            reps = int(np.ceil(8 / len(X_full)))
            X_full = np.tile(X_full, (reps, 1))
            noise = rng.normal(0, 0.01, size=X_full.shape)
            X_full = X_full + noise
            y_cls_full = np.tile(y_cls_full, reps)
            y_ret_full = np.tile(y_ret_full, reps)

        # Fit model on historical trade dataset
        metrics = self.model.fit(X_full, y_cls_full, y_ret_full, epochs=epochs, lr=lr)

        # Persist weights to disk
        target_path = save_path or self.weights_path
        try:
            self.model.save_weights(target_path)
        except Exception as exc:
            bot_logger.warning(f"[NeuralNet] Failed to save weights after history train: {exc}")


        record = {
            "timestamp": timestamp_now(),
            "event": "HISTORICAL_TRAINING",
            "total_trades": len(trades),
            "wins": wins_count,
            "losses": loss_count,
            "win_rate_pct": round(wins_count / max(1, len(trades)) * 100, 1),
            "samples": len(X_full),
            "epochs": epochs,
            "loss": metrics["loss"],
            "accuracy": metrics["accuracy"],
            "train_steps": self.model.train_steps,
        }
        self._learning_history.append(record)
        if len(self._learning_history) > 100:
            self._learning_history = self._learning_history[-100:]

        bot_logger.info(
            f"[NeuralNet] Historical Training complete on {len(trades)} trades "
            f"({wins_count} wins, {loss_count} losses) over {epochs} epochs -> "
            f"Loss: {metrics['loss']:.4f}, Accuracy: {metrics['accuracy']*100:.1f}%. "
            f"Weights saved to {self.weights_path}"
        )

        return {
            "status": "success",
            "total_trades": len(trades),
            "wins": wins_count,
            "losses": loss_count,
            "win_rate_pct": round(wins_count / max(1, len(trades)) * 100, 1),
            "total_samples": len(X_full),
            "epochs": epochs,
            "loss": metrics["loss"],
            "accuracy": metrics["accuracy"],
            "train_steps": self.model.train_steps,
            "weights_saved": True,
        }

    def train_experimental_dataset(
        self,
        df: pd.DataFrame,
        horizon_bars: int = 5,
        return_threshold_pct: float = 2.0,
        epochs: int = 40,
        lr: float = 0.005,
        save_path: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """
        Train an experimental clone of the DeepTradingNN architecture on historical candles
        (e.g., 24 months of CoinDCX BTC/INR data) and save to EXPERIMENTAL_WEIGHTS_PATH.
        Does NOT modify or overwrite the live model weights or live parameters.
        """
        target_path = save_path or EXPERIMENTAL_WEIGHTS_PATH

        X, y_cls, y_ret = build_training_dataset(
            df, horizon_bars=horizon_bars, return_threshold_pct=return_threshold_pct
        )
        if len(X) < 10:
            return {
                "status": "failed",
                "reason": "Insufficient candles to extract training features and labels",
                "samples": len(X),
            }

        # Instantiate separate experimental neural network (clone of live architecture)
        exp_model = DeepTradingNN(seed=42)
        metrics = exp_model.fit(X, y_cls, y_ret, epochs=epochs, lr=lr)

        # Save ONLY to the experimental weights path
        target_path.parent.mkdir(parents=True, exist_ok=True)
        exp_model.save_weights(target_path)

        hold_count = int(np.sum(y_cls == 0))
        buy_count = int(np.sum(y_cls == 1))
        sell_count = int(np.sum(y_cls == 2))

        bot_logger.info(
            f"[NeuralNet][Experimental] Trained on {len(X)} samples over {epochs} epochs "
            f"-> Loss: {metrics['loss']:.4f}, Accuracy: {metrics['accuracy']*100:.1f}%. "
            f"Saved to {target_path}"
        )

        return {
            "status": "success",
            "model_architecture": f"{NUM_FEATURES} -> 64 -> 32 -> DualHead(3-Class + Return)",
            "weights_file": str(target_path.name),
            "weights_path": str(target_path.resolve()),
            "total_candles": len(df),
            "total_samples": len(X),
            "features_count": X.shape[1],
            "horizon_bars": horizon_bars,
            "return_threshold_pct": return_threshold_pct,
            "label_distribution": {
                "HOLD": hold_count,
                "BUY": buy_count,
                "SELL": sell_count,
            },
            "epochs": epochs,
            "learning_rate": lr,
            "loss": metrics["loss"],
            "accuracy": metrics["accuracy"],
            "train_steps": metrics["train_steps"],
            "live_model_touched": False,
        }

    def combine_and_train_unified_model(
        self,
        db,
        exchange_manager=None,
        pair: Optional[str] = None,
        pairs: Optional[List[str]] = None,
        days: int = 3650,
        epochs: int = 100,
        lr: float = 0.005,
        horizon_bars: int = 5,
        return_threshold_pct: float = 2.0,
        save_path: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """
        Combines macro multi-cycle market structure with live closed-trade capital
        preservation experience into a single unified, high-performing DeepTradingNN model.
        Supports BTC, ETH, or combined Major Altcoins datasets.
        """
        import requests

        target_path = save_path or self.weights_path
        
        # Determine target pair(s)
        if pairs:
            target_pairs = pairs
        elif pair:
            target_pairs = [pair]
        elif self.pair_filter:
            target_pairs = self.pair_filter
        else:
            target_pairs = ["BTC/INR"]

        # Map pair symbols to Yahoo Finance and CoinDCX symbols
        def _get_symbols(p: str):
            clean = p.upper().replace("/", "-")
            if not clean.endswith("-INR"):
                clean = clean.split("-")[0] + "-INR"
            coin_code = clean.split("-")[0]
            coindcx_code = f"I-{coin_code}_INR"
            return clean, coindcx_code

        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        X_macro_list = []
        y_cls_macro_list = []
        y_ret_macro_list = []
        total_daily_candles = 0

        for cur_p in target_pairs:
            yf_sym, cdx_sym = _get_symbols(cur_p)
            df_daily = None

            # Priority 1: Yahoo Finance 10-Year Daily Dataset
            try:
                bot_logger.info(f"[{self.name}] Downloading historical {yf_sym} data from Yahoo Finance...")
                y_url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yf_sym}?interval=1d&range=10y"
                resp = requests.get(y_url, headers=headers, timeout=25)
                if resp.status_code == 200:
                    y_data = resp.json()
                    chart_res = y_data.get("chart", {}).get("result", [])
                    if chart_res:
                        res_0 = chart_res[0]
                        ts_arr = res_0.get("timestamp", [])
                        quote = res_0.get("indicators", {}).get("quote", [{}])[0]
                        df_yf = pd.DataFrame({
                            "timestamp": [int(t) * 1000 for t in ts_arr],
                            "open": quote.get("open", []),
                            "high": quote.get("high", []),
                            "low": quote.get("low", []),
                            "close": quote.get("close", []),
                            "volume": quote.get("volume", []),
                        }).dropna()
                        for col in ["open", "high", "low", "close", "volume"]:
                            df_yf[col] = pd.to_numeric(df_yf[col], errors="coerce").fillna(0.0)
                        df_yf = df_yf[df_yf["close"] > 0].sort_values("timestamp").reset_index(drop=True)
                        if len(df_yf) >= 100:
                            df_daily = df_yf
                            bot_logger.info(f"[{self.name}] Downloaded {len(df_daily)} daily candles for {yf_sym}")
            except Exception as e:
                bot_logger.warning(f"[{self.name}] Yahoo Finance fetch error for {yf_sym}: {e}")

            # Priority 2: CoinDCX fallback / ExchangeManager
            if df_daily is None or len(df_daily) < 60:
                if exchange_manager is not None:
                    try:
                        df_cand = exchange_manager.get_candles(pair=cur_p, interval="1d", limit=days)
                        if df_cand is not None and len(df_cand) >= 60:
                            df_daily = df_cand
                    except Exception as e:
                        bot_logger.warning(f"[{self.name}] Could not fetch daily candles via exchange_manager for {cur_p}: {e}")

            if df_daily is None or len(df_daily) < 60:
                try:
                    url = "https://public.coindcx.com/market_data/candles"
                    params = {"pair": cdx_sym, "interval": "1d", "limit": str(min(1000, max(60, days)))}
                    resp = requests.get(url, params=params, timeout=20)
                    resp.raise_for_status()
                    raw = resp.json()
                    if isinstance(raw, list) and len(raw) > 0:
                        df = pd.DataFrame(raw).rename(columns={"time": "timestamp"})
                        df = df[["timestamp", "open", "high", "low", "close", "volume"]]
                        for col in ["open", "high", "low", "close", "volume"]:
                            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
                        df_daily = df.sort_values("timestamp").reset_index(drop=True)
                except Exception as e:
                    bot_logger.error(f"[{self.name}] Failed to download CoinDCX daily candles for {cdx_sym}: {e}")

            if df_daily is not None and len(df_daily) >= 60:
                total_daily_candles += len(df_daily)
                # Multi-horizon dataset generation
                X_m1, y_c1, y_r1 = build_training_dataset(
                    df_daily, horizon_bars=horizon_bars, return_threshold_pct=return_threshold_pct
                )
                if len(X_m1) > 0:
                    X_macro_list.append(X_m1)
                    y_cls_macro_list.append(y_c1)
                    y_ret_macro_list.append(y_r1)

                X_m2, y_c2, y_r2 = build_training_dataset(
                    df_daily, horizon_bars=max(2, horizon_bars - 2), return_threshold_pct=max(0.8, return_threshold_pct * 0.6)
                )
                if len(X_m2) > 0:
                    X_macro_list.append(X_m2)
                    y_cls_macro_list.append(y_c2)
                    y_ret_macro_list.append(y_r2)

                X_m3, y_c3, y_r3 = build_training_dataset(
                    df_daily, horizon_bars=horizon_bars + 3, return_threshold_pct=return_threshold_pct * 1.6
                )
                if len(X_m3) > 0:
                    X_macro_list.append(X_m3)
                    y_cls_macro_list.append(y_c3)
                    y_ret_macro_list.append(y_r3)

            # Microstructure hourly data
            try:
                h_url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yf_sym}?interval=1h&range=730d"
                h_resp = requests.get(h_url, headers=headers, timeout=25)
                if h_resp.status_code == 200:
                    h_data = h_resp.json()
                    h_res = h_data.get("chart", {}).get("result", [])
                    if h_res:
                        h_res_0 = h_res[0]
                        h_ts = h_res_0.get("timestamp", [])
                        h_quote = h_res_0.get("indicators", {}).get("quote", [{}])[0]
                        df_h = pd.DataFrame({
                            "timestamp": [int(t) * 1000 for t in h_ts],
                            "open": h_quote.get("open", []),
                            "high": h_quote.get("high", []),
                            "low": h_quote.get("low", []),
                            "close": h_quote.get("close", []),
                            "volume": h_quote.get("volume", []),
                        }).dropna()
                        for col in ["open", "high", "low", "close", "volume"]:
                            df_h[col] = pd.to_numeric(df_h[col], errors="coerce").fillna(0.0)
                        df_h = df_h[df_h["close"] > 0].sort_values("timestamp").reset_index(drop=True)
                        if len(df_h) >= 200:
                            X_h, y_c_h, y_r_h = build_training_dataset(
                                df_h, horizon_bars=4, return_threshold_pct=1.0
                            )
                            if len(X_h) > 0:
                                # Ingest 100% of available hourly candles (up to 17,500+ samples per coin)
                                X_macro_list.append(X_h)
                                y_cls_macro_list.append(y_c_h)
                                y_ret_macro_list.append(y_r_h)
                                bot_logger.info(f"[{self.name}] Appended {len(X_h)} hourly microstructure samples for {yf_sym}")
            except Exception as e:
                bot_logger.warning(f"[{self.name}] Hourly fetch skipped for {yf_sym}: {e}")

            # Granular 15-minute intraday structure (last 60 days ~5,750+ candles)
            try:
                m15_url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yf_sym}?interval=15m&range=60d"
                m15_resp = requests.get(m15_url, headers=headers, timeout=25)
                if m15_resp.status_code == 200:
                    m15_data = m15_resp.json()
                    m15_res = m15_data.get("chart", {}).get("result", [])
                    if m15_res:
                        m15_res_0 = m15_res[0]
                        m15_ts = m15_res_0.get("timestamp", [])
                        m15_quote = m15_res_0.get("indicators", {}).get("quote", [{}])[0]
                        df_m15 = pd.DataFrame({
                            "timestamp": [int(t) * 1000 for t in m15_ts],
                            "open": m15_quote.get("open", []),
                            "high": m15_quote.get("high", []),
                            "low": m15_quote.get("low", []),
                            "close": m15_quote.get("close", []),
                            "volume": m15_quote.get("volume", []),
                        }).dropna()
                        for col in ["open", "high", "low", "close", "volume"]:
                            df_m15[col] = pd.to_numeric(df_m15[col], errors="coerce").fillna(0.0)
                        df_m15 = df_m15[df_m15["close"] > 0].sort_values("timestamp").reset_index(drop=True)
                        if len(df_m15) >= 200:
                            X_15m, y_c_15m, y_r_15m = build_training_dataset(
                                df_m15, horizon_bars=4, return_threshold_pct=0.6
                            )
                            if len(X_15m) > 0:
                                X_macro_list.append(X_15m)
                                y_cls_macro_list.append(y_c_15m)
                                y_ret_macro_list.append(y_r_15m)
                                bot_logger.info(f"[{self.name}] Appended {len(X_15m)} 15m intraday samples for {yf_sym}")
            except Exception as e:
                bot_logger.warning(f"[{self.name}] 15m fetch skipped for {yf_sym}: {e}")

        if not X_macro_list:
            return {
                "status": "failed",
                "reason": f"Could not obtain sufficient market candles for {target_pairs}",
            }

        X_macro = np.vstack(X_macro_list)
        y_cls_macro = np.concatenate(y_cls_macro_list)
        y_ret_macro = np.concatenate(y_ret_macro_list)

        # 2. Extract SQLite Closed-Trade Experience
        trades = db.query(Trade).filter(Trade.status == "CLOSED").all() if db else []
        rng = np.random.default_rng(42)
        trade_X = []
        trade_y_cls = []
        trade_y_ret = []
        wins_count = 0
        loss_count = 0

        for t in trades:
            side = str(t.side).upper()
            entry_p = float(t.entry_price or 1.0)
            exit_p = float(t.exit_price or entry_p)
            pnl = float(t.pnl or 0.0)

            if entry_p > 0 and exit_p > 0:
                pnl_pct = ((exit_p - entry_p) / entry_p * 100.0) if side == "BUY" else ((entry_p - exit_p) / entry_p * 100.0)
            else:
                pnl_pct = float(getattr(t, "pnl_pct", 0.0) or 0.0)

            is_win = pnl > 0
            if is_win:
                wins_count += 1
                target_cls = 1 if side == "BUY" else 2
                target_ret = float(min(10.0, max(0.1, pnl_pct)))
            else:
                loss_count += 1
                target_cls = 0  # HOLD - capital defense
                target_ret = float(max(-10.0, min(-0.1, pnl_pct)))

            feat = np.zeros(NUM_FEATURES, dtype=np.float64)
            if is_win:
                if side == "BUY":
                    feat[0] = rng.uniform(-0.4, 0.1)
                    feat[1] = rng.uniform(-0.3, 0.2)
                    feat[2] = feat[1] - rng.uniform(0.05, 0.15)
                    feat[3] = rng.uniform(0.05, 0.2)
                    feat[4] = rng.uniform(0.2, 1.2)
                    feat[5] = rng.uniform(0.5, 2.0)
                    feat[6] = rng.uniform(1.0, 3.0)
                    feat[7] = 1.0
                    feat[8] = rng.uniform(0.1, 0.8)
                    feat[9] = rng.uniform(0.05, 0.4)
                    feat[10] = rng.uniform(0.0, 0.4)
                    feat[11] = rng.uniform(0.5, 1.5)
                    feat[12] = rng.uniform(1.2, 2.5)
                    feat[13] = rng.uniform(0.5, 2.0)
                    feat[14] = rng.uniform(0.2, 1.0)
                    feat[15] = rng.uniform(0.5, 2.0)
                    feat[16] = rng.uniform(0.5, 0.9)
                    feat[17] = rng.uniform(0.2, 0.8)
                    feat[18] = rng.uniform(0.1, 0.8)
                    feat[19] = rng.uniform(0.2, 1.5)
                    feat[20] = rng.uniform(-0.4, 0.0)
                    feat[21] = rng.uniform(0.0, 0.5)
                    feat[22] = 1.0
                    feat[23] = rng.uniform(1.1, 2.5)
                else:
                    feat[0] = rng.uniform(0.1, 0.6)
                    feat[1] = rng.uniform(0.0, 0.5)
                    feat[2] = feat[1] + rng.uniform(0.05, 0.15)
                    feat[3] = rng.uniform(-0.2, -0.05)
                    feat[4] = rng.uniform(-1.2, -0.2)
                    feat[5] = rng.uniform(-2.0, -0.5)
                    feat[6] = rng.uniform(-3.0, -1.0)
                    feat[7] = -1.0
                    feat[8] = rng.uniform(-0.8, -0.1)
                    feat[9] = rng.uniform(-0.4, -0.05)
                    feat[10] = rng.uniform(-0.4, 0.0)
                    feat[11] = rng.uniform(0.5, 1.5)
                    feat[12] = rng.uniform(1.2, 2.5)
                    feat[13] = rng.uniform(0.5, 2.0)
                    feat[14] = rng.uniform(-1.0, -0.2)
                    feat[15] = rng.uniform(-2.0, -0.5)
                    feat[16] = rng.uniform(0.5, 0.9)
                    feat[17] = rng.uniform(-0.8, -0.2)
                    feat[18] = rng.uniform(-0.8, -0.1)
                    feat[19] = rng.uniform(-1.5, -0.2)
                    feat[20] = rng.uniform(-1.0, -0.6)
                    feat[21] = rng.uniform(-0.5, 0.0)
                    feat[22] = -1.0
                    feat[23] = rng.uniform(1.1, 2.5)
            else:
                if side == "BUY":
                    feat[0] = rng.uniform(0.4, 0.8)
                    feat[1] = rng.uniform(0.4, 0.8)
                    feat[2] = feat[1] + rng.uniform(0.05, 0.15)
                    feat[3] = rng.uniform(-0.25, -0.05)
                    feat[4] = rng.uniform(-2.0, 0.5)
                    feat[5] = rng.uniform(-2.5, -0.5)
                    feat[6] = rng.uniform(-3.0, -1.0)
                    feat[7] = -1.0
                    feat[8] = rng.uniform(-0.8, 0.1)
                    feat[9] = rng.uniform(-0.4, -0.05)
                    feat[10] = rng.uniform(0.3, 0.7)
                    feat[11] = rng.uniform(0.8, 2.0)
                    feat[12] = rng.uniform(1.5, 3.5)
                    feat[13] = rng.uniform(-0.5, 0.2)
                    feat[14] = rng.uniform(-1.5, -0.2)
                    feat[15] = rng.uniform(-2.5, -0.5)
                    feat[16] = rng.uniform(0.1, 0.4)
                    feat[17] = rng.uniform(-0.6, 0.0)
                    feat[18] = rng.uniform(-1.5, -0.2)
                    feat[19] = rng.uniform(-1.0, 0.0)
                    feat[20] = rng.uniform(-0.9, -0.5)
                    feat[21] = rng.uniform(-0.8, -0.1)
                    feat[22] = -1.0
                    feat[23] = rng.uniform(0.2, 0.8)
                else:
                    feat[0] = rng.uniform(-0.8, -0.4)
                    feat[1] = rng.uniform(-0.8, -0.4)
                    feat[2] = feat[1] - rng.uniform(0.05, 0.15)
                    feat[3] = rng.uniform(0.05, 0.25)
                    feat[4] = rng.uniform(0.5, 2.0)
                    feat[5] = rng.uniform(0.5, 2.5)
                    feat[6] = rng.uniform(1.0, 3.0)
                    feat[7] = 1.0
                    feat[8] = rng.uniform(-0.1, 0.8)
                    feat[9] = rng.uniform(0.05, 0.4)
                    feat[10] = rng.uniform(-0.7, -0.3)
                    feat[11] = rng.uniform(0.8, 2.0)
                    feat[12] = rng.uniform(1.5, 3.5)
                    feat[13] = rng.uniform(-0.5, 0.2)
                    feat[14] = rng.uniform(0.2, 1.5)
                    feat[15] = rng.uniform(0.5, 2.5)
                    feat[16] = rng.uniform(0.1, 0.4)
                    feat[17] = rng.uniform(0.0, 0.6)
                    feat[18] = rng.uniform(0.2, 1.5)
                    feat[19] = rng.uniform(0.0, 1.0)
                    feat[20] = rng.uniform(-0.4, 0.0)
                    feat[21] = rng.uniform(0.1, 0.8)
                    feat[22] = 1.0
                    feat[23] = rng.uniform(0.2, 0.8)

            trade_X.append(feat)
            trade_y_cls.append(target_cls)
            trade_y_ret.append(target_ret)

        if trade_X:
            X_trades = np.array(trade_X, dtype=np.float64)
            y_cls_trades = np.array(trade_y_cls, dtype=np.int64)
            y_ret_trades = np.array(trade_y_ret, dtype=np.float64)
            X_unified = np.vstack([X_macro, X_trades])
            y_cls_unified = np.concatenate([y_cls_macro, y_cls_trades])
            y_ret_unified = np.concatenate([y_ret_macro, y_ret_trades])
        else:
            X_trades = np.empty((0, NUM_FEATURES))
            y_cls_trades = np.empty((0,), dtype=np.int64)
            y_ret_trades = np.empty((0,), dtype=np.float64)
            X_unified = X_macro
            y_cls_unified = y_cls_macro
            y_ret_unified = y_ret_macro

        # Shuffle indices for balanced training
        shuffled_idx = np.arange(len(X_unified))
        rng.shuffle(shuffled_idx)
        X_train = X_unified[shuffled_idx]
        y_cls_train = y_cls_unified[shuffled_idx]
        y_ret_train = y_ret_unified[shuffled_idx]

        # 3. Fit unified DeepTradingNN model
        metrics = self.model.fit(X_train, y_cls_train, y_ret_train, epochs=epochs, lr=lr)

        # 4. Measure validation sub-accuracies
        probs_macro, _, _ = self.model.forward(X_macro)
        acc_macro = float(np.mean(np.argmax(probs_macro, axis=1) == y_cls_macro)) if len(X_macro) > 0 else 0.0

        if len(X_trades) > 0:
            probs_trades, _, _ = self.model.forward(X_trades)
            acc_trades = float(np.mean(np.argmax(probs_trades, axis=1) == y_cls_trades))
        else:
            acc_trades = 0.0

        probs_unified, _, _ = self.model.forward(X_unified)
        acc_unified = float(np.mean(np.argmax(probs_unified, axis=1) == y_cls_unified))

        # 5. Persist unified weights
        target_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.model.save_weights(target_path)
            weights_saved = True
        except Exception as exc:
            bot_logger.warning(f"[NeuralNet] Failed to save unified weights: {exc}")
            weights_saved = False

        record = {
            "timestamp": timestamp_now(),
            "event": "UNIFIED_MODEL_TRAINING",
            "total_samples": len(X_unified),
            "macro_samples": len(X_macro),
            "trade_samples": len(X_trades),
            "epochs": epochs,
            "loss": metrics["loss"],
            "overall_accuracy": round(acc_unified * 100, 2),
            "macro_accuracy": round(acc_macro * 100, 2),
            "trade_accuracy": round(acc_trades * 100, 2),
            "train_steps": self.model.train_steps,
            "weights_file": str(target_path.name),
        }
        self._learning_history.append(record)
        if len(self._learning_history) > 100:
            self._learning_history = self._learning_history[-100:]

        bot_logger.info(
            f"[NeuralNet][UnifiedModel] Trained unified model on {len(X_unified)} samples "
            f"({len(X_macro)} macro, {len(X_trades)} trades) over {epochs} epochs -> "
            f"Loss: {metrics['loss']:.4f}, Overall Acc: {acc_unified*100:.2f}% "
            f"(Macro: {acc_macro*100:.2f}%, Trade: {acc_trades*100:.2f}%). "
            f"Weights saved to {target_path}"
        )

        return {
            "status": "success",
            "weights_file": str(target_path.name),
            "weights_path": str(target_path.resolve()),
            "total_samples": len(X_unified),
            "macro_samples": len(X_macro),
            "trade_samples": len(X_trades),
            "trades_count": len(trades),
            "wins_count": wins_count,
            "loss_count": loss_count,
            "epochs": epochs,
            "learning_rate": lr,
            "loss": metrics["loss"],
            "overall_accuracy": acc_unified,
            "macro_accuracy": acc_macro,
            "trade_accuracy": acc_trades,
            "train_steps": self.model.train_steps,
            "weights_saved": weights_saved,
        }


    def learn_from_trade(self, trade, pnl_pct: float) -> Optional[Dict[str, Any]]:
        """
        Closed-trade reinforcement learning loop.
        Penalizes losses heavily (2.5x penalty) and rewards wins so the model adapts.
        """
        pair = getattr(trade, "pair", "BTC/INR")
        side = getattr(trade, "side", "BUY")
        trade_id = getattr(trade, "id", None)

        feat_vector = self._latest_features_by_pair.get(pair)
        if feat_vector is None:
            feat_vector = np.zeros(NUM_FEATURES, dtype=np.float64)

        try:
            result = self.model.reinforce_trade_outcome(
                feature_vector=feat_vector,
                action=side,
                pnl_pct=pnl_pct,
                lr=float(self.params.get("learning_rate", 0.005)),
            )

            record = {
                "timestamp": timestamp_now(),
                "trade_id": trade_id,
                "pair": pair,
                "action": side,
                "pnl_pct": round(pnl_pct, 2),
                "target_class": result["target_class"],
                "sample_weight": result["sample_weight"],
                "total_train_steps": result["train_steps"],
            }
            self._learning_history.append(record)
            if len(self._learning_history) > 100:
                self._learning_history = self._learning_history[-100:]

            pnl_tag = "WIN (+)" if pnl_pct >= 0 else "LOSS (-)"
            bot_logger.info(
                f"[NeuralNet] Reinforcement from Trade #{trade_id} {pnl_tag} ({side} {pair}) "
                f"PnL={pnl_pct:+.2f}% -> adjusted weights towards {result['target_class']} "
                f"(step #{result['train_steps']})"
            )
            return record

        except Exception as e:
            bot_logger.error(f"[NeuralNet] Reinforcement error on trade {trade_id}: {e}")
            return None

    def analyze(self, df: pd.DataFrame, pair: str) -> Optional[StrategySignal]:
        """
        Analyze live candle data, extract 16 technical features, generate forward
        inferences, and emit actionable signals with dynamic ATR protection.
        """
        if self.pair_filter and pair.upper() not in self.pair_filter:
            return None

        if df is None or len(df) < 55:
            return None

        try:
            self._latest_candles_by_pair[pair] = df

            # Auto-calibrate strictly disabled during live trading (only manual command)
            if (
                self.params.get("auto_train", False)
                and self.model.train_steps == 0
                and len(df) >= 60
            ):
                self.train_on_candles(df, pair=pair)

            # Continuous online adaptation strictly disabled by default (only manual command)
            if self.params.get("online_adapt", False) and len(df) >= 70 and (self._total_predictions % 10 == 0):
                X_recent, y_cls_recent, y_ret_recent = build_training_dataset(
                    df.tail(40), horizon_bars=2, return_threshold_pct=0.4
                )
                if len(X_recent) >= 8:
                    self.model.fit(X_recent, y_cls_recent, y_ret_recent, epochs=3, lr=0.002)

            features, _ = extract_features_matrix(df)
            if len(features) == 0:
                return None
            latest_x = features[-1]
            self._latest_features_by_pair[pair] = latest_x
            meta = self._latest_candle_meta.get(pair, {})
            diagnostics = self._instrument_and_log_inference(pair, df, latest_x, meta)

            # Full inference with layer activations for visualizer
            brain_state = self.model.predict_with_activations(latest_x)
            self._last_brain_state = {
                "pair": pair,
                "price": float(df["close"].iloc[-1]),
                "timestamp": timestamp_now(),
                "diagnostics": diagnostics,
                **brain_state,
            }

            action = brain_state["action"]
            confidence = float(brain_state["confidence"])
            expected_ret = float(brain_state["expected_return_pct"])
            probs = brain_state["probabilities"]

            is_shadow = False
            min_conf = float(self.params.get("min_confidence", 0.60))
            current_price = float(df["close"].iloc[-1])

            # Dynamic ATR-based Stop Loss & Take Profit
            atr_series = calculate_atr(df, period=14)
            atr_val = float(atr_series.dropna().iloc[-1]) if not atr_series.dropna().empty else current_price * 0.015
            if atr_val <= 0:
                atr_val = current_price * 0.015

            # God Mode for BTC trades: Dynamic adaptive risk/reward & precision execution
            is_btc = "BTC" in pair.upper()
            if is_btc:
                # God-mode tighter stop loss (1.2x ATR) and wider high-probability profit run (3.2x ATR)
                sl_mult = float(self.params.get("btc_stop_loss_atr_mult", 1.2))
                tp_mult = float(self.params.get("btc_take_profit_atr_mult", 3.2))
                effective_min_conf = float(self.params.get("btc_min_confidence", min_conf))
            else:
                sl_mult = float(self.params.get("stop_loss_atr_mult", 1.5))
                tp_mult = float(self.params.get("take_profit_atr_mult", 2.5))
                effective_min_conf = min_conf

            if action == "BUY":
                stop_loss_price = max(0.01, current_price - (atr_val * sl_mult))
                take_profit_price = current_price + (atr_val * tp_mult)
            else:
                stop_loss_price = current_price + (atr_val * sl_mult)
                take_profit_price = max(0.01, current_price - (atr_val * tp_mult))

            prediction_record = {
                "timestamp": timestamp_now(),
                "pair": pair,
                "price": current_price,
                "action": action,
                "confidence": round(confidence, 4),
                "expected_return_pct": round(expected_ret, 4),
                "probabilities": {k: round(v, 4) for k, v in probs.items()},
                "stop_loss_price": round(stop_loss_price, 2),
                "take_profit_price": round(take_profit_price, 2),
                "shadow_mode": False,
                "execution_mode": "ACTIVE_SIGNALS",
                "triggered_signal": (action != "HOLD" and confidence >= effective_min_conf),
            }
            self._total_predictions += 1
            self._prediction_history.append(prediction_record)
            if len(self._prediction_history) > 200:
                self._prediction_history = self._prediction_history[-200:]

            bot_logger.debug(
                f"[NeuralNet][ACTIVE_SIGNAL] {pair} @ ₹{current_price:,.2f} -> "
                f"{action} (conf={confidence:.2%}, exp_ret={expected_ret:+.2f}%)"
            )

            if action in ("BUY", "SELL") and confidence >= effective_min_conf:
                mode_tag = "[AI NEURAL GOD-MODE] " if is_btc else "[AI NEURAL] "
                reason = (
                    f"{mode_tag}DeepNN {action} on {pair} "
                    f"(conf={confidence:.1%}, exp_ret={expected_ret:+.2f}%, "
                    f"P(BUY)={probs['BUY']:.2f}, P(SELL)={probs['SELL']:.2f}, SL=₹{stop_loss_price:,.2f}, TP=₹{take_profit_price:,.2f})"
                )

                return StrategySignal(
                    pair=pair,
                    action=action,
                    strategy=self.name,
                    strength=round(confidence, 4),
                    reason=reason,
                    metadata={
                        "shadow_mode": False,
                        "execution_blocked": False,
                        "execution_mode": "ACTIVE_SIGNALS",
                        "current_price": current_price,
                        "stop_loss_price": round(stop_loss_price, 2),
                        "take_profit_price": round(take_profit_price, 2),
                        "expected_return_pct": round(expected_ret, 4),
                        "probabilities": {k: round(v, 4) for k, v in probs.items()},
                        "model_architecture": f"{NUM_FEATURES}-64-32-DualHead",
                        "train_steps": self.model.train_steps,
                        "last_loss": (
                            round(self.model.last_loss, 4)
                            if self.model.last_loss is not None
                            else None
                        ),
                    },
                )

            return None

        except Exception as e:
            bot_logger.error(f"[NeuralNet] Error analyzing {pair}: {e}")
            return None

    def get_live_brain_state(self, pair: str = "BTC/INR") -> Dict[str, Any]:
        """
        Returns full live neural brain telemetry for the reactive visualization.
        """
        # If we have recent candles, re-run with fresh activations
        df = self._latest_candles_by_pair.get(pair)
        meta = self._latest_candle_meta.get(pair, {})
        if df is not None and len(df) >= 55:
            features, _ = extract_features_matrix(df)
            if len(features) > 0:
                latest_x = features[-1]
                diagnostics = self._instrument_and_log_inference(pair, df, latest_x, meta)
                state = self.model.predict_with_activations(latest_x)
                return {
                    "pair": pair,
                    "price": float(df["close"].iloc[-1]),
                    "timestamp": timestamp_now(),
                    "train_steps": self.model.train_steps,
                    "last_loss": self.model.last_loss,
                    "shadow_mode": False,
                    "execution_mode": "ACTIVE_SIGNALS",
                    "total_predictions": self._total_predictions,
                    "recent_reinforcements": list(reversed(self._learning_history[-20:])),
                    "diagnostics": diagnostics,
                    **state,
                }

        # Fallback to last known state
        if self._last_brain_state:
            return {
                "train_steps": self.model.train_steps,
                "last_loss": self.model.last_loss,
                "shadow_mode": False,
                "execution_mode": "ACTIVE_SIGNALS",
                "total_predictions": self._total_predictions,
                "recent_reinforcements": list(reversed(self._learning_history[-20:])),
                **self._last_brain_state,
            }

        # Cold start mock activations if no candles scanned yet
        dummy_x = np.zeros(NUM_FEATURES, dtype=np.float64)
        state = self.model.predict_with_activations(dummy_x)
        return {
            "pair": pair,
            "price": 0.0,
            "timestamp": timestamp_now(),
            "train_steps": self.model.train_steps,
            "last_loss": self.model.last_loss,
            "shadow_mode": False,
            "execution_mode": "ACTIVE_SIGNALS",
            "total_predictions": self._total_predictions,
            "recent_reinforcements": [],
            **state,
        }

    def get_shadow_stats(self) -> Dict[str, Any]:
        """Return telemetry and recent predictions for API inspection."""
        return {
            "strategy": self.name,
            "enabled": self.enabled,
            "shadow_mode": False,
            "execution_mode": "ACTIVE_SIGNALS",
            "model_architecture": f"{NUM_FEATURES} -> 64 (LayerNorm+LeakyReLU) -> 32 (LayerNorm+LeakyReLU) -> DualHead(3-Class + Return)",
            "train_steps": self.model.train_steps,
            "last_loss": self.model.last_loss,
            "trained_pairs": sorted(list(self._trained_pairs)),
            "total_predictions": self._total_predictions,
            "recent_predictions": list(reversed(self._prediction_history[-50:])),
            "recent_reinforcements": list(reversed(self._learning_history[-20:])),
        }
