"""
Systematic Neural Network Architecture Optimization & Chronological Evaluation
================================================================================
Evaluates multiple neuron configurations on BTC/INR:
- Slices data strictly chronologically (Train: past years, Val: most recent out-of-sample data)
- Compares Training vs. Validation Loss, Accuracy, F1-Score, Expected Return MSE, and Overfitting Gap
- Tests simulated walk-forward trading performance (Win Rate, Total Return %, Max Drawdown)
- Identifies the Pareto-optimal best-performing architecture and updates production weights
- Generates an in-depth analytical evaluation report
"""

import sys
import json
import time
from pathlib import Path
from typing import Dict, List, Tuple, Any

import numpy as np
import pandas as pd
import requests

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.engine.neural_net import (
    DeepTradingNN,
    build_training_dataset,
    NUM_FEATURES,
    CLASS_LABELS,
)
from backend.engine.neural_net_strategy import WEIGHTS_PATH
from backend.utils.logger import bot_logger


def fetch_btc_inr_data() -> pd.DataFrame:
    """Fetch 10 years of historical daily candles for BTC/INR from Yahoo Finance."""
    print("[*] Downloading 10 years of historical BTC/INR daily candles...")
    url = "https://query1.finance.yahoo.com/v8/finance/chart/BTC-INR?interval=1d&range=10y"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    resp = requests.get(url, headers=headers, timeout=25)
    resp.raise_for_status()
    res = resp.json()["chart"]["result"][0]
    quote = res["indicators"]["quote"][0]
    df = pd.DataFrame({
        "timestamp": [int(t) * 1000 for t in res["timestamp"]],
        "open": quote["open"],
        "high": quote["high"],
        "low": quote["low"],
        "close": quote["close"],
        "volume": quote["volume"],
    }).dropna()
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    df = df[df["close"] > 0].sort_values("timestamp").reset_index(drop=True)
    print(f"[+] Downloaded {len(df)} daily candles (from {pd.to_datetime(df['timestamp'].iloc[0], unit='ms').strftime('%Y-%m-%d')} to {pd.to_datetime(df['timestamp'].iloc[-1], unit='ms').strftime('%Y-%m-%d')})")
    return df


def calculate_metrics(y_true_cls: np.ndarray, y_pred_cls: np.ndarray, y_true_ret: np.ndarray, y_pred_ret: np.ndarray) -> Dict[str, float]:
    """Calculate multi-class classification and regression evaluation metrics."""
    acc = float(np.mean(y_true_cls == y_pred_cls))
    
    # Macro F1 calculation
    f1_list = []
    for c in range(3):
        tp = np.sum((y_pred_cls == c) & (y_true_cls == c))
        fp = np.sum((y_pred_cls == c) & (y_true_cls != c))
        fn = np.sum((y_pred_cls != c) & (y_true_cls == c))
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2 * prec * rec / (prec + rec)) if (prec + rec) > 0 else 0.0
        f1_list.append(f1)
    macro_f1 = float(np.mean(f1_list))
    
    # Return head MSE
    mse = float(np.mean((y_true_ret - y_pred_ret.flatten()) ** 2))
    
    # Directional correlation (directional accuracy of expected return)
    dir_match = float(np.mean(np.sign(y_true_ret) == np.sign(y_pred_ret.flatten())))

    return {
        "accuracy": acc,
        "macro_f1": macro_f1,
        "return_mse": mse,
        "directional_accuracy": dir_match,
    }


