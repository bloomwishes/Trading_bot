"""
AutoTrader Pro - Neural Network Retraining CLI
==============================================
CLI tool to retrain and update all deep neural network models with the expanded
24-feature set. Supports macro candle data, CoinDCX history, and closed-trade
experience.

Usage:
    python -m backend.engine.retrain_models
    python -m backend.engine.retrain_models --models BTC,ETH,ALTS --epochs 40 --lr 0.005
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Dict, Any

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.database import SessionLocal
from backend.engine.neural_net_strategy import (
    NeuralNetworkStrategy,
    WEIGHTS_PATH_BTC,
    WEIGHTS_PATH_ETH,
    WEIGHTS_PATH_ALTS,
)
from backend.engine.neural_net import NUM_FEATURES, FEATURE_NAMES
from backend.utils.logger import bot_logger


def retrain_model(
    model_key: str,
    epochs: int = 40,
    lr: float = 0.005,
    days: int = 730,
) -> Dict[str, Any]:
    """Retrain a specific neural network model and save weights."""
    model_key = model_key.upper()
    db = SessionLocal()

    try:
        if model_key == "BTC":
            strategy = NeuralNetworkStrategy(
                name="Neural_Network_BTC",
                weights_path=WEIGHTS_PATH_BTC,
                pair_filter=["BTC/INR"],
            )
        elif model_key == "ETH":
            strategy = NeuralNetworkStrategy(
                name="Neural_Network_ETH",
                weights_path=WEIGHTS_PATH_ETH,
                pair_filter=["ETH/INR"],
            )
        elif model_key in ("ALTS", "ALT"):
            strategy = NeuralNetworkStrategy(
                name="Neural_Network_ALTS",
                weights_path=WEIGHTS_PATH_ALTS,
                pair_filter=["SOL/INR", "XRP/INR", "BNB/INR"],
            )
        else:
            raise ValueError(f"Unknown model key '{model_key}'. Must be BTC, ETH, or ALTS.")

        print(f"\n=======================================================")
        print(f"[*] Retraining {strategy.name} with {NUM_FEATURES} features...")
        print(f"[*] Target weights file: {strategy.weights_path}")
        print(f"=======================================================")

        res = strategy.combine_and_train_unified_model(
            db=db,
            days=days,
            epochs=epochs,
            lr=lr,
            horizon_bars=5,
            return_threshold_pct=1.5,
        )

        if res.get("status") == "success":
            print(f"[+] Successfully retrained {strategy.name}!")
            print(f"    - Total Samples: {res.get('total_samples', 0)}")
            print(f"    - Overall Accuracy: {res.get('overall_accuracy', 0)*100:.2f}%")
            print(f"    - Macro Accuracy: {res.get('macro_accuracy', 0)*100:.2f}%")
            print(f"    - Final Loss: {res.get('loss', 0):.5f}")
            print(f"    - Weights Saved: {strategy.weights_path}")
        else:
            print(f"[-] Training finished with status: {res.get('status')} ({res.get('reason')})")

        return res

    finally:
        db.close()


def retrain_all_models(
    models: List[str],
    epochs: int = 40,
    lr: float = 0.005,
    days: int = 730,
) -> Dict[str, Any]:
    """Retrain all requested neural network models."""
    results = {}
    print(f"Starting neural network retraining with {NUM_FEATURES} features:")
    for i, name in enumerate(FEATURE_NAMES, 1):
        print(f"  {i:2d}. {name}")

    for m in models:
        try:
            results[m] = retrain_model(m, epochs=epochs, lr=lr, days=days)
        except Exception as exc:
            bot_logger.error(f"Error retraining model {m}: {exc}")
            results[m] = {"status": "error", "error": str(exc)}

    print("\n[+] Retraining complete for models:", list(results.keys()))
    return results


def main() -> None:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(
        description="Retrain AutoTrader Pro Deep Neural Networks with 24 features."
    )
    parser.add_argument(
        "--models",
        type=str,
        default="BTC,ETH,ALTS",
        help="Comma-separated list of models to retrain (BTC, ETH, ALTS). Default: BTC,ETH,ALTS",
    )
    parser.add_argument(
        "--epochs",
        type=int,
        default=40,
        help="Number of Adam training epochs (default: 40)",
    )
    parser.add_argument(
        "--lr",
        type=float,
        default=0.005,
        help="Learning rate for Adam optimizer (default: 0.005)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=730,
        help="Days of historical macro candles (default: 730)",
    )

    args = parser.parse_args()
    model_list = [m.strip().upper() for m in args.models.split(",") if m.strip()]
    retrain_all_models(models=model_list, epochs=args.epochs, lr=args.lr, days=args.days)


if __name__ == "__main__":
    main()
