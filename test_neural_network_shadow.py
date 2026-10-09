"""
AutoTrader Pro - Neural Network Active Learning & Brain Visualizer Suite
========================================================================
Comprehensive test suite verifying:
  1. 16-Feature Technical Extraction & Dataset Builder
  2. DeepTradingNN Forward Pass, Backprop Training, Layer Activations, and Serialization
  3. Active Trading Signal Generation with Volatility ATR Risk Boundaries
  4. TradingEngine Active Execution Gate (Opens Paper Trades when shadow_mode=False)
  5. Closed-Trade Experience Replay & Reinforcement Learning (Win Reward / Loss Penalty)
  6. Capital Survival Preservation (Paper Trading Only, Risk Limits Intact)
  7. Live Brain Endpoint (/api/strategies/neural_network/live_brain) with Synaptic Activations
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


class TestNeuralNetworkActiveAndBrain(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def test_01_safety_and_config_preservation(self):
        """Verify paper trading mode is strictly preserved and risk controls remain active."""
        self.assertTrue(settings.PAPER_MODE, "PAPER_MODE must remain True!")
        self.assertEqual(settings.PAPER_BALANCE, 10000.0)
        self.assertEqual(settings.MAX_POSITION_PCT, 5.0)
        self.assertEqual(settings.MAX_OPEN_TRADES, 5)
        self.assertEqual(settings.DAILY_LOSS_LIMIT_PCT, 3.0)

        engine = TradingEngine()
        self.assertEqual(engine.mode, "paper", "Engine mode must default to paper!")
        self.assertEqual(engine.risk_manager.max_open_trades, 5)
        self.assertEqual(engine.risk_manager.daily_loss_limit_pct, 3.0)

    def test_02_feature_extraction_and_dataset_builder(self):
        """Verify 16 technical features are extracted cleanly without NaNs or Infs."""
        df = generate_synthetic_candles(120, trend="bullish")
        feats, valid_idx = extract_features_matrix(df)

        self.assertGreater(len(feats), 50)
        self.assertEqual(feats.shape[1], 16)
        self.assertEqual(len(FEATURE_NAMES), 16)
        self.assertFalse(np.isnan(feats).any())
        self.assertFalse(np.isinf(feats).any())

        X, y_class, y_ret = build_training_dataset(df, horizon_bars=3, return_threshold_pct=0.5)
        self.assertGreater(len(X), 50)
        self.assertEqual(X.shape[1], 16)
        self.assertEqual(len(X), len(y_class))
        self.assertEqual(len(X), len(y_ret))

    def test_03_neural_network_activations_and_reinforcement(self):
        """Verify layer activations, firing synapses, and reinforcement feedback."""
        df = generate_synthetic_candles(120, trend="bullish")
        X, y_class, y_ret = build_training_dataset(df, horizon_bars=3, return_threshold_pct=0.4)

        nn = DeepTradingNN(seed=101)
        nn.fit(X, y_class, y_ret, epochs=20, lr=0.008)

        # Test predict_with_activations
        res = nn.predict_with_activations(X[-1])
        self.assertIn("layer1_activations", res)
        self.assertIn("layer2_activations", res)
        self.assertEqual(len(res["layer1_activations"]), 64)
        self.assertEqual(len(res["layer2_activations"]), 32)
        self.assertEqual(len(res["input_features"]), 16)
        self.assertIn("top_synapses", res)

        # Test reinforce_trade_outcome on winning trade
        steps_before = nn.train_steps
        win_res = nn.reinforce_trade_outcome(X[-1], action="BUY", pnl_pct=2.4)
        self.assertEqual(nn.train_steps, steps_before + 1)
        self.assertEqual(win_res["target_class"], "BUY")

        # Test reinforce_trade_outcome on losing trade (penalty averse)
        loss_res = nn.reinforce_trade_outcome(X[-1], action="BUY", pnl_pct=-1.5)
        self.assertEqual(loss_res["target_class"], "HOLD")
        self.assertEqual(loss_res["sample_weight"], 2.5)

    def test_04_active_trading_signal_generation(self):
        """Verify NeuralNetworkStrategy emits active trade signals with dynamic ATR SL/TP."""
        strat = NeuralNetworkStrategy(params={"shadow_mode": False, "min_confidence": 0.40})
        self.assertFalse(strat.params["shadow_mode"], "Active trading mode is enabled")

        df = generate_synthetic_candles(120, trend="bullish")
        strat.model.W_cls[:, 1] += 5.0  # bias class head towards BUY
        signal = strat.analyze(df, "BTC/INR")

        self.assertIsNotNone(signal)
        self.assertEqual(signal.action, "BUY")
        self.assertFalse(signal.metadata["shadow_mode"])
        self.assertFalse(signal.metadata["execution_blocked"])
        self.assertIn("stop_loss_price", signal.metadata)
        self.assertIn("take_profit_price", signal.metadata)
        self.assertGreater(signal.metadata["take_profit_price"], signal.metadata["current_price"])
        self.assertLess(signal.metadata["stop_loss_price"], signal.metadata["current_price"])

    def test_05_trading_engine_active_trade_execution(self):
        """Verify that when shadow_mode=False, TradingEngine executes the paper trade."""
        engine = TradingEngine(mode="paper")
        engine.risk_manager.max_open_trades = 15  # ensure open trade capacity for test
        db = SessionLocal()
        try:
            trades_before = db.query(Trade).filter(Trade.status == "OPEN").count()

            active_signal = StrategySignal(
                pair="BTC/INR",
                action="BUY",
                strategy="Neural_Network",
                strength=0.88,
                reason="[AI NEURAL] DeepNN BUY prediction on BTC/INR with ATR Guard",
                metadata={
                    "shadow_mode": False,
                    "execution_blocked": False,
                    "stop_loss_price": 4900000.0,
                    "take_profit_price": 5200000.0,
                },
            )

            result = engine._process_signal(active_signal, db)
            trades_after = db.query(Trade).filter(Trade.status == "OPEN").count()

            # Result confirms trade execution
            self.assertIsNotNone(result)
            self.assertEqual(result["pair"], "BTC/INR")
            self.assertEqual(result["side"], "BUY")
            self.assertEqual(result["strategy"], "Neural_Network")
            self.assertEqual(trades_after, trades_before + 1, "Active neural signal must execute a paper trade")

            # Verify trade has the neural stop_loss and take_profit
            latest_trade = db.query(Trade).order_by(Trade.id.desc()).first()
            self.assertEqual(latest_trade.strategy, "Neural_Network")
            self.assertEqual(latest_trade.stop_loss, 4900000.0)
            self.assertEqual(latest_trade.take_profit, 5200000.0)

            # Test close and reinforcement
            exit_price = latest_trade.entry_price * 1.03  # +3% win
            engine._close_trade_internal(latest_trade, exit_price, "TAKE_PROFIT", db)
            self.assertEqual(latest_trade.status, "CLOSED")

            nn_strat = next(s for s in engine.strategies if s.name == "Neural_Network")
            self.assertGreaterEqual(len(nn_strat._learning_history), 1)
        finally:
            db.close()

    def test_06_live_brain_endpoint(self):
        """Verify the /api/strategies/neural_network/live_brain endpoint."""
        from backend.main import app

        with TestClient(app) as client:
            res = client.get("/api/strategies/neural_network/live_brain?pair=BTC/INR")
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertIn("brain", data)
            self.assertIn("capital_health", data)

            brain = data["brain"]
            self.assertIn("layer1_activations", brain)
            self.assertIn("layer2_activations", brain)
            self.assertIn("top_synapses", brain)
            self.assertIn("probabilities", brain)
            self.assertEqual(len(brain["layer1_activations"]), 64)
            self.assertEqual(len(brain["layer2_activations"]), 32)
            self.assertEqual(len(brain["input_features"]), 16)

            cap = data["capital_health"]
            self.assertIn("portfolio_value", cap)
            self.assertIn("survival_score", cap)
            self.assertIn("risk_status", cap)

    def test_07_historical_trade_training_and_api(self):
        """Verify training neural network on database closed trade history and the API endpoint."""
        from backend.main import app

        db = SessionLocal()
        try:
            strategy = NeuralNetworkStrategy()
            initial_steps = strategy.model.train_steps
            train_res = strategy.train_on_closed_trades(db, epochs=5)

            self.assertEqual(train_res["status"], "success")
            self.assertGreater(train_res["total_trades"], 0)
            self.assertEqual(train_res["epochs"], 5)
            self.assertIn("loss", train_res)
            self.assertIn("accuracy", train_res)
            self.assertTrue(train_res["weights_saved"])
            self.assertGreater(strategy.model.train_steps, initial_steps)
            self.assertTrue(strategy.weights_path.exists())

            # Test API endpoint
            with TestClient(app) as client:
                res = client.post("/api/strategies/neural_network/train_on_history?epochs=3")
                self.assertEqual(res.status_code, 200)
                data = res.json()
                self.assertIn("message", data)
                self.assertIn("metrics", data)
                self.assertEqual(data["metrics"]["status"], "success")
                self.assertEqual(data["metrics"]["epochs"], 3)
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
