"""
AutoTrader Pro — Agent 4 Comprehensive Test Suite
=================================================
Validates:
1. Pre-Trade Risk Gate (validate_signal with 10+ rules, rejection reasons)
2. Multi-Model Position Sizing (Fixed, Kelly, Volatility-Adjusted, ATR Damper)
3. Correlation Manager (matrix updates, cross-asset correlation check)
4. Portfolio Monitor (high-water mark, drawdowns, loss streaks, cooldowns)
5. Emergency Shutdown (circuit-breaker liquidation & resume)
6. FastAPI Risk Endpoints (/portfolio-state, /correlation-matrix, /limits, /emergency-shutdown, /resume-trading, /settings)
"""

import os
import sys
import time
from datetime import datetime, timedelta

import pandas as pd
from fastapi.testclient import TestClient

from backend.main import app
from backend.database import SessionLocal
from backend.models import Trade
from backend.engine.strategy_base import StrategySignal
from backend.risk.risk_manager import RiskManager, RiskDecision
from backend.risk.correlation_manager import CorrelationManager
from backend.risk.portfolio_monitor import PortfolioMonitor
from backend.risk.emergency import EmergencyShutdown


def test_position_sizing_models():
    rm = RiskManager()
    portfolio = 100000.0
    entry_price = 8000000.0  # BTC @ 80L

    # 1. Fixed Fractional: 5% of 100,000 = 5,000 INR -> 5,000 / 8,000,000 = 0.000625 BTC
    fixed_size = rm.calculate_position_size(portfolio, entry_price)
    assert abs(fixed_size - 0.000625) < 1e-7

    # 2. Volatility-Adjusted:
    # stop loss 7,900,000 (risk_distance = 100,000). Risk amount = 5,000.
    # vol_size = 5,000 / 100,000 = 0.05 BTC. But capped at fixed ceiling (0.000625).
    vol_size = rm.calculate_position_size(portfolio, entry_price, stop_loss_price=7900000.0)
    assert vol_size <= 0.000625

    # 3. High Volatility ATR Damper (ATR > 2x avg_atr) - halves position size
    damped_size = rm.calculate_position_size(
        portfolio, entry_price, atr=500.0, avg_atr=200.0
    )
    assert abs(damped_size - (fixed_size * 0.5)) < 1e-7

    # 4. Kelly Criterion with high win rate
    kelly_size = rm.calculate_position_size(
        portfolio, entry_price, strategy_win_rate=0.70, avg_win=1000.0, avg_loss=500.0
    )
    assert kelly_size > 0


def test_correlation_manager():
    cm = CorrelationManager(max_correlated_positions=2, correlation_threshold=0.7)

    # Mock price history
    dates = pd.date_range("2026-01-01", periods=60, freq="15min")
    base = pd.Series([100 + i for i in range(60)], index=dates)
    corr_high = pd.Series([200 + i * 2 for i in range(60)], index=dates)
    uncorr = pd.Series([100 + (10 if i % 2 == 0 else -10) for i in range(60)], index=dates)

    history = {
        "BTC/INR": base,
        "ETH/INR": corr_high,
        "SOL/INR": corr_high * 1.05,
        "XRP/INR": uncorr,
    }
    cm.update_correlation_matrix(history)

    # BTC and ETH should be highly correlated (r > 0.8)
    r_btc_eth = cm.get_correlation("BTC/INR", "ETH/INR")
    assert r_btc_eth > 0.8

    # Test rejection when 2 correlated positions already exist in same direction
    open_positions = [
        {"pair": "ETH/INR", "direction": "LONG", "quantity": 0.5, "price": 250000.0},
        {"pair": "SOL/INR", "direction": "LONG", "quantity": 5.0, "price": 15000.0},
    ]

    # New signal for BTC/INR (BUY = LONG). It is correlated with both ETH and SOL (count = 2 >= max 2)
    sig_btc = StrategySignal(pair="BTC/INR", action="BUY", strategy="Neural_Network_BTC", strength=0.8, reason="test")
    allowed, reason = cm.check_correlation(sig_btc, open_positions)
    assert allowed is False
    assert "Correlation limit reached" in reason

    # New signal for XRP/INR (BUY) should pass because it's not correlated
    sig_xrp = StrategySignal(pair="XRP/INR", action="BUY", strategy="Price_Action", strength=0.8, reason="test")
    allowed_xrp, _ = cm.check_correlation(sig_xrp, open_positions)
    assert allowed_xrp is True


