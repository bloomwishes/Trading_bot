"""
AutoTrader Pro - Deep Neural Network Strategy (Shadow Mode)
============================================================
Integrates the custom multi-layer DeepTradingNN into the strategy pipeline.

KEY SAFETY DESIGN — SHADOW MODE:
  By default, ``shadow_mode`` is set to ``True``.
  In Shadow Mode:
    1. The strategy receives live/paper market candles on every engine cycle.
    2. It extracts the 16-feature technical state vector and performs forward
       inference through the neural network (and optional online training).
    3. It generates a ``StrategySignal`` tagged with ``shadow_mode=True`` in
       its metadata, complete with class probabilities (HOLD / BUY / SELL)
       and expected return percentage.
    4. The TradingEngine persists the signal to the ``signals`` database table
       and logs the shadow prediction, **without executing any paper or live
       order** and without touching existing risk exposure or balances.
"""

from typing import Optional, Dict, Any, List
import numpy as np
import pandas as pd

from backend.engine.strategy_base import StrategyBase, StrategySignal
from backend.engine.neural_net import (
    DeepTradingNN,
    extract_features_matrix,
    build_training_dataset,
    CLASS_LABELS,
)
from backend.utils.logger import bot_logger
from backend.utils.helpers import timestamp_now


class NeuralNetworkStrategy(StrategyBase):
    """
    Deep Neural Network Strategy operating in Shadow Mode by default.

    Default Parameters:
        shadow_mode (bool): If True, signals are logged & persisted to DB only;
                            no paper or live trades are executed (default True).
        min_confidence (float): Minimum class probability required to emit a
                                BUY/SELL signal (default 0.55).
        horizon_bars (int): Lookahead candle horizon for self-supervised training
                            labels (default 3).
        return_threshold_pct (float): Minimum % move to classify a training
                                      sample as BUY/SELL (default 0.6%).
        learning_rate (float): Adam optimizer learning rate (default 0.005).
        train_epochs (int): Number of training epochs per calibration run (default 25).
        auto_train (bool): Automatically calibrate network weights on historical
                           candles when first analyzing data (default True).
    """

    DEFAULT_PARAMS = {
        "shadow_mode": True,
        "min_confidence": 0.55,
        "horizon_bars": 3,
        "return_threshold_pct": 0.6,
        "learning_rate": 0.005,
        "train_epochs": 25,
        "auto_train": True,
    }

    def __init__(self, params: Optional[dict] = None, seed: int = 42):
        merged = {**self.DEFAULT_PARAMS, **(params or {})}
        # Enforce shadow_mode=True unless explicitly overridden
        merged["shadow_mode"] = bool(merged.get("shadow_mode", True))
        super().__init__(name="Neural_Network", default_params=merged)

        self.model = DeepTradingNN(seed=seed)
        self._shadow_history: List[Dict[str, Any]] = []
        self._total_predictions: int = 0
        self._trained_pairs: set = set()

    def train_on_candles(self, df: pd.DataFrame, pair: str = "GENERIC") -> Dict[str, Any]:
        """
        Train / calibrate the neural network on historical OHLCV candles.

        Args:
            df: DataFrame with [open, high, low, close, volume].
            pair: Trading pair identifier for logging.

        Returns:
            Dictionary of training metrics (epochs, samples, loss, accuracy).
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

        metrics = self.model.fit(
            X, y_class, y_ret, epochs=epochs, lr=lr
        )
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

    def analyze(self, df: pd.DataFrame, pair: str) -> Optional[StrategySignal]:
        """
        Run neural network inference on the latest candle data.

        In Shadow Mode (default), any generated BUY/SELL signal carries
        ``metadata['shadow_mode'] = True`` so the TradingEngine records and
        monitors the prediction without placing any orders.
        """
        if df is None or len(df) < 55:
            return None

        try:
            # Auto-calibrate on first encounter with historical candles
            if (
                self.params.get("auto_train", True)
                and self.model.train_steps == 0
                and len(df) >= 60
            ):
                self.train_on_candles(df, pair=pair)

            features, _ = extract_features_matrix(df)
            if len(features) == 0:
                return None
            latest_x = features[-1]

            pred = self.model.predict_single(latest_x)
            action = pred["action"]
            confidence = float(pred["confidence"])
            expected_ret = float(pred["expected_return_pct"])
            probs = pred["probabilities"]

            is_shadow = bool(self.params.get("shadow_mode", True))
            min_conf = float(self.params.get("min_confidence", 0.55))

            current_price = float(df["close"].iloc[-1])

            prediction_record = {
                "timestamp": timestamp_now(),
                "pair": pair,
                "price": current_price,
                "action": action,
                "confidence": round(confidence, 4),
                "expected_return_pct": round(expected_ret, 4),
                "probabilities": {k: round(v, 4) for k, v in probs.items()},
                "shadow_mode": is_shadow,
                "triggered_signal": (action != "HOLD" and confidence >= min_conf),
            }
            self._total_predictions += 1
            self._shadow_history.append(prediction_record)
            if len(self._shadow_history) > 200:
                self._shadow_history = self._shadow_history[-200:]

            bot_logger.debug(
                f"[NeuralNet][{'SHADOW' if is_shadow else 'ACTIVE'}] {pair} @ ₹{current_price:,.2f} -> "
                f"{action} (conf={confidence:.2%}, exp_ret={expected_ret:+.2f}%)"
            )

            if action in ("BUY", "SELL") and confidence >= min_conf:
                mode_tag = "[SHADOW MODE] " if is_shadow else ""
                reason = (
                    f"{mode_tag}DeepNN {action} prediction on {pair} "
                    f"(confidence={confidence:.1%}, expected_return={expected_ret:+.2f}%, "
                    f"P(BUY)={probs['BUY']:.2f}, P(SELL)={probs['SELL']:.2f}, P(HOLD)={probs['HOLD']:.2f})"
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

    def get_shadow_stats(self) -> Dict[str, Any]:
        """Return telemetry and recent shadow predictions for API inspection."""
        return {
            "strategy": self.name,
            "enabled": self.enabled,
            "shadow_mode": bool(self.params.get("shadow_mode", True)),
            "model_architecture": "16 -> 64 (LayerNorm+LeakyReLU) -> 32 (LayerNorm+LeakyReLU) -> DualHead(3-Class + Return)",
            "train_steps": self.model.train_steps,
            "last_loss": self.model.last_loss,
            "trained_pairs": sorted(list(self._trained_pairs)),
            "total_predictions": self._total_predictions,
            "recent_predictions": list(reversed(self._shadow_history[-50:])),
        }
