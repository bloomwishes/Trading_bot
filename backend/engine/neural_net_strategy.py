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
from backend.utils.logger import bot_logger
from backend.utils.helpers import timestamp_now


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
        "shadow_mode": False,
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
        merged["shadow_mode"] = bool(merged.get("shadow_mode", False))
        super().__init__(name="Neural_Network", default_params=merged)

        self.model = DeepTradingNN(seed=seed)
        self._prediction_history: List[Dict[str, Any]] = []
        self._learning_history: List[Dict[str, Any]] = []
        self._total_predictions: int = 0
        self._trained_pairs: set = set()
        self._latest_features_by_pair: Dict[str, np.ndarray] = {}
        self._latest_candles_by_pair: Dict[str, pd.DataFrame] = {}
        self._last_brain_state: Optional[Dict[str, Any]] = None

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

            # Full inference with layer activations for visualizer
            brain_state = self.model.predict_with_activations(latest_x)
            self._last_brain_state = {
                "pair": pair,
                "price": float(df["close"].iloc[-1]),
                "timestamp": timestamp_now(),
                **brain_state,
            }

            action = brain_state["action"]
            confidence = float(brain_state["confidence"])
            expected_ret = float(brain_state["expected_return_pct"])
            probs = brain_state["probabilities"]

            is_shadow = bool(self.params.get("shadow_mode", False))
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
                "shadow_mode": is_shadow,
                "triggered_signal": (action != "HOLD" and confidence >= min_conf),
            }
            self._total_predictions += 1
            self._prediction_history.append(prediction_record)
            if len(self._prediction_history) > 200:
                self._prediction_history = self._prediction_history[-200:]

            mode_str = "SHADOW" if is_shadow else "LIVE_SIGNAL"
            bot_logger.debug(
                f"[NeuralNet][{mode_str}] {pair} @ ₹{current_price:,.2f} -> "
                f"{action} (conf={confidence:.2%}, exp_ret={expected_ret:+.2f}%)"
            )

            if action in ("BUY", "SELL") and confidence >= min_conf:
                mode_tag = "[SHADOW] " if is_shadow else "[AI NEURAL] "
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
                        "shadow_mode": is_shadow,
                        "execution_blocked": is_shadow,
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
        if df is not None and len(df) >= 55:
            features, _ = extract_features_matrix(df)
            if len(features) > 0:
                latest_x = features[-1]
                state = self.model.predict_with_activations(latest_x)
                return {
                    "pair": pair,
                    "price": float(df["close"].iloc[-1]),
                    "timestamp": timestamp_now(),
                    "train_steps": self.model.train_steps,
                    "last_loss": self.model.last_loss,
                    "shadow_mode": bool(self.params.get("shadow_mode", False)),
                    "total_predictions": self._total_predictions,
                    "recent_reinforcements": list(reversed(self._learning_history[-20:])),
                    **state,
                }

        # Fallback to last known state
        if self._last_brain_state:
            return {
                "train_steps": self.model.train_steps,
                "last_loss": self.model.last_loss,
                "shadow_mode": bool(self.params.get("shadow_mode", False)),
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
            "shadow_mode": bool(self.params.get("shadow_mode", False)),
            "total_predictions": self._total_predictions,
            "recent_reinforcements": [],
            **state,
        }

    def get_shadow_stats(self) -> Dict[str, Any]:
        """Return telemetry and recent predictions for API inspection."""
        return {
            "strategy": self.name,
            "enabled": self.enabled,
            "shadow_mode": bool(self.params.get("shadow_mode", False)),
            "model_architecture": "16 -> 64 (LayerNorm+LeakyReLU) -> 32 (LayerNorm+LeakyReLU) -> DualHead(3-Class + Return)",
            "train_steps": self.model.train_steps,
            "last_loss": self.model.last_loss,
            "trained_pairs": sorted(list(self._trained_pairs)),
            "total_predictions": self._total_predictions,
            "recent_predictions": list(reversed(self._prediction_history[-50:])),
            "recent_reinforcements": list(reversed(self._learning_history[-20:])),
        }
