"""
AutoTrader Pro - Deep Neural Network Engine (NumPy)
====================================================
A self-contained, zero-external-DL-dependency Multi-Layer Perceptron (MLP)
with Layer Normalization, LeakyReLU activations, dual heads (3-class
classification [HOLD, BUY, SELL] + expected return regression), and
vectorized Adam optimizer with L2 weight decay.

Designed for low-latency candle inference and walk-forward self-supervised
learning on OHLCV market data in Shadow Mode.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

import numpy as np
import pandas as pd

from backend.engine.indicators import (
    calculate_atr,
    calculate_bollinger_bands,
    calculate_ema,
    calculate_macd,
    calculate_rsi,
    calculate_stoch_rsi,
    calculate_volume_sma,
)
from backend.utils.logger import bot_logger

FEATURE_NAMES: List[str] = [
    "rsi_norm",
    "stoch_k_norm",
    "stoch_d_norm",
    "stoch_diff",
    "ema9_dist_pct",
    "ema21_dist_pct",
    "ema50_dist_pct",
    "trend_alignment",
    "macd_norm",
    "macd_hist_norm",
    "bb_percent_b",
    "bb_bandwidth",
    "atr_pct",
    "rel_volume",
    "bar_return_pct",
    "mom_3bar_pct",
]

NUM_FEATURES: int = len(FEATURE_NAMES)
CLASS_LABELS: List[str] = ["HOLD", "BUY", "SELL"]


def extract_features_matrix(df: pd.DataFrame) -> Tuple[np.ndarray, pd.Index]:
    """
    Compute the 16-feature matrix for all valid rows in an OHLCV DataFrame.

    Args:
        df: DataFrame with columns [open, high, low, close, volume].

    Returns:
        Tuple of (features_array of shape [N_valid, 16], valid_index).
    """
    if df is None or len(df) < 55:
        return np.empty((0, NUM_FEATURES), dtype=np.float64), pd.Index([])

    close = df["close"].astype(float)
    open_ = df["open"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    volume = df["volume"].astype(float)

    rsi = calculate_rsi(df, period=14)
    stoch_k, stoch_d = calculate_stoch_rsi(df, period=14, smooth_k=3, smooth_d=3)
    ema9 = calculate_ema(df, period=9)
    ema21 = calculate_ema(df, period=21)
    ema50 = calculate_ema(df, period=50)
    macd_line, macd_sig, macd_hist = calculate_macd(df, fast=12, slow=26, signal=9)
    bb_upper, bb_mid, bb_lower, bb_bw = calculate_bollinger_bands(df, period=20, std_dev=2)
    atr = calculate_atr(df, period=14)
    vol_sma = calculate_volume_sma(df, period=20)

    safe_close = close.replace(0, np.nan)
    bb_range = (bb_upper - bb_lower).replace(0, np.nan)
    safe_vol_sma = vol_sma.replace(0, np.nan)
    safe_open = open_.replace(0, np.nan)

    # 1-4: Momentum oscillators
    f_rsi = (rsi - 50.0) / 50.0
    f_stoch_k = (stoch_k - 50.0) / 50.0
    f_stoch_d = (stoch_d - 50.0) / 50.0
    f_stoch_diff = (stoch_k - stoch_d) / 100.0

    # 5-8: Moving average structure
    f_ema9 = (close - ema9) / safe_close * 100.0
    f_ema21 = (close - ema21) / safe_close * 100.0
    f_ema50 = (close - ema50) / safe_close * 100.0
    f_trend = np.where(
        (ema9 > ema21) & (ema21 > ema50),
        1.0,
        np.where((ema9 < ema21) & (ema21 < ema50), -1.0, 0.0),
    )

    # 9-10: MACD normalized
    f_macd = macd_line / safe_close * 100.0
    f_macd_hist = macd_hist / safe_close * 100.0

    # 11-12: Bollinger position & bandwidth
    f_bb_pos = ((close - bb_lower) / bb_range) - 0.5
    f_bb_bw = bb_bw / 10.0

    # 13-14: Volatility & Volume
    f_atr_pct = atr / safe_close * 100.0
    f_rel_vol = ((volume / safe_vol_sma) - 1.0).clip(-1.0, 5.0)

    # 15-16: Price returns
    f_bar_ret = (close - open_) / safe_open * 100.0
    f_mom3 = close.pct_change(3) * 100.0

    feat_df = pd.DataFrame(
        {
            "rsi_norm": f_rsi,
            "stoch_k_norm": f_stoch_k,
            "stoch_d_norm": f_stoch_d,
            "stoch_diff": f_stoch_diff,
            "ema9_dist_pct": f_ema9,
            "ema21_dist_pct": f_ema21,
            "ema50_dist_pct": f_ema50,
            "trend_alignment": pd.Series(f_trend, index=df.index),
            "macd_norm": f_macd,
            "macd_hist_norm": f_macd_hist,
            "bb_percent_b": f_bb_pos,
            "bb_bandwidth": f_bb_bw,
            "atr_pct": f_atr_pct,
            "rel_volume": f_rel_vol,
            "bar_return_pct": f_bar_ret,
            "mom_3bar_pct": f_mom3,
        },
        index=df.index,
    )

    feat_df = feat_df.replace([np.inf, -np.inf], np.nan).dropna()
    if feat_df.empty:
        return np.empty((0, NUM_FEATURES), dtype=np.float64), pd.Index([])

    # Clip extreme outliers for numerical stability
    matrix = np.clip(feat_df.values.astype(np.float64), -10.0, 10.0)
    return matrix, feat_df.index


def build_training_dataset(
    df: pd.DataFrame,
    horizon_bars: int = 3,
    return_threshold_pct: float = 0.8,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Create supervised training data (X, y_class, y_return) from historical OHLCV candles.

    Labels:
        0 = HOLD (forward return within [-threshold, +threshold])
        1 = BUY  (forward return >= +threshold%)
        2 = SELL (forward return <= -threshold%)
    """
    X_all, valid_idx = extract_features_matrix(df)
    if len(X_all) <= horizon_bars + 2:
        return (
            np.empty((0, NUM_FEATURES)),
            np.empty((0,), dtype=np.int64),
            np.empty((0,), dtype=np.float64),
        )

    close_series = df.loc[valid_idx, "close"].astype(float).values
    fwd_returns = (
        (close_series[horizon_bars:] - close_series[:-horizon_bars])
        / np.maximum(close_series[:-horizon_bars], 1e-8)
        * 100.0
    )

    X = X_all[:-horizon_bars]
    y_ret = np.clip(fwd_returns, -15.0, 15.0)
    y_cls = np.zeros(len(y_ret), dtype=np.int64)
    y_cls[y_ret >= return_threshold_pct] = 1   # BUY
    y_cls[y_ret <= -return_threshold_pct] = 2  # SELL

    return X, y_cls, y_ret


