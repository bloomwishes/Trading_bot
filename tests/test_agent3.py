"""
AutoTrader Pro — Agent 3 Comprehensive Test Suite
=================================================
Validates:
1. Smart Order Router (OrderPlan, market/limit/TWAP thresholds, fallbacks)
2. Unified Position Tracker (Position, aggregation, mark-to-market, exposure, close)
3. Paper Trader (slippage simulation, partial fills, history, performance summary)
4. Trading Engine execution lifecycle, metrics, scalping max hold exit, grid rebalance exit
5. FastAPI Trades & Bot Endpoints:
   - POST /api/bot/start (all 12 strategies remain enabled)
   - GET /api/trades/performance
   - GET /api/trades/positions
   - GET /api/trades/execution-quality
   - PUT /api/trades/{id}/stop-loss
   - PUT /api/trades/{id}/take-profit
"""

import os
import sys
import time
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from backend.main import app
from backend.database import SessionLocal
from backend.models import Trade
from backend.engine.strategy_base import StrategySignal
from backend.engine.order_router import SmartOrderRouter, OrderPlan
from backend.engine.position_tracker import PositionTracker, Position
from backend.paper.paper_trader import PaperTrader
from backend.engine.trading_engine import TradingEngine


def test_smart_order_router_thresholds():
    router = SmartOrderRouter()
    signal = StrategySignal(pair="BTC/INR", action="BUY", strategy="Neural_Network_BTC", strength=0.85, reason="Test signal")

    # Mock order book with 10.0 BTC top liquidity, bid 8,000,000, ask 8,020,000 (mid = 8,010,000)
    order_book = {
        "bids": [[8000000.0, 5.0], [7990000.0, 5.0]],
        "asks": [[8020000.0, 5.0], [8030000.0, 5.0]],
    }

    # 1. Small order (< 5% of 10.0 BTC = < 0.5 BTC) -> MARKET order
    small_state = {"order_book": order_book, "current_price": 8010000.0}
    small_plans = router.route(signal, small_state, quantity=0.2)
    assert len(small_plans) == 1
    assert small_plans[0].order_type == "MARKET"
    assert small_plans[0].quantity == 0.2

    # 2. Medium order (5% to 20% of 10.0 BTC = 0.5 to 2.0 BTC) -> LIMIT order at mid price
    med_plans = router.route(signal, small_state, quantity=1.0)
    assert len(med_plans) == 1
    assert med_plans[0].order_type == "LIMIT"
    assert med_plans[0].price == 8010000.0
    assert med_plans[0].fallback == "MARKET"

    # 3. Large order (> 20% of 10.0 BTC = > 2.0 BTC) -> TWAP split into chunks
    large_plans = router.route(signal, small_state, quantity=5.0)
    assert len(large_plans) >= 3
    total_qty = sum(p.quantity for p in large_plans)
    assert abs(total_qty - 5.0) < 1e-5
    # Verify chunks are spaced 30s apart
    delays = [p.delay_seconds for p in large_plans]
    assert delays[0] == 0.0
    assert delays[1] == 30.0
    assert delays[2] == 60.0

    # 4. Fallback when order book is empty
    empty_plans = router.route(signal, {"current_price": 8010000.0}, quantity=1.0)
    assert len(empty_plans) == 1
    assert empty_plans[0].order_type == "MARKET"


def test_position_tracker_aggregation_and_mtm():
    tracker = PositionTracker()

    # Open first tranche: 0.1 BTC @ 8,000,000
    pos1 = tracker.open_position({
        "pair": "BTC/INR",
        "side": "BUY",
        "quantity": 0.1,
        "price": 8000000.0,
        "stop_loss": 7800000.0,
        "take_profit": 8400000.0,
        "strategy": "Breakout_Hunter",
        "trade_id": 101,
    })
    assert pos1.quantity == 0.1
    assert pos1.avg_entry_price == 8000000.0
    assert pos1.trade_ids == [101]

    # Open second tranche for same pair: 0.1 BTC @ 8,200,000
    # Average entry should be (0.1 * 8,000,000 + 0.1 * 8,200,000) / 0.2 = 8,100,000
    pos2 = tracker.open_position({
        "pair": "BTC/INR",
        "side": "BUY",
        "quantity": 0.1,
        "price": 8200000.0,
        "stop_loss": 7900000.0,
        "take_profit": 8500000.0,
        "strategy": "Scalping",
        "trade_id": 102,
    })
    assert pos2.quantity == 0.2
    assert pos2.avg_entry_price == 8100000.0
    assert 101 in pos2.trade_ids and 102 in pos2.trade_ids

    # Mark-to-market update at current price 8,500,000
    # Unrealized PnL = (8,500,000 - 8,100,000) * 0.2 = 80,000 INR (+4.94%)
    tracker.update_mark_to_market({"BTC/INR": 8500000.0})
    updated_pos = tracker.get_position("BTC/INR")
    assert updated_pos is not None
    assert updated_pos.unrealized_pnl == 80000.0
    assert updated_pos.unrealized_pnl_pct > 4.9

    # Check total exposure = 0.2 * 8,100,000 = 1,620,000 INR
    exposure = tracker.get_total_exposure()
    assert exposure == 1620000.0

    # Close position
    realized_pnl = tracker.close_position("BTC/INR", exit_price=8500000.0, reason="TAKE_PROFIT")
    assert realized_pnl == 80000.0
    assert tracker.get_position("BTC/INR") is None


