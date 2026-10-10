"""
AutoTrader Pro - CoinDCX 24-Month BTC/INR Historical Data Training Script
========================================================================
CLI / Standalone utility to:
  1. Download 24 months of historical BTC/INR data directly from CoinDCX.
  2. Extract the identical 16 technical features (Momentum, Trend, MACD, BB, ATR, Volume).
  3. Create explicit training labels:
       - 0 = HOLD (Forward return within [-threshold, +threshold])
       - 1 = BUY  (Forward return >= +threshold%)
       - 2 = SELL (Forward return <= -threshold%)
  4. Train the DeepTradingNN architecture (16 -> 64 -> 32 -> DualHead) on the historical dataset.
  5. Save weights to backend/engine/nn_weights_experimental.json (WITHOUT touching live model weights or thresholds).
"""

import argparse
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import requests

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.engine.neural_net import (
    DeepTradingNN,
    extract_features_matrix,
    build_training_dataset,
    FEATURE_NAMES,
)
from backend.engine.neural_net_strategy import WEIGHTS_PATH, EXPERIMENTAL_WEIGHTS_PATH
from backend.utils.logger import bot_logger


def download_coindcx_candles(days: int = 730) -> pd.DataFrame:
    """Download daily candles for BTC/INR directly from CoinDCX public API."""
    url = "https://public.coindcx.com/market_data/candles"
    params = {
        "pair": "I-BTC_INR",
        "interval": "1d",
        "limit": str(min(1000, max(60, days))),
    }
    print(f"[*] Fetching {days} daily candles for I-BTC_INR from CoinDCX ({url})...")
    resp = requests.get(url, params=params, timeout=20)
    resp.raise_for_status()
    raw = resp.json()

    if not isinstance(raw, list) or len(raw) == 0:
        raise ValueError("CoinDCX API returned empty candle response")

    df = pd.DataFrame(raw).rename(columns={"time": "timestamp"})
    df = df[["timestamp", "open", "high", "low", "close", "volume"]]
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    # Sort chronological (oldest to newest)
    df = df.sort_values("timestamp").reset_index(drop=True)
    start_dt = pd.to_datetime(df["timestamp"].iloc[0], unit="ms")
    end_dt = pd.to_datetime(df["timestamp"].iloc[-1], unit="ms")
    print(f"[+] Downloaded {len(df)} daily candles: {start_dt} to {end_dt} (~{(end_dt - start_dt).days / 30.4:.1f} months)")
    return df


def run_experimental_training(
    days: int = 730,
    horizon_bars: int = 5,
    return_threshold_pct: float = 2.0,
    epochs: int = 50,
    learning_rate: float = 0.005,
    save_path: Path = EXPERIMENTAL_WEIGHTS_PATH,
) -> dict:
    """Execute training pipeline and save to experimental weights path."""
    print("=================================================================")
    print("AutoTrader Pro - Experimental Neural Network Training Pipeline")
    print("=================================================================")

    # 1. Download CoinDCX data
    df = download_coindcx_candles(days=days)

    # 2. Extract 16 features and build labeled dataset
    print(f"[*] Computing 16 technical features with horizon={horizon_bars} bars and threshold={return_threshold_pct}%...")
    X, y_cls, y_ret = build_training_dataset(
        df, horizon_bars=horizon_bars, return_threshold_pct=return_threshold_pct
    )
    print(f"[+] Features shape: {X.shape} (16 indicators per candle)")
    print(f"[+] Sample counts: {len(X)} valid training windows")

    # Label distribution breakdown
    hold_count = int(np.sum(y_cls == 0))
    buy_count = int(np.sum(y_cls == 1))
    sell_count = int(np.sum(y_cls == 2))
    print("[+] Explicit Training Label Distribution:")
    print(f"    - Class 0 (HOLD): {hold_count} ({hold_count / len(y_cls):.1%})")
    print(f"    - Class 1 (BUY) : {buy_count} ({buy_count / len(y_cls):.1%})")
    print(f"    - Class 2 (SELL): {sell_count} ({sell_count / len(y_cls):.1%})")

    # 3. Verify Live Weights are Untouched
    live_weights_exist = WEIGHTS_PATH.exists()
    live_stat_before = WEIGHTS_PATH.stat().st_mtime if live_weights_exist else None

    # 4. Instantiate Experimental Model Clone
    print(f"[*] Training DeepTradingNN (16 -> 64 -> 32 -> DualHead) for {epochs} epochs (lr={learning_rate})...")
    exp_model = DeepTradingNN(seed=42)
    metrics = exp_model.fit(X, y_cls, y_ret, epochs=epochs, lr=learning_rate)
    print(f"[+] Training Complete! Final Loss: {metrics['loss']:.4f}, Accuracy: {metrics['accuracy'] * 100:.2f}%")

    # 5. Save ONLY to experimental path
    save_path.parent.mkdir(parents=True, exist_ok=True)
    exp_model.save_weights(save_path)
    print(f"[+] Successfully saved experimental weights to: {save_path.resolve()}")

    # 6. Safety Verification
    if live_weights_exist:
        live_stat_after = WEIGHTS_PATH.stat().st_mtime
        assert live_stat_before == live_stat_after, "CRITICAL ERROR: Live weights file was touched!"
        print(f"[+] SAFETY VERIFIED: Live model weights ({WEIGHTS_PATH.name}) were NOT modified.")

    summary = {
        "status": "success",
        "data_source": "CoinDCX Public API (I-BTC_INR)",
        "candles_count": len(df),
        "samples_count": len(X),
        "horizon_bars": horizon_bars,
        "return_threshold_pct": return_threshold_pct,
        "label_distribution": {
            "HOLD": hold_count,
            "BUY": buy_count,
            "SELL": sell_count,
        },
        "epochs": epochs,
        "loss": metrics["loss"],
        "accuracy": metrics["accuracy"],
        "experimental_weights_file": str(save_path.name),
        "live_weights_touched": False,
    }
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train experimental neural network on CoinDCX BTC/INR data")
    parser.add_argument("--days", type=int, default=730, help="Days of history to download (730 = 24 months)")
    parser.add_argument("--epochs", type=int, default=50, help="Training epochs")
    parser.add_argument("--lr", type=float, default=0.005, help="Learning rate")
    parser.add_argument("--horizon", type=int, default=5, help="Forward return horizon bars")
    parser.add_argument("--threshold", type=float, default=2.0, help="Return threshold % for BUY/SELL labels")

    args = parser.parse_args()
    res = run_experimental_training(
        days=args.days,
        horizon_bars=args.horizon,
        return_threshold_pct=args.threshold,
        epochs=args.epochs,
        learning_rate=args.lr,
    )
    print("\nSummary Results:")
    print(json.dumps(res, indent=2))