class DeepTradingNN:
    """
    Multi-Layer Perceptron (16 -> 64 -> 32 -> [3 classes + 1 return head])
    with LayerNorm, LeakyReLU, and Adam optimizer.
    """

    def __init__(
        self,
        input_dim: int = NUM_FEATURES,
        hidden1: int = 64,
        hidden2: int = 32,
        num_classes: int = 3,
        seed: int = 42,
    ):
        self.input_dim = input_dim
        self.hidden1 = hidden1
        self.hidden2 = hidden2
        self.num_classes = num_classes
        self.rng = np.random.default_rng(seed)

        # He Initialization
        self.W1 = self.rng.normal(0, np.sqrt(2.0 / input_dim), (input_dim, hidden1))
        self.b1 = np.zeros((1, hidden1))
        self.gamma1 = np.ones((1, hidden1))
        self.beta1 = np.zeros((1, hidden1))

        self.W2 = self.rng.normal(0, np.sqrt(2.0 / hidden1), (hidden1, hidden2))
        self.b2 = np.zeros((1, hidden2))
        self.gamma2 = np.ones((1, hidden2))
        self.beta2 = np.zeros((1, hidden2))

        # Classification head (HOLD, BUY, SELL)
        self.W_cls = self.rng.normal(0, np.sqrt(1.0 / hidden2), (hidden2, num_classes))
        self.b_cls = np.zeros((1, num_classes))

        # Expected return regression head
        self.W_reg = self.rng.normal(0, np.sqrt(1.0 / hidden2), (hidden2, 1))
        self.b_reg = np.zeros((1, 1))

        # Feature standardization statistics
        self.feat_mean = np.zeros((1, input_dim))
        self.feat_std = np.ones((1, input_dim))
        self.is_trained: bool = False
        self.train_steps: int = 0
        self.last_loss: float = 0.0

        # Adam state
        self._adam_m: Dict[str, np.ndarray] = {}
        self._adam_v: Dict[str, np.ndarray] = {}
        self._adam_t: int = 0

    @staticmethod
    def _leaky_relu(x: np.ndarray, alpha: float = 0.01) -> np.ndarray:
        return np.where(x > 0, x, alpha * x)

    @staticmethod
    def _leaky_relu_grad(x: np.ndarray, alpha: float = 0.01) -> np.ndarray:
        return np.where(x > 0, 1.0, alpha)

    @staticmethod
    def _layer_norm(
        x: np.ndarray, gamma: np.ndarray, beta: np.ndarray, eps: float = 1e-5
    ) -> Tuple[np.ndarray, Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]]:
        mean = np.mean(x, axis=-1, keepdims=True)
        var = np.var(x, axis=-1, keepdims=True)
        std_inv = 1.0 / np.sqrt(var + eps)
        x_hat = (x - mean) * std_inv
        out = gamma * x_hat + beta
        return out, (x_hat, std_inv, gamma, x - mean)

    @staticmethod
    def _layer_norm_backward(
        dout: np.ndarray, cache: Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        x_hat, std_inv, gamma, x_mu = cache
        D = dout.shape[-1]
        dgamma = np.sum(dout * x_hat, axis=0, keepdims=True)
        dbeta = np.sum(dout, axis=0, keepdims=True)
        dx_hat = dout * gamma
        dx = (1.0 / D) * std_inv * (
            D * dx_hat
            - np.sum(dx_hat, axis=-1, keepdims=True)
            - x_hat * np.sum(dx_hat * x_hat, axis=-1, keepdims=True)
        )
        return dx, dgamma, dbeta

    @staticmethod
    def _softmax(logits: np.ndarray) -> np.ndarray:
        shifted = logits - np.max(logits, axis=-1, keepdims=True)
        exp_scores = np.exp(shifted)
        return exp_scores / np.sum(exp_scores, axis=-1, keepdims=True)

    def _normalize_input(self, X: np.ndarray) -> np.ndarray:
        return np.clip((X - self.feat_mean) / np.maximum(self.feat_std, 1e-6), -5.0, 5.0)

    def forward(
        self, X: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray, Dict[str, Any]]:
        """
        Forward pass through the network.

        Returns:
            Tuple of (class_probs [N, 3], expected_return [N, 1], cache).
        """
        X_norm = self._normalize_input(X)

        # Layer 1
        z1 = X_norm @ self.W1 + self.b1
        ln1, ln1_cache = self._layer_norm(z1, self.gamma1, self.beta1)
        a1 = self._leaky_relu(ln1)

        # Layer 2
        z2 = a1 @ self.W2 + self.b2
        ln2, ln2_cache = self._layer_norm(z2, self.gamma2, self.beta2)
        a2 = self._leaky_relu(ln2)

        # Heads
        logits = a2 @ self.W_cls + self.b_cls
        probs = self._softmax(logits)
        pred_return = a2 @ self.W_reg + self.b_reg

        cache = {
            "X_norm": X_norm,
            "z1": z1,
            "ln1": ln1,
            "ln1_cache": ln1_cache,
            "a1": a1,
            "z2": z2,
            "ln2": ln2,
            "ln2_cache": ln2_cache,
            "a2": a2,
            "probs": probs,
            "pred_return": pred_return,
        }
        return probs, pred_return, cache

    def predict_single(self, feature_row: np.ndarray) -> Dict[str, Any]:
        """Run inference on a single 1D or 2D feature vector."""
        x = feature_row.reshape(1, -1)
        probs, pred_ret, _ = self.forward(x)
        p = probs[0]
        cls_idx = int(np.argmax(p))
        label = CLASS_LABELS[cls_idx]
        confidence = float(p[cls_idx])
        expected_return = float(pred_ret[0, 0])

        return {
            "action": label,
            "confidence": round(confidence, 4),
            "expected_return_pct": round(expected_return, 4),
            "probabilities": {
                "HOLD": round(float(p[0]), 4),
                "BUY": round(float(p[1]), 4),
                "SELL": round(float(p[2]), 4),
            },
        }

    def fit(
        self,
        X: np.ndarray,
        y_cls: np.ndarray,
        y_ret: np.ndarray,
        epochs: int = 25,
        lr: float = 0.005,
        weight_decay: float = 1e-4,
    ) -> Dict[str, float]:
        """
        Train the neural network on (X, y_cls, y_ret) using Adam.
        """
        N = len(X)
        if N < 8:
            return {"loss": 0.0, "accuracy": 0.0, "samples": N}

        # Update feature scaling statistics
        self.feat_mean = np.mean(X, axis=0, keepdims=True)
        self.feat_std = np.std(X, axis=0, keepdims=True) + 1e-5

        # Class weights to counter class imbalance
        counts = np.bincount(y_cls, minlength=self.num_classes).astype(np.float64)
        total = np.sum(counts)
        class_weights = total / (self.num_classes * np.maximum(counts, 1.0))
        sample_weights = class_weights[y_cls]

        final_loss = 0.0
        accuracy = 0.0

        for _ in range(epochs):
            probs, pred_ret, cache = self.forward(X)

            # Cross-entropy loss
            clipped_probs = np.clip(probs[np.arange(N), y_cls], 1e-9, 1.0)
            ce_loss = -np.mean(sample_weights * np.log(clipped_probs))

            # Regression MSE loss (scaled)
            ret_target = y_ret.reshape(-1, 1)
            reg_diff = pred_ret - ret_target
            reg_loss = 0.1 * np.mean(reg_diff ** 2)

            final_loss = float(ce_loss + reg_loss)
            preds = np.argmax(probs, axis=1)
            accuracy = float(np.mean(preds == y_cls))

            # Gradients for heads
            dlogits = probs.copy()
            dlogits[np.arange(N), y_cls] -= 1.0
            dlogits *= (sample_weights[:, None] / N)

            dpred_ret = 0.2 * reg_diff / N

            a2 = cache["a2"]
            dW_cls = a2.T @ dlogits + weight_decay * self.W_cls
            db_cls = np.sum(dlogits, axis=0, keepdims=True)

            dW_reg = a2.T @ dpred_ret + weight_decay * self.W_reg
            db_reg = np.sum(dpred_ret, axis=0, keepdims=True)

            # Backprop into Layer 2
            da2 = dlogits @ self.W_cls.T + dpred_ret @ self.W_reg.T
            dln2 = da2 * self._leaky_relu_grad(cache["ln2"])
            dz2, dgamma2, dbeta2 = self._layer_norm_backward(dln2, cache["ln2_cache"])

            a1 = cache["a1"]
            dW2 = a1.T @ dz2 + weight_decay * self.W2
            db2 = np.sum(dz2, axis=0, keepdims=True)

            # Backprop into Layer 1
            da1 = dz2 @ self.W2.T
            dln1 = da1 * self._leaky_relu_grad(cache["ln1"])
            dz1, dgamma1, dbeta1 = self._layer_norm_backward(dln1, cache["ln1_cache"])

            X_norm = cache["X_norm"]
            dW1 = X_norm.T @ dz1 + weight_decay * self.W1
            db1 = np.sum(dz1, axis=0, keepdims=True)

            grads = {
                "W1": dW1,
                "b1": db1,
                "gamma1": dgamma1,
                "beta1": dbeta1,
                "W2": dW2,
                "b2": db2,
                "gamma2": dgamma2,
                "beta2": dbeta2,
                "W_cls": dW_cls,
                "b_cls": db_cls,
                "W_reg": dW_reg,
                "b_reg": db_reg,
            }
            self._adam_step(grads, lr=lr)

        self.is_trained = True
        self.train_steps += epochs
        self.last_loss = round(final_loss, 5)

        return {
            "loss": round(final_loss, 5),
            "accuracy": round(accuracy, 4),
            "samples": N,
            "train_steps": self.train_steps,
        }

    def _adam_step(
        self,
        grads: Dict[str, np.ndarray],
        lr: float = 0.005,
        beta1: float = 0.9,
        beta2: float = 0.999,
        eps: float = 1e-8,
    ) -> None:
        self._adam_t += 1
        for name, grad in grads.items():
            grad = np.clip(grad, -5.0, 5.0)
            param = getattr(self, name)
            if name not in self._adam_m:
                self._adam_m[name] = np.zeros_like(param)
                self._adam_v[name] = np.zeros_like(param)

            self._adam_m[name] = beta1 * self._adam_m[name] + (1.0 - beta1) * grad
            self._adam_v[name] = beta2 * self._adam_v[name] + (1.0 - beta2) * (grad ** 2)

            m_hat = self._adam_m[name] / (1.0 - beta1 ** self._adam_t)
            v_hat = self._adam_v[name] / (1.0 - beta2 ** self._adam_t)

            setattr(self, name, param - lr * m_hat / (np.sqrt(v_hat) + eps))

    def save_weights(self, filepath: str | Path) -> bool:
        """Persist model weights and normalization stats to JSON."""
        try:
            payload = {
                "W1": self.W1.tolist(),
                "b1": self.b1.tolist(),
                "gamma1": self.gamma1.tolist(),
                "beta1": self.beta1.tolist(),
                "W2": self.W2.tolist(),
                "b2": self.b2.tolist(),
                "gamma2": self.gamma2.tolist(),
                "beta2": self.beta2.tolist(),
                "W_cls": self.W_cls.tolist(),
                "b_cls": self.b_cls.tolist(),
                "W_reg": self.W_reg.tolist(),
                "b_reg": self.b_reg.tolist(),
                "feat_mean": self.feat_mean.tolist(),
                "feat_std": self.feat_std.tolist(),
                "is_trained": self.is_trained,
                "train_steps": self.train_steps,
                "last_loss": self.last_loss,
            }
            Path(filepath).write_text(json.dumps(payload), encoding="utf-8")
            return True
        except Exception as exc:
            bot_logger.error(f"[DeepTradingNN] Failed to save weights: {exc}")
            return False

    def load_weights(self, filepath: str | Path) -> bool:
        """Load model weights and normalization stats from JSON."""
        path = Path(filepath)
        if not path.exists():
            return False
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            self.W1 = np.array(data["W1"], dtype=np.float64)
            self.b1 = np.array(data["b1"], dtype=np.float64)
            self.gamma1 = np.array(data["gamma1"], dtype=np.float64)
            self.beta1 = np.array(data["beta1"], dtype=np.float64)
            self.W2 = np.array(data["W2"], dtype=np.float64)
            self.b2 = np.array(data["b2"], dtype=np.float64)
            self.gamma2 = np.array(data["gamma2"], dtype=np.float64)
            self.beta2 = np.array(data["beta2"], dtype=np.float64)
            self.W_cls = np.array(data["W_cls"], dtype=np.float64)
            self.b_cls = np.array(data["b_cls"], dtype=np.float64)
            self.W_reg = np.array(data["W_reg"], dtype=np.float64)
            self.b_reg = np.array(data["b_reg"], dtype=np.float64)
            self.feat_mean = np.array(data["feat_mean"], dtype=np.float64)
            self.feat_std = np.array(data["feat_std"], dtype=np.float64)
            self.is_trained = bool(data.get("is_trained", True))
            self.train_steps = int(data.get("train_steps", 0))
            self.last_loss = float(data.get("last_loss", 0.0))
            return True
        except Exception as exc:
            bot_logger.error(f"[DeepTradingNN] Failed to load weights: {exc}")
            return False
