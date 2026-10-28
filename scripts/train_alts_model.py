"""
Train Major Altcoins Specialist Deep Neural Network Model
=========================================================
Downloads complete historical market data for major altcoins (SOL/INR, XRP/INR, BNB/INR)
from Yahoo Finance (multi-year daily and hourly candles) and closed trade experience
from SQLite, training DeepTradingNN and persisting weights directly to backend/engine/nn_weights_alts.json.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.database import SessionLocal, init_db
from backend.engine.neural_net_strategy import NeuralNetworkStrategy, WEIGHTS_PATH_ALTS
from backend.exchange.exchange_manager import exchange_manager


def train_alts():
    print("=================================================================")
    print("AutoTrader Pro - Major Altcoins Neural Network Training Pipeline")
    print("=================================================================")
    init_db()
    db = SessionLocal()
    try:
        strategy = NeuralNetworkStrategy(
            name="Neural_Network_ALTS",
            weights_path=WEIGHTS_PATH_ALTS,
            pair_filter=["SOL/INR", "XRP/INR", "BNB/INR"],
        )
        print(f"[*] Training model for: SOL/INR, XRP/INR, BNB/INR, DOGE/INR, ADA/INR, LINK/INR")
        print(f"[*] Saving weights to: {WEIGHTS_PATH_ALTS}")

        res = strategy.combine_and_train_unified_model(
            db=db,
            exchange_manager=exchange_manager,
            pairs=["SOL/INR", "XRP/INR", "BNB/INR", "DOGE/INR", "ADA/INR", "LINK/INR"],
            days=3650,
            epochs=200,
            lr=0.005,
            horizon_bars=5,
            return_threshold_pct=2.0,
            save_path=WEIGHTS_PATH_ALTS,
        )

        print("\n=================================================================")
        print("Altcoins Training Results Summary:")
        print("=================================================================")
        print(f"[+] Status: {res.get('status')}")
        print(f"[+] Total Samples: {res.get('total_samples')}")
        print(f"[+] Macro Samples: {res.get('macro_samples')}")
        print(f"[+] Loss: {res.get('loss'):.4f}")
        print(f"[+] Overall Accuracy: {res.get('overall_accuracy', 0)*100:.2f}%")
        print(f"[+] Macro Accuracy: {res.get('macro_accuracy', 0)*100:.2f}%")
        print(f"[+] Weights Saved: {res.get('weights_path')}")
        print("=================================================================\n")
        return res
    finally:
        db.close()


if __name__ == "__main__":
    train_alts()