def test_paper_trader_slippage_and_summary():
    pt = PaperTrader(initial_balance=500000.0)

    # 1. Test backward-compatible execute_trade (exact price)
    trade_exact = pt.execute_trade("ETH/INR", "BUY", 0.5, 250000.0, strategy="Manual")
    assert trade_exact["entry_price"] == 250000.0
    assert trade_exact["slippage_bps"] == 0.0
    pt.close_trade(trade_exact["id"], 251000.0, exit_reason="TAKE_PROFIT")

    # 2. Test execute_trade_with_slippage on MARKET order
    trade_market = pt.execute_trade_with_slippage(
        "ETH/INR", "BUY", 0.5, 250000.0, strategy="Scalping", order_type="MARKET"
    )
    # Buy market order should have effective price >= 250000
    assert trade_market["entry_price"] >= 250000.0
    assert trade_market["slippage_bps"] >= 0.0

    # 3. Close the trade with profit
    close_res = pt.close_trade(trade_market["id"], 260000.0, exit_reason="TAKE_PROFIT")
    assert close_res["status"] == "CLOSED"
    assert close_res["pnl"] > 0

    # 4. Check performance summary
    summary = pt.get_performance_summary()
    assert summary["total_trades"] >= 1
    assert "win_rate" in summary
    assert "profit_factor" in summary
    assert "avg_hold_time_seconds" in summary


def test_trading_engine_execution_and_exits():
    engine = TradingEngine(mode="paper")
    engine.paper_trader.balance = 100000.0
    assert hasattr(engine, "order_router")
    assert hasattr(engine, "position_tracker")

    # 1. Test smart trade execution
    signal = StrategySignal(pair="SOL/INR", action="BUY", strategy="Neural_Network_ALTS", strength=0.88, reason="Test signal")
    trade_info = engine._execute_trade(
        pair="SOL/INR",
        side="BUY",
        quantity=2.0,
        price=15000.0,
        stop_loss=14000.0,
        take_profit=17000.0,
        signal=signal,
    )
    assert trade_info is not None
    assert "execution_metrics" in trade_info
    metrics = trade_info["execution_metrics"]
    assert metrics["total_filled"] == 2.0
    assert metrics["num_orders"] >= 1
    assert "fill_time_ms" in metrics
    assert "slippage_bps" in metrics

    # Verify position is recorded in position_tracker
    pos = engine.position_tracker.get_position("SOL/INR")
    assert pos is not None
    assert pos.quantity == 2.0
    if trade_info.get("id"):
        engine.paper_trader.close_trade(trade_info["id"], 155000.0, exit_reason="TAKE_PROFIT")

    # 2. Test Scalping MAX_HOLD_TIME exit
    db = SessionLocal()
    try:
        # Create a mock open scalping trade created 400 seconds ago (> 300s max hold)
        old_time = datetime.utcnow() - timedelta(seconds=400)
        scalp_trade = Trade(
            pair="SOL/INR",
            side="BUY",
            strategy="Scalping",
            entry_price=15000.0,
            quantity=1.0,
            status="OPEN",
            paper_mode=True,
            created_at=old_time,
        )
        db.add(scalp_trade)
        db.commit()
        db.refresh(scalp_trade)

        # Mock ticker price
        engine.exchange_manager.get_ticker = lambda pair: {"last_price": 15100.0}

        # Check single trade
        engine._check_single_trade(scalp_trade, db)
        db.refresh(scalp_trade)
        assert scalp_trade.status == "CLOSED"
        assert scalp_trade.exit_reason == "MAX_HOLD_TIME"

        # 3. Test Grid_Trading GRID_REBALANCE exit (price deviation >= 5%)
        grid_trade = Trade(
            pair="SOL/INR",
            side="BUY",
            strategy="Grid_Trading",
            entry_price=15000.0,
            quantity=1.0,
            status="OPEN",
            paper_mode=True,
            created_at=datetime.utcnow(),
        )
        db.add(grid_trade)
        db.commit()
        db.refresh(grid_trade)

        # Price dropped 6% to 14,100
        engine.exchange_manager.get_ticker = lambda pair: {"last_price": 14100.0}
        engine._check_single_trade(grid_trade, db)
        db.refresh(grid_trade)
        assert grid_trade.status == "CLOSED"
        assert grid_trade.exit_reason == "GRID_REBALANCE"

    finally:
        db.close()


