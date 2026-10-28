"""
Train ETH Specialist Deep Neural Network Model
==============================================
Downloads complete historical market data for ETH/INR (Yahoo Finance ~3,250 daily candles
plus 17,500 hourly candles) and closed trade experience from SQLite, training
DeepTradingNN and persisting weights directly to backend/engine/nn_weights_eth.json.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.database import SessionLocal, init_db
from backend.engine.neural_net_strategy import NeuralNetworkStrategy, WEIGHTS_PATH_ETH
from backend.exchange.exchange_manager import exchange_manager


def train_eth():
    print("=================================================================")
    print("AutoTrader Pro - ETH Specialist Neural Network Training Pipeline")
    print("=================================================================")
    init_db()
    db = SessionLocal()
    try:
        strategy = NeuralNetworkStrategy(
            name="Neural_Network_ETH",
            weights_path=WEIGHTS_PATH_ETH,
            pair_filter=["ETH/INR"],
        )
        print(f"[*] Training model for: ETH/INR")
        print(f"[*] Saving weights to: {WEIGHTS_PATH_ETH}")

        res = strategy.combine_and_train_unified_model(
            db=db,
            exchange_manager=exchange_manager,
            pair="ETH/INR",
            days=3650,
            epochs=200,
            lr=0.005,
            horizon_bars=5,
            return_threshold_pct=2.0,
            save_path=WEIGHTS_PATH_ETH,
        )

        print("\n=================================================================")
        print("ETH Training Results Summary:")
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
    train_eth()