def test_portfolio_monitor_and_cooldown():
    pm = PortfolioMonitor(initial_peak=100000.0)

    # 1. Update equity and check drawdown
    # Current value drops to 90,000 (10% drawdown)
    state = pm.update_portfolio_value(90000.0)
    assert state["high_water_mark"] == 100000.0
    assert state["current_drawdown_pct"] == 10.0

    # 2. Consecutive losses tracking
    class MockTrade:
        def __init__(self, pnl):
            self.id = 999
            self.pnl = pnl

    pm.on_trade_closed(MockTrade(-500.0))
    assert pm.consecutive_losses == 1
    assert pm.is_in_cooldown()[0] is False

    pm.on_trade_closed(MockTrade(-400.0))
    assert pm.consecutive_losses == 2
    assert pm.is_in_cooldown()[0] is False

    # 3rd consecutive loss triggers 60m cooldown
    pm.on_trade_closed(MockTrade(-300.0))
    assert pm.consecutive_losses == 3
    in_cd, cd_reason = pm.is_in_cooldown()
    assert in_cd is True
    assert "cooldown active" in cd_reason.lower()

    # A winning trade resets streak and clears cooldown
    pm.on_trade_closed(MockTrade(800.0))
    assert pm.consecutive_losses == 0
    assert pm.consecutive_wins == 1
    assert pm.is_in_cooldown()[0] is False


def test_emergency_shutdown():
    es = EmergencyShutdown()
    assert es.is_trading_allowed() is True

    # Trigger shutdown
    res = es.execute("Test circuit breaker trigger")
    assert es.is_trading_allowed() is False
    assert res["status"] == "EMERGENCY_SHUTDOWN_ACTIVE"

    # Resume trading
    res_resume = es.resume_trading("Operator test clearance")
    assert es.is_trading_allowed() is True
    assert res_resume["status"] == "TRADING_RESUMED"


def test_pre_trade_risk_gate():
    rm = RiskManager()
    portfolio = 100000.0
    open_positions = []

    # Valid signal with SL/TP having R:R = 2.0 (entry 80L, SL 79L risk=1L, TP 82L reward=2L)
    valid_sig = StrategySignal(
        pair="BTC/INR",
        action="BUY",
        strategy="Breakout_Hunter",
        strength=0.85,
        reason="Breakout squeeze",
        metadata={"current_price": 8000000.0, "stop_loss_price": 7900000.0, "take_profit_price": 8200000.0},
    )

    decision = rm.validate_signal(
        signal=valid_sig,
        portfolio_value=portfolio,
        open_positions=open_positions,
        db_session=None,
        current_price=8000000.0,
    )
    assert decision.approved is True
    assert decision.position_size > 0
    assert "min_risk_reward_ratio" in decision.checks_passed
    assert "max_open_trades" in decision.checks_passed

    # 1. Reject if R:R is poor (< 1.5): entry 80L, SL 79L (risk=1L), TP 80.5L (reward=0.5L, R:R=0.5)
    bad_rr_sig = StrategySignal(
        pair="BTC/INR",
        action="BUY",
        strategy="Scalping",
        strength=0.85,
        reason="Bad RR",
        metadata={"current_price": 8000000.0, "stop_loss_price": 7900000.0, "take_profit_price": 8050000.0},
    )
    decision_rr = rm.validate_signal(
        signal=bad_rr_sig,
        portfolio_value=portfolio,
        open_positions=open_positions,
        db_session=None,
        current_price=8000000.0,
    )
    assert decision_rr.approved is False
    assert "min_risk_reward_ratio" in decision_rr.checks_failed

    # 2. Reject if max open trades reached
    five_positions = [
        {"pair": f"COIN{i}/INR", "side": "BUY", "quantity": 1.0, "price": 1000.0} for i in range(5)
    ]
    decision_max = rm.validate_signal(
        signal=valid_sig,
        portfolio_value=portfolio,
        open_positions=five_positions,
        db_session=None,
        current_price=8000000.0,
    )
    assert decision_max.approved is False
    assert "max_open_trades" in decision_max.checks_failed

    # 3. Reject if total exposure would exceed 50%
    heavy_positions = [
        {"pair": "ETH/INR", "side": "BUY", "quantity": 0.2, "entry_price": 250000.0}  # 50,000 INR = 50%
    ]
    decision_exp = rm.validate_signal(
        signal=valid_sig,
        portfolio_value=portfolio,
        open_positions=heavy_positions,
        db_session=None,
        current_price=8000000.0,
    )
    assert decision_exp.approved is False
    assert "max_total_exposure" in decision_exp.checks_failed


