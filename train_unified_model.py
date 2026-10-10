"""
AutoTrader Pro - Unified Neural Network Training Pipeline
==========================================================
Combines:
  1. 24 Months of Historical CoinDCX BTC/INR Daily Candles (macro market regimes & cycle structure)
  2. Live Closed-Trade Experience from SQLite (capital loss aversion penalties & winning setup rewards)
Into a single unified DeepTradingNN model (16 -> 64 -> 32 -> DualHead) and persists weights
directly to backend/engine/nn_weights.json for production execution.
"""

import argparse
import json
import sys
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.database import SessionLocal, init_db
from backend.engine.neural_net_strategy import NeuralNetworkStrategy, WEIGHTS_PATH
from backend.exchange.exchange_manager import exchange_manager
from backend.utils.logger import bot_logger


def run_unified_training(
    days: int = 730,
    epochs: int = 100,
    lr: float = 0.005,
    horizon: int = 5,
    threshold: float = 2.0,
) -> dict:
    print("=================================================================")
    print("AutoTrader Pro - Unified Model Training Pipeline")
    print("=================================================================")
    print(f"[*] Configuration: days={days}, epochs={epochs}, lr={lr}, horizon={horizon}, threshold={threshold}%")

    init_db()
    db = SessionLocal()
    try:
        strategy = NeuralNetworkStrategy()
        print(f"[*] Model architecture: 16 -> 64 (LayerNorm+LeakyReLU) -> 32 (LayerNorm+LeakyReLU) -> DualHead")
        print(f"[*] Target weights file: {WEIGHTS_PATH.resolve()}")

        res = strategy.combine_and_train_unified_model(
            db=db,
            exchange_manager=exchange_manager,
            days=days,
            epochs=epochs,
            lr=lr,
            horizon_bars=horizon,
            return_threshold_pct=threshold,
            save_path=WEIGHTS_PATH,
        )

        print("\n=================================================================")
        print("Training Results Summary:")
        print("=================================================================")
        print(f"[+] Status: {res.get('status')}")
        print(f"[+] Total Samples Combined: {res.get('total_samples')}")
        print(f"    - Macro Candles (24-Month CoinDCX): {res.get('macro_samples')}")
        print(f"    - Trade Experience (SQLite DB)   : {res.get('trade_samples')} ({res.get('wins_count')} wins, {res.get('loss_count')} losses)")
        print(f"[+] Final Loss: {res.get('loss'):.4f}")
        print(f"[+] Overall Combined Accuracy: {res.get('overall_accuracy', 0)*100:.2f}%")
        print(f"[+] 24-Month Macro Accuracy  : {res.get('macro_accuracy', 0)*100:.2f}%")
        print(f"[+] Trade Experience Accuracy: {res.get('trade_accuracy', 0)*100:.2f}%")
        print(f"[+] Live Weights Saved: {res.get('weights_path')}")
        print("=================================================================\n")
        return res
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train unified neural network model combining macro data and trade history")
    parser.add_argument("--days", type=int, default=730, help="Days of history to download (730 = 24 months)")
    parser.add_argument("--epochs", type=int, default=100, help="Training epochs")
    parser.add_argument("--lr", type=float, default=0.005, help="Learning rate")
    parser.add_argument("--horizon", type=int, default=5, help="Forward return horizon bars")
    parser.add_argument("--threshold", type=float, default=2.0, help="Return threshold % for BUY/SELL labels")

    args = parser.parse_args()
    summary = run_unified_training(
        days=args.days,
        epochs=args.epochs,
        lr=args.lr,
        horizon=args.horizon,
        threshold=args.threshold,
    )
    print(json.dumps({k: v for k, v in summary.items() if not k.startswith("_")}, indent=2))