def simulate_trading(y_pred_probs: np.ndarray, y_pred_ret: np.ndarray, fwd_actual_returns: np.ndarray, min_conf: float = 0.50) -> Dict[str, float]:
    """
    Simulate trading on chronological evaluation slice:
    - BUY when p(BUY) > min_conf and pred_ret > 0.5%
    - SELL when p(SELL) > min_conf and pred_ret < -0.5%
    - Else HOLD
    """
    trades_pnl = []
    equity = 1.0
    equity_curve = [1.0]

    for i in range(len(y_pred_probs)):
        p_hold, p_buy, p_sell = y_pred_probs[i]
        pred_r = y_pred_ret[i, 0]
        actual_r = fwd_actual_returns[i]

        action = 0
        if p_buy >= min_conf and pred_r > 0.4:
            action = 1
        elif p_sell >= min_conf and pred_r < -0.4:
            action = 2

        if action == 1:
            pnl = actual_r
            trades_pnl.append(pnl)
            equity *= (1.0 + pnl / 100.0)
        elif action == 2:
            pnl = -actual_r
            trades_pnl.append(pnl)
            equity *= (1.0 + pnl / 100.0)

        equity_curve.append(equity)

    trade_count = len(trades_pnl)
    win_count = sum(1 for p in trades_pnl if p > 0)
    win_rate = (win_count / trade_count * 100.0) if trade_count > 0 else 0.0
    total_return_pct = (equity - 1.0) * 100.0

    # Max drawdown
    peak = equity_curve[0]
    max_dd = 0.0
    for val in equity_curve:
        if val > peak:
            peak = val
        dd = (peak - val) / peak * 100.0
        if dd > max_dd:
            max_dd = dd

    profit_factor = 0.0
    gross_win = sum(p for p in trades_pnl if p > 0)
    gross_loss = abs(sum(p for p in trades_pnl if p < 0))
    if gross_loss > 0:
        profit_factor = gross_win / gross_loss
    elif gross_win > 0:
        profit_factor = 99.0

    return {
        "trades": trade_count,
        "win_rate": round(win_rate, 2),
        "total_return_pct": round(total_return_pct, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "profit_factor": round(profit_factor, 2),
    }


def evaluate_architecture(
    name: str,
    h1: int,
    h2: int,
    X_train: np.ndarray,
    y_cls_train: np.ndarray,
    y_ret_train: np.ndarray,
    X_val: np.ndarray,
    y_cls_val: np.ndarray,
    y_ret_val: np.ndarray,
    epochs: int = 120,
    lr: float = 0.005,
    seed: int = 42,
) -> Dict[str, Any]:
    """Train architecture and evaluate train vs. val performance."""
    nn = DeepTradingNN(input_dim=NUM_FEATURES, hidden1=h1, hidden2=h2, seed=seed)
    
    start_time = time.time()
    train_res = nn.fit(X_train, y_cls_train, y_ret_train, epochs=epochs, lr=lr)
    elapsed = time.time() - start_time

    # Train predictions
    train_probs, train_ret, _ = nn.forward(X_train)
    train_preds = np.argmax(train_probs, axis=1)
    train_metrics = calculate_metrics(y_cls_train, train_preds, y_ret_train, train_ret)

    # Validation predictions (Strictly Out-of-Sample)
    val_probs, val_ret, _ = nn.forward(X_val)
    val_preds = np.argmax(val_probs, axis=1)
    val_metrics = calculate_metrics(y_cls_val, val_preds, y_ret_val, val_ret)

    # Overfitting assessment
    overfit_gap_acc = (train_metrics["accuracy"] - val_metrics["accuracy"]) * 100.0
    overfit_ratio = train_metrics["accuracy"] / max(val_metrics["accuracy"], 1e-5)

    # Simulated trading performance on validation slice
    trading_sim = simulate_trading(val_probs, val_ret, y_ret_val)

    # Combined composite score:
    # High Val Accuracy + Macro F1 + Simulated Profit Factor - Overfit Penalty
    overfit_penalty = max(0.0, (overfit_gap_acc - 5.0) * 0.5)
    composite_score = (
        val_metrics["accuracy"] * 40.0
        + val_metrics["macro_f1"] * 30.0
        + min(trading_sim["win_rate"], 100.0) * 0.2
        + min(trading_sim["profit_factor"], 5.0) * 5.0
        - overfit_penalty
    )

    return {
        "name": name,
        "h1": h1,
        "h2": h2,
        "parameters": (NUM_FEATURES * h1 + h1) + (h1 * h2 + h2) + (h2 * 3 + 3) + (h2 * 1 + 1),
        "train_loss": train_res["loss"],
        "train_accuracy": round(train_metrics["accuracy"] * 100, 2),
        "train_macro_f1": round(train_metrics["macro_f1"], 4),
        "val_accuracy": round(val_metrics["accuracy"] * 100, 2),
        "val_macro_f1": round(val_metrics["macro_f1"], 4),
        "val_return_mse": round(val_metrics["return_mse"], 4),
        "val_dir_accuracy": round(val_metrics["directional_accuracy"] * 100, 2),
        "overfit_gap_pct": round(overfit_gap_acc, 2),
        "overfit_ratio": round(overfit_ratio, 2),
        "trading": trading_sim,
        "composite_score": round(composite_score, 2),
        "training_time_sec": round(elapsed, 2),
        "_model_instance": nn,
    }


def run_systematic_optimization():
    print("==========================================================================")
    print("AutoTrader Pro - Systematic Neural Network Optimization & Validation Pipeline")
    print("==========================================================================")

    df_daily = fetch_btc_inr_data()
    
    # Multi-horizon dataset generation
    X_m1, y_c1, y_r1 = build_training_dataset(df_daily, horizon_bars=5, return_threshold_pct=2.0)
    X_m2, y_c2, y_r2 = build_training_dataset(df_daily, horizon_bars=3, return_threshold_pct=1.2)
    X_m3, y_c3, y_r3 = build_training_dataset(df_daily, horizon_bars=8, return_threshold_pct=3.5)

    # Stack chronological multi-horizon data maintaining time ordering
    # Chronological split: First 80% for Train, Final 20% for strictly Out-of-Sample Validation
    split_pct = 0.80
    n1 = len(X_m1)
    split_idx_1 = int(n1 * split_pct)

    n2 = len(X_m2)
    split_idx_2 = int(n2 * split_pct)

    n3 = len(X_m3)
    split_idx_3 = int(n3 * split_pct)

    X_train = np.vstack([X_m1[:split_idx_1], X_m2[:split_idx_2], X_m3[:split_idx_3]])
    y_cls_train = np.concatenate([y_c1[:split_idx_1], y_c2[:split_idx_2], y_c3[:split_idx_3]])
    y_ret_train = np.concatenate([y_r1[:split_idx_1], y_r2[:split_idx_2], y_r3[:split_idx_3]])

    # Out-of-sample validation slice (strictly most recent unseen 20% market cycles)
    X_val = np.vstack([X_m1[split_idx_1:], X_m2[split_idx_2:], X_m3[split_idx_3:]])
    y_cls_val = np.concatenate([y_c1[split_idx_1:], y_c2[split_idx_2:], y_c3[split_idx_3:]])
    y_ret_val = np.concatenate([y_r1[split_idx_1:], y_r2[split_idx_2:], y_r3[split_idx_3:]])

    print(f"\n[*] Chronological Data Split:")
    print(f"    - Training Set (In-Sample): {len(X_train)} samples ({split_pct*100:.0f}% historical macro)")
    print(f"    - Validation Set (Out-of-Sample): {len(X_val)} samples ({(1-split_pct)*100:.0f}% recent cycles)")

    # Test candidate neuron sizes spanning compact, current, deep, and wide configurations
    architectures = [
        {"name": "Ultra-Compact (16 -> 32 -> 16)", "h1": 32, "h2": 16},
        {"name": "Compact-Tuned (16 -> 48 -> 24)", "h1": 48, "h2": 24},
        {"name": "Current Baseline (16 -> 64 -> 32)", "h1": 64, "h2": 32},
        {"name": "Wide First-Layer (16 -> 96 -> 32)", "h1": 96, "h2": 32},
        {"name": "Balanced Expansion (16 -> 96 -> 48)", "h1": 96, "h2": 48},
        {"name": "Deep-Capacity (16 -> 128 -> 64)", "h1": 128, "h2": 64},
        {"name": "High-Capacity (16 -> 160 -> 80)", "h1": 160, "h2": 80},
    ]

    print("\n[*] Evaluating Candidate Architectures...")
    results = []
    for arch in architectures:
        print(f"    -> Evaluating: {arch['name']} (L1={arch['h1']}, L2={arch['h2']})...", end="", flush=True)
        res = evaluate_architecture(
            name=arch["name"],
            h1=arch["h1"],
            h2=arch["h2"],
            X_train=X_train,
            y_cls_train=y_cls_train,
            y_ret_train=y_ret_train,
            X_val=X_val,
            y_cls_val=y_cls_val,
            y_ret_val=y_ret_val,
            epochs=140,
            lr=0.005,
        )
        results.append(res)
        print(f" Done! [Val Acc: {res['val_accuracy']}%, Win Rate: {res['trading']['win_rate']}%, Overfit Gap: {res['overfit_gap_pct']}%]")

    # Rank results by composite score
    ranked_results = sorted(results, key=lambda x: x["composite_score"], reverse=True)
    best = ranked_results[0]

    print("\n==========================================================================")
    print("Comparative Architecture Evaluation Results:")
    print("==========================================================================")
    print(f"{'Architecture':<34} | {'Params':>6} | {'Train Acc':>9} | {'Val Acc':>8} | {'Gap %':>6} | {'WinRate':>7} | {'TotalRet %':>10} | {'Score':>6}")
    print("-" * 105)
    for r in ranked_results:
        star = " [BEST]" if r["name"] == best["name"] else ""
        print(
            f"{r['name']:<34} | {r['parameters']:>6} | {r['train_accuracy']:>8}% | "
            f"{r['val_accuracy']:>7}% | {r['overfit_gap_pct']:>5}% | "
            f"{r['trading']['win_rate']:>6}% | {r['trading']['total_return_pct']:>9}% | "
            f"{r['composite_score']:>6.1f}{star}"
        )
    print("==========================================================================")

    # Save the best performing model weights to production
    best_model = best["_model_instance"]
    saved = best_model.save_weights(WEIGHTS_PATH)
    if saved:
        print(f"\n[+] Production BTC weights updated with best model ({best['name']}) -> {WEIGHTS_PATH.resolve()}")

    # Prepare summary JSON without model instance
    clean_results = []
    for r in ranked_results:
        c = {k: v for k, v in r.items() if not k.startswith("_")}
        clean_results.append(c)

    summary_output_path = PROJECT_ROOT / "optimization_results.json"
    summary_output_path.write_text(json.dumps(clean_results, indent=2), encoding="utf-8")
    print(f"[+] Detailed metrics saved to: {summary_output_path.resolve()}\n")

    return ranked_results


if __name__ == "__main__":
    run_systematic_optimization()
