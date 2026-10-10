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
)
from backend.models import Trade
from backend.utils.logger import bot_logger
from backend.utils.helpers import timestamp_now

WEIGHTS_PATH = Path(__file__).parent / "nn_weights.json"


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
        "auto_train": True,
        "online_adapt": True,
        "stop_loss_atr_mult": 1.5,
        "take_profit_atr_mult": 2.5,
    }

    def __init__(self, params: Optional[dict] = None, seed: int = 42):
        merged = {**self.DEFAULT_PARAMS, **(params or {})}
        merged["shadow_mode"] = False
        super().__init__(name="Neural_Network", default_params=merged)

        self.model = DeepTradingNN(seed=seed)
        self.weights_path = WEIGHTS_PATH
        if self.weights_path.exists():
            try:
                if self.model.load_weights(self.weights_path):
                    bot_logger.info(
                        f"[NeuralNet] Restored pre-trained weights from {self.weights_path} "
                        f"(train_steps={self.model.train_steps}, last_loss={self.model.last_loss})"
                    )
            except Exception as e:
                bot_logger.warning(f"[NeuralNet] Could not load saved weights: {e}")

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

            feat = np.zeros(16, dtype=np.float64)
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

            trade_X.append(feat)
            trade_y_cls.append(target_cls)
            trade_y_ret.append(target_ret)

        if trade_X:
            X_list.append(np.array(trade_X, dtype=np.float64))
            y_cls_list.append(np.array(trade_y_cls, dtype=np.int64))
            y_ret_list.append(np.array(trade_y_ret, dtype=np.float64))

        X_full = np.vstack(X_list)
        y_cls_full = np.concatenate(y_cls_list)
        y_ret_full = np.concatenate(y_ret_list)

        # Fit model on historical trade dataset
        metrics = self.model.fit(X_full, y_cls_full, y_ret_full, epochs=epochs, lr=lr)

        # Persist weights to disk
        try:
            self.model.save_weights(self.weights_path)
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
            feat_vector = np.zeros(16, dtype=np.float64)

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
        if df is None or len(df) < 55:
            return None

        try:
            self._latest_candles_by_pair[pair] = df

            # Auto-calibrate on first encounter
            if (
                self.params.get("auto_train", True)
                and self.model.train_steps == 0
                and len(df) >= 60
            ):
                self.train_on_candles(df, pair=pair)

            # Continuous online adaptation step on latest regime
            if self.params.get("online_adapt", True) and len(df) >= 70 and (self._total_predictions % 10 == 0):
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

            sl_mult = float(self.params.get("stop_loss_atr_mult", 1.5))
            tp_mult = float(self.params.get("take_profit_atr_mult", 2.5))

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
                "triggered_signal": (action != "HOLD" and confidence >= min_conf),
            }
            self._total_predictions += 1
            self._prediction_history.append(prediction_record)
            if len(self._prediction_history) > 200:
                self._prediction_history = self._prediction_history[-200:]

            bot_logger.debug(
                f"[NeuralNet][ACTIVE_SIGNAL] {pair} @ ₹{current_price:,.2f} -> "
                f"{action} (conf={confidence:.2%}, exp_ret={expected_ret:+.2f}%)"
            )

            if action in ("BUY", "SELL") and confidence >= min_conf:
                mode_tag = "[AI NEURAL] "
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
                        "model_architecture": "16-64-32-DualHead",
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
        dummy_x = np.zeros(16, dtype=np.float64)
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
            "model_architecture": "16 -> 64 (LayerNorm+LeakyReLU) -> 32 (LayerNorm+LeakyReLU) -> DualHead(3-Class + Return)",
            "train_steps": self.model.train_steps,
            "last_loss": self.model.last_loss,
            "trained_pairs": sorted(list(self._trained_pairs)),
            "total_predictions": self._total_predictions,
            "recent_predictions": list(reversed(self._prediction_history[-50:])),
            "recent_reinforcements": list(reversed(self._learning_history[-20:])),
        }