def test_api_endpoints():
    auth_headers = {"X-API-Key": "test-secret-key"}
    with TestClient(app) as client:
        # 1. POST /api/bot/start - ensure all 12 strategies remain enabled!
        # First ensure bot is stopped
        client.post("/api/bot/stop", headers=auth_headers)
        start_res = client.post("/api/bot/start", headers=auth_headers)
        assert start_res.status_code == 200

        engine = app.state.engine
        assert engine.running is True
        assert len(engine.strategies) == 12
        enabled_strats = [s.name for s in engine.strategies if s.enabled]
        # Traditional strategies must NOT be disabled on start_bot
        assert "Breakout_Hunter" in enabled_strats
        assert "MA_Pullback" in enabled_strats
        assert "RSI_Divergence" in enabled_strats
        assert "Grid_Trading" in enabled_strats
        assert "Price_Action" in enabled_strats
        assert "Sentiment_LLM" in enabled_strats
        assert "Neural_Network_BTC" in enabled_strats
        assert "Scalping" in enabled_strats
        assert "Mean_Reversion" in enabled_strats
        assert "Stat_Arb" in enabled_strats

        # 2. GET /api/trades/performance
        perf_res = client.get("/api/trades/performance")
        assert perf_res.status_code == 200
        perf = perf_res.json()
        assert "total_trades" in perf
        assert "win_rate" in perf
        assert "profit_factor" in perf
        assert "sharpe_ratio" in perf

        # 3. GET /api/trades/positions
        pos_res = client.get("/api/trades/positions")
        assert pos_res.status_code == 200
        pos_data = pos_res.json()
        assert "positions" in pos_data
        assert "total_exposure" in pos_data

        # 4. GET /api/trades/execution-quality
        eq_res = client.get("/api/trades/execution-quality")
        assert eq_res.status_code == 200
        eq_data = eq_res.json()
        assert "average_slippage_bps" in eq_data
        assert "router_status" in eq_data
        assert eq_data["router_status"] == "ACTIVE"
        assert "supported_order_types" in eq_data

        # 5. Create an open trade to test PUT /api/trades/{id}/stop-loss and take-profit
        db = SessionLocal()
        try:
            test_trade = Trade(
                pair="BTC/INR",
                side="BUY",
                strategy="Neural_Network_BTC",
                entry_price=8000000.0,
                quantity=0.01,
                status="OPEN",
                stop_loss=7800000.0,
                take_profit=8400000.0,
                paper_mode=True,
                created_at=datetime.utcnow(),
            )
            db.add(test_trade)
            db.commit()
            db.refresh(test_trade)
            trade_id = test_trade.id

            # PUT /api/trades/{id}/stop-loss
            sl_res = client.put(f"/api/trades/{trade_id}/stop-loss", json={"stop_loss": 7850000.0}, headers=auth_headers)
            assert sl_res.status_code == 200
            assert sl_res.json()["stop_loss"] == 7850000.0

            # PUT /api/trades/{id}/take-profit
            tp_res = client.put(f"/api/trades/{trade_id}/take-profit", json={"take_profit": 8550000.0}, headers=auth_headers)
            assert tp_res.status_code == 200
            assert tp_res.json()["take_profit"] == 8550000.0

            # Clean up
            db.delete(test_trade)
            db.commit()
        finally:
            db.close()


if __name__ == "__main__":
    print("=" * 60)
    print("RUNNING AGENT 3 COMPREHENSIVE TEST SUITE")
    print("=" * 60)

    test_smart_order_router_thresholds()
    print("[PASS] 1. Smart Order Router thresholds & TWAP chunking verified")

    test_position_tracker_aggregation_and_mtm()
    print("[PASS] 2. Unified Position Tracker aggregation & MTM verified")

    test_paper_trader_slippage_and_summary()
    print("[PASS] 3. Paper Trader slippage modeling & summary verified")

    test_trading_engine_execution_and_exits()
    print("[PASS] 4. Trading Engine execution, metrics, and exit triggers verified")

    test_api_endpoints()
    print("[PASS] 5. FastAPI trades & bot management endpoints verified")

    print("\nALL AGENT 3 TESTS PASSED PERFECTLY (5/5)!")
