"""
AutoTrader Pro - Neural Network Shadow Mode Verification Suite
==============================================================
Comprehensive test suite verifying:
  1. 16-Feature Technical Extraction & Dataset Builder
  2. DeepTradingNN Forward Pass, Backprop Training, and Weight Serialization
  3. NeuralNetworkStrategy Shadow Mode Signal Generation
  4. TradingEngine Shadow Mode Gate (DB Signal Persistence + Zero Trade Execution)
  5. Preservation of Paper Trading Mode, Risk Management, and API Keys
  6. FastAPI Endpoints (/api/strategies, /api/strategies/shadow/predictions, /api/strategies/neural_network/train)
"""

import json
import os
import tempfile
import unittest
import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from backend.config import settings
from backend.database import SessionLocal, init_db
from backend.models import Trade, Signal
from backend.engine.neural_net import (
    DeepTradingNN,
    extract_features_matrix,
    build_training_dataset,
    FEATURE_NAMES,
)
from backend.engine.neural_net_strategy import NeuralNetworkStrategy
from backend.engine.strategy_base import StrategySignal
from backend.engine.trading_engine import TradingEngine


def generate_synthetic_candles(n: int = 120, trend: str = "bullish", seed: int = 42) -> pd.DataFrame:
    """Generate realistic synthetic OHLCV candle data for testing."""
    rng = np.random.default_rng(seed)
    prices = [5000000.0]  # ~50L INR BTC price
    for i in range(1, n):
        drift = 0.005 if trend == "bullish" else (-0.005 if trend == "bearish" else 0.0005 * np.sin(i / 5.0))
        shock = rng.normal(drift, 0.006)
        prices.append(prices[-1] * (1.0 + shock))

    close = np.array(prices, dtype=np.float64)
    open_p = np.roll(close, 1)
    open_p[0] = close[0] * 0.999
    high = np.maximum(open_p, close) * (1.0 + rng.uniform(0.001, 0.005, size=n))
    low = np.minimum(open_p, close) * (1.0 - rng.uniform(0.001, 0.005, size=n))
    volume = rng.uniform(10.0, 100.0, size=n)

    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01", periods=n, freq="15min").astype(str),
            "open": open_p,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        }
    )


class TestNeuralNetworkShadowIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def test_01_safety_and_config_preservation(self):
        """Verify paper trading mode is active and risk management is untouched."""
        self.assertTrue(settings.PAPER_MODE, "PAPER_MODE must remain True!")
        self.assertEqual(settings.PAPER_BALANCE, 10000.0)
        self.assertEqual(settings.MAX_POSITION_PCT, 5.0)
        self.assertEqual(settings.MAX_OPEN_TRADES, 5)
        self.assertEqual(settings.DAILY_LOSS_LIMIT_PCT, 3.0)
        self.assertEqual(settings.DEFAULT_STOP_LOSS_PCT, 1.5)
        self.assertEqual(settings.DEFAULT_TAKE_PROFIT_PCT, 3.0)

        engine = TradingEngine()
        self.assertEqual(engine.mode, "paper", "Engine mode must default to paper!")
        self.assertEqual(engine.risk_manager.max_open_trades, 5)
        self.assertEqual(engine.risk_manager.daily_loss_limit_pct, 3.0)
        self.assertEqual(engine.risk_manager.max_position_pct, 5.0)

    def test_02_feature_extraction_and_dataset_builder(self):
        """Verify 16 technical features are extracted cleanly without NaNs or Infs."""
        df = generate_synthetic_candles(120, trend="bullish")
        feats, valid_idx = extract_features_matrix(df)

        self.assertGreater(len(feats), 50)
        self.assertEqual(feats.shape[1], 16)
        self.assertEqual(len(FEATURE_NAMES), 16)
        self.assertFalse(np.isnan(feats).any(), "Features must not contain NaN")
        self.assertFalse(np.isinf(feats).any(), "Features must not contain Inf")
        self.assertTrue((feats >= -10.0).all() and (feats <= 10.0).all())

        X, y_class, y_ret = build_training_dataset(df, horizon_bars=3, return_threshold_pct=0.5)
        self.assertGreater(len(X), 50)
        self.assertEqual(X.shape[1], 16)
        self.assertEqual(len(X), len(y_class))
        self.assertEqual(len(X), len(y_ret))
        self.assertTrue(set(np.unique(y_class)).issubset({0, 1, 2}))

    def test_03_neural_network_training_and_serialization(self):
        """Verify DeepTradingNN reduces loss during training and serializes weights accurately."""
        df = generate_synthetic_candles(140, trend="bullish")
        X, y_class, y_ret = build_training_dataset(df, horizon_bars=3, return_threshold_pct=0.4)

        nn = DeepTradingNN(seed=101)
        # Measure initial loss
        probs_init, ret_init, _ = nn.forward(X)
        eps = 1e-8
        init_ce = -np.mean(np.log(probs_init[np.arange(len(y_class)), y_class] + eps))

        # Train for 30 epochs
        metrics = nn.fit(X, y_class, y_ret, epochs=30, lr=0.008)
        self.assertGreater(nn.train_steps, 0)
        self.assertIn("loss", metrics)

        probs_after, _, _ = nn.forward(X)
        final_ce = -np.mean(np.log(probs_after[np.arange(len(y_class)), y_class] + eps))
        self.assertLess(final_ce, init_ce, "Cross-entropy loss must decrease after training")

        # Check softmax probabilities sum to 1.0
        row_sums = np.sum(probs_after, axis=1)
        np.testing.assert_allclose(row_sums, np.ones_like(row_sums), atol=1e-5)

        # Check single sample inference
        pred = nn.predict_single(X[-1])
        self.assertIn(pred["action"], ("HOLD", "BUY", "SELL"))
        self.assertAlmostEqual(sum(pred["probabilities"].values()), 1.0, places=4)

        # Check weight save/load round-trip
        with tempfile.TemporaryDirectory() as tmpdir:
            weight_path = os.path.join(tmpdir, "nn_weights.json")
            saved = nn.save_weights(weight_path)
            self.assertTrue(saved)

            nn2 = DeepTradingNN(seed=999)
            loaded = nn2.load_weights(weight_path)
            self.assertTrue(loaded)
            pred2 = nn2.predict_single(X[-1])
            self.assertEqual(pred["action"], pred2["action"])
            self.assertAlmostEqual(pred["confidence"], pred2["confidence"], places=6)

    def test_04_neural_network_strategy_shadow_mode(self):
        """Verify NeuralNetworkStrategy operates in shadow mode and generates rich metadata."""
        strat = NeuralNetworkStrategy(params={"min_confidence": 0.50})
        self.assertTrue(strat.params["shadow_mode"], "Shadow mode must be enabled by default")

        df = generate_synthetic_candles(120, trend="bullish")
        strat.analyze(df, "BTC/INR")

        stats = strat.get_shadow_stats()
        self.assertTrue(stats["shadow_mode"])
        self.assertGreaterEqual(stats["total_predictions"], 1)
        self.assertIn("BTC/INR", stats["trained_pairs"])

        # When the neural net classifies a directional setup with sufficient confidence
        strat.model.W_cls[:, 1] += 5.0  # bias class head towards BUY
        signal = strat.analyze(df, "BTC/INR")

        self.assertIsNotNone(signal)
        self.assertEqual(signal.action, "BUY")
        self.assertEqual(signal.strategy, "Neural_Network")
        self.assertTrue(signal.metadata.get("shadow_mode"))
        self.assertTrue(signal.metadata.get("execution_blocked"))
        self.assertIn("probabilities", signal.metadata)
        self.assertIn("[SHADOW MODE]", signal.reason)

    def test_05_trading_engine_shadow_gate_blocks_trades(self):
        """
        Verify TradingEngine._process_signal saves shadow signals to the database
        but NEVER executes any paper or live trade.
        """
        engine = TradingEngine(mode="paper")
        strategy_names = [s.name for s in engine.strategies]
        self.assertIn("Neural_Network", strategy_names)

        db = SessionLocal()
        try:
            trades_before = db.query(Trade).count()
            signals_before = db.query(Signal).filter(Signal.strategy == "Neural_Network").count()
            cash_before = engine.paper_trader.balance

            shadow_signal = StrategySignal(
                pair="BTC/INR",
                action="BUY",
                strategy="Neural_Network",
                strength=0.84,
                reason="[SHADOW MODE] DeepNN BUY prediction on BTC/INR",
                metadata={
                    "shadow_mode": True,
                    "execution_blocked": True,
                    "expected_return_pct": 1.45,
                    "probabilities": {"HOLD": 0.08, "BUY": 0.84, "SELL": 0.08},
                },
            )

            result = engine._process_signal(shadow_signal, db)

            trades_after = db.query(Trade).count()
            signals_after = db.query(Signal).filter(Signal.strategy == "Neural_Network").count()
            cash_after = engine.paper_trader.balance

            # 1. Result confirms shadow mode & non-execution
            self.assertIsNotNone(result)
            self.assertTrue(result["shadow_mode"])
            self.assertFalse(result["executed"])
            self.assertEqual(result["strategy"], "Neural_Network")

            # 2. Signal WAS persisted to the database
            self.assertEqual(signals_after, signals_before + 1)

            # 3. ZERO trades were opened and paper cash balance is 100% untouched
            self.assertEqual(trades_after, trades_before, "Shadow mode must NEVER open a trade!")
            self.assertEqual(cash_after, cash_before, "Shadow mode must NEVER alter paper balance!")
        finally:
            db.close()

    def test_06_fastapi_shadow_and_training_endpoints(self):
        """Verify FastAPI endpoints for strategy config, training, and shadow telemetry."""
        from backend.main import app

        with TestClient(app) as client:
            # 1. Check /api/strategies lists Neural_Network
            res = client.get("/api/strategies")
            self.assertEqual(res.status_code, 200)
            strategies = res.json().get("strategies", {})
            self.assertIn("Neural_Network", strategies)
            self.assertTrue(strategies["Neural_Network"]["params"]["shadow_mode"])

            # 2. Trigger calibration on BTC/INR
            train_res = client.post(
                "/api/strategies/neural_network/train",
                json={"pair": "BTC/INR"},
            )
            self.assertEqual(train_res.status_code, 200)
            train_data = train_res.json()
            self.assertIn("metrics", train_data)
            self.assertEqual(train_data["metrics"]["status"], "trained")

            # 3. Query shadow predictions telemetry
            shadow_res = client.get("/api/strategies/shadow/predictions?limit=10")
            self.assertEqual(shadow_res.status_code, 200)
            shadow_data = shadow_res.json()
            self.assertIn("shadow_telemetry", shadow_data)
            self.assertIn("persisted_signals", shadow_data)
            self.assertTrue(shadow_data["shadow_telemetry"]["shadow_mode"])
            self.assertIsInstance(shadow_data["persisted_signals"], list)


if __name__ == "__main__":
    unittest.main(verbosity=2)