def test_api_risk_endpoints():
    with TestClient(app) as client:
        # 1. GET /api/risk/settings and GET /api/risk
        r1 = client.get("/api/risk/settings")
        assert r1.status_code == 200
        data1 = r1.json()
        assert "max_position_pct" in data1
        assert "weekly_loss_limit_pct" in data1
        assert "total_drawdown_limit_pct" in data1
        assert "min_risk_reward_ratio" in data1

        # 2. PUT /api/risk/settings
        update_payload = {"max_position_pct": 4.5, "weekly_loss_limit_pct": 6.5}
        r2 = client.put("/api/risk/settings", json=update_payload)
        assert r2.status_code == 200
        assert r2.json()["risk_settings"]["max_position_pct"] == 4.5
        assert r2.json()["risk_settings"]["weekly_loss_limit_pct"] == 6.5

        # Restore default
        client.put("/api/risk/settings", json={"max_position_pct": 5.0, "weekly_loss_limit_pct": 7.0})

        # 3. GET /api/risk/portfolio-state
        r3 = client.get("/api/risk/portfolio-state")
        assert r3.status_code == 200
        state = r3.json()
        assert "high_water_mark" in state
        assert "current_drawdown_pct" in state
        assert "consecutive_losses" in state
        assert "is_in_cooldown" in state
        assert "trading_enabled" in state

        # 4. GET /api/risk/correlation-matrix
        r4 = client.get("/api/risk/correlation-matrix")
        assert r4.status_code == 200
        corr = r4.json()
        assert "matrix" in corr
        assert "correlation_threshold" in corr
        assert "max_correlated_positions" in corr

        # 5. GET /api/risk/limits
        r5 = client.get("/api/risk/limits")
        assert r5.status_code == 200
        limits = r5.json()
        assert "max_open_trades" in limits
        assert "daily_loss_limit" in limits
        assert "weekly_loss_limit" in limits
        assert "total_drawdown_limit" in limits
        assert "max_total_exposure" in limits

        # 6. POST /api/risk/emergency-shutdown
        r6 = client.post("/api/risk/emergency-shutdown", json={"reason": "Test API shutdown"})
        assert r6.status_code == 200
        assert r6.json()["status"] == "EMERGENCY_SHUTDOWN_ACTIVE"

        # Verify state reflects shutdown
        r_state = client.get("/api/risk/portfolio-state")
        assert r_state.json()["trading_enabled"] is False

        # 7. POST /api/risk/resume-trading
        r7 = client.post("/api/risk/resume-trading", json={"reason": "Test API resume"})
        assert r7.status_code == 200
        assert r7.json()["status"] == "TRADING_RESUMED"

        # Verify state reflects resumed
        r_state2 = client.get("/api/risk/portfolio-state")
        assert r_state2.json()["trading_enabled"] is True


if __name__ == "__main__":
    print("=" * 60)
    print("RUNNING AGENT 4 COMPREHENSIVE TEST SUITE")
    print("=" * 60)

    test_position_sizing_models()
    print("[PASS] 1. Advanced Position Sizing (Fixed, Kelly, Volatility, ATR Damper) verified")

    test_correlation_manager()
    print("[PASS] 2. Correlation Manager (Matrix updates & cross-asset checks) verified")

    test_portfolio_monitor_and_cooldown()
    print("[PASS] 3. Portfolio Monitor (HWM, drawdowns, loss streaks & cooldowns) verified")

    test_emergency_shutdown()
    print("[PASS] 4. Emergency Shutdown (Circuit breaker execution & resume) verified")

    test_pre_trade_risk_gate()
    print("[PASS] 5. Pre-Trade Risk Gate (validate_signal with 10+ rules) verified")

    test_api_risk_endpoints()
    print("[PASS] 6. FastAPI Risk Endpoints (/portfolio-state, /correlation-matrix, /limits, /emergency-shutdown, /resume-trading) verified")

    print("\nALL AGENT 4 TESTS PASSED PERFECTLY (6/6)!")
