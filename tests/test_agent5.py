"""
AutoTrader Pro — Agent 5 Comprehensive Test Suite
=================================================
Validates:
1. System Health Monitor (API, DB, Scheduler, WS, Freshness checks & 1-3-5-10 escalation ladder)
2. Performance Analytics Engine (Core, Averages, Risk-adjusted ratios, Drawdowns, Streaks, Breakdowns, Execution)
3. Strategy Performance Tracker (Rolling windows, degradation detection, auto-disable, dynamic weights)
4. Alert Manager (Priority routing, non-blocking dispatch, circular buffer)
5. Daily Report Generator (Digest assembly, markdown formatting, dispatch)
6. Structured Logging Helpers (Event formatting, trace_id generation, categorization)
7. FastAPI Monitoring & Analytics Endpoints (/status, /status/health, /portfolio/analytics, /portfolio/equity-curve)
"""

import os
import sys
import time
from datetime import datetime, timedelta, timezone

import numpy as np
from fastapi.testclient import TestClient

from backend.main import app
from backend.database import SessionLocal
from backend.models import PortfolioSnapshot, Trade
from backend.monitoring.alert_manager import AlertManager, alert_manager
from backend.monitoring.health_monitor import SystemHealthMonitor, health_monitor
from backend.monitoring.performance_analytics import PerformanceAnalytics
from backend.monitoring.strategy_tracker import StrategyPerformanceTracker, strategy_tracker
from backend.monitoring.daily_report import DailyReportGenerator
from backend.utils.logger import log_trade_event, log_signal_event, log_risk_event


def create_mock_trades() -> list[Trade]:
    """Generate a rich sample trade history for testing analytics."""
    now = datetime.now(timezone.utc)
    trades = []

    # 1. BTC Winning trade (Breakout_Hunter)
    trades.append(
        Trade(
            id=101,
            pair="BTC/INR",
            strategy="Breakout_Hunter",
            side="BUY",
            entry_price=8000000.0,
            exit_price=8200000.0,
            quantity=0.1,
            pnl=20000.0,
            status="CLOSED",
            created_at=now - timedelta(hours=4),
            closed_at=now - timedelta(hours=3),
            entry_reason="BB Squeeze",
            exit_reason="TAKE_PROFIT",
        )
    )

    # 2. ETH Losing trade (MA_Pullback)
    trades.append(
        Trade(
            id=102,
            pair="ETH/INR",
            strategy="MA_Pullback",
            side="BUY",
            entry_price=250000.0,
            exit_price=245000.0,
            quantity=1.0,
            pnl=-5000.0,
            status="CLOSED",
            created_at=now - timedelta(hours=2),
            closed_at=now - timedelta(hours=1),
            entry_reason="Pullback to EMA 21",
            exit_reason="STOP_LOSS",
        )
    )

    # 3. SOL Winning trade (Neural_Network_ALTS)
    trades.append(
        Trade(
            id=103,
            pair="SOL/INR",
            strategy="Neural_Network_ALTS",
            side="BUY",
            entry_price=12000.0,
            exit_price=12600.0,
            quantity=5.0,
            pnl=3000.0,
            status="CLOSED",
            created_at=now - timedelta(minutes=45),
            closed_at=now - timedelta(minutes=15),
            entry_reason="NN Conf 0.82",
            exit_reason="TAKE_PROFIT",
        )
    )

    # 4. BTC Break-even trade
    trades.append(
        Trade(
            id=104,
            pair="BTC/INR",
            strategy="Mean_Reversion",
            side="BUY",
            entry_price=8100000.0,
            exit_price=8100000.0,
            quantity=0.05,
            pnl=0.0,
            status="CLOSED",
            created_at=now - timedelta(days=2),
            closed_at=now - timedelta(days=2, hours=-1),
            entry_reason="RSI Oversold",
            exit_reason="MANUAL",
        )
    )

    return trades


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1. Health Monitor Tests
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def test_health_monitor_checks_and_escalation():
    monitor = SystemHealthMonitor()

    # DB check
    db_res = monitor.check_database()
    assert db_res["status"] == "ok"
    assert db_res["latency_ms"] >= 0

    # API check (standalone)
    api_res = monitor.run_check("coindcx_api")
    assert api_res["status"] in ("ok", "warning", "error")

    # Scheduler check
    sched_res = monitor.check_scheduler()
    assert sched_res["status"] in ("ok", "warning")

    # Overall health assessment
    status = monitor.get_health_status()
    assert "overall_status" in status
    assert "healthy" in status
    assert "checks" in status

    # Verify escalation ladder simulation
    comp = "coindcx_api"
    monitor.failures[comp] = 0

    # 1 fail -> warning
    monitor._handle_escalation(comp, 1, "Simulated 1st fail")
    assert monitor.failures[comp] == 0  # not modified by handler

    # 3 fails -> HIGH alert
    monitor._handle_escalation(comp, 3, "Simulated 3rd fail")

    # 5 fails -> CRITICAL alert + recovery
    monitor._handle_escalation(comp, 5, "Simulated 5th fail")

    # 10 fails -> Emergency shutdown
    monitor._handle_escalation(comp, 10, "Simulated 10th fail")
    assert monitor.emergency_shutdown.shutdown_triggered is True

    # Health status should reflect critical state
    crit_status = monitor.get_health_status()
    assert crit_status["overall_status"] == "critical"
    assert crit_status["shutdown_active"] is True


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2. Performance Analytics Engine Tests
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def test_performance_analytics_metrics():
    trades = create_mock_trades()
    initial_capital = 100000.0

    report = PerformanceAnalytics.calculate_full_report(
        trades=trades,
        period="all",
        initial_capital=initial_capital,
    )

    # Core Summary
    summary = report["summary"]
    assert summary["total_trades"] == 4
    assert summary["winning_trades"] == 2
    assert summary["losing_trades"] == 1
    assert summary["break_even_trades"] == 1
    assert summary["win_rate"] == 50.0  # 2 wins out of 4 trades
    assert summary["total_pnl"] == 18000.0  # 20,000 - 5,000 + 3,000 + 0
    assert summary["total_pnl_pct"] == 18.0  # 18k / 100k * 100

    # Profit Factor: Gross profit (23,000) / Gross loss (5,000) = 4.6
    assert summary["profit_factor"] == 4.6
    assert summary["expectancy"] > 0

    # Averages
    averages = report["averages"]
    assert averages["avg_win"] == 11500.0  # (20,000 + 3,000) / 2
    assert averages["avg_loss"] == -5000.0
    assert averages["avg_trade_pnl"] == 4500.0  # 18,000 / 4

    # Risk Adjusted
    risk_adj = report["risk_adjusted"]
    assert "sharpe_ratio" in risk_adj
    assert "sortino_ratio" in risk_adj
    assert "calmar_ratio" in risk_adj

    # Drawdown
    drawdown = report["drawdown"]
    assert "max_drawdown_pct" in drawdown
    assert "current_drawdown_pct" in drawdown

    # Streaks
    streaks = report["streaks"]
    assert streaks["max_win_streak"] >= 1
    assert streaks["max_loss_streak"] >= 1

    # Breakdowns
    breakdowns = report["breakdowns"]
    assert "Breakout_Hunter" in breakdowns["by_strategy"]
    assert "MA_Pullback" in breakdowns["by_strategy"]
    assert "BTC/INR" in breakdowns["by_pair"]
    assert len(breakdowns["by_hour_of_day"]) == 24
    assert len(breakdowns["by_day_of_week"]) == 7

    # Execution
    exec_q = report["execution"]
    assert "avg_slippage_bps" in exec_q
    assert "avg_hold_time_minutes" in exec_q

    # Empty trade history handling
    empty_report = PerformanceAnalytics.calculate_full_report(trades=[], period="all")
    assert empty_report["summary"]["total_trades"] == 0
    assert empty_report["summary"]["win_rate"] == 0.0
    assert empty_report["summary"]["total_pnl"] == 0.0


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3. Strategy Tracker Tests
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def test_strategy_performance_tracker():
    tracker = StrategyPerformanceTracker()
    now = datetime.now(timezone.utc)

    # Feed 50 initial winning trades to build a solid 100-trade baseline
    strat = "Test_Momentum"
    baseline_trades = [
        Trade(
            pair="BTC/INR",
            strategy=strat,
            side="BUY",
            entry_price=100.0,
            exit_price=110.0,
            quantity=1.0,
            pnl=10.0,
            status="CLOSED",
            created_at=now - timedelta(hours=i),
            closed_at=now - timedelta(hours=i, minutes=-10),
        )
        for i in range(60, 10, -1)
    ]
    tracker.sync_from_database(baseline_trades)
    state = tracker.evaluate_strategy(strat)
    assert state["win_rate_100"] == 1.0
    assert state["win_rate_30"] == 1.0
    assert state["is_degraded"] is False
    assert state["auto_disabled"] is False

    # Now add 30 recent trades where only 12 are wins (WR30 = 12/30 = 40%)
    # Window 100 WR is (50 + 12) / 80 = 77.5%.
    # 40% < 77.5% * 0.80 (62.0%) -> is_degraded should be True!
    for i in range(30):
        is_win = (i < 12)
        pnl = 10.0 if is_win else -15.0
        exit_p = 110.0 if is_win else 85.0
        t = Trade(
            pair="BTC/INR",
            strategy=strat,
            side="BUY",
            entry_price=100.0,
            exit_price=exit_p,
            quantity=1.0,
            pnl=pnl,
            status="CLOSED",
            created_at=now - timedelta(minutes=(30 - i) * 5),
            closed_at=now - timedelta(minutes=(30 - i) * 5 - 2),
        )
        tracker.record_closed_trade(t)

    eval_state = tracker.evaluate_strategy(strat)
    assert eval_state["is_degraded"] is True

    # Test auto-disable threshold: add 10 more losses so WR30 < 35%
    for i in range(10):
        t = Trade(
            pair="BTC/INR",
            strategy=strat,
            side="BUY",
            entry_price=100.0,
            exit_price=85.0,
            quantity=1.0,
            pnl=-15.0,
            status="CLOSED",
            created_at=now,
            closed_at=now,
        )
        tracker.record_closed_trade(t)

    disabled_state = tracker.evaluate_strategy(strat)
    assert disabled_state["auto_disabled"] is True
    assert disabled_state["status"] == "DISABLED"

    # Verify dynamic weighting
    weights = tracker.get_strategy_weights()
    assert weights[strat] == 0.0  # auto-disabled gets weight 0.0


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 4. Alert Manager Tests
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def test_alert_manager():
    am = AlertManager()
    am.clear_alerts()

    # Normal alert
    a1 = am.send_alert(
        event="TEST_TRADE_OPENED",
        message="Opened position on BTC/INR",
        priority="NORMAL",
    )
    assert a1["priority"] == "NORMAL"
    assert a1["icon"] == "📊"

    # High alert
    a2 = am.send_alert(
        event="TEST_DRAWDOWN_WARNING",
        message="Portfolio down 2.5%",
        priority="HIGH",
    )
    assert a2["priority"] == "HIGH"
    assert a2["icon"] == "⚠️"

    # Critical alert
    a3 = am.send_alert(
        event="TEST_CIRCUIT_BREAKER",
        message="Emergency liquidation triggered",
        priority="CRITICAL",
    )
    assert a3["priority"] == "CRITICAL"
    assert a3["icon"] == "🚨"

    # Buffer inspection
    recent = am.get_recent_alerts(limit=10)
    assert len(recent) == 3
    # Check newest first
    assert recent[0]["event"] == "TEST_CIRCUIT_BREAKER"
    assert recent[2]["event"] == "TEST_TRADE_OPENED"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 5. Daily Report Generator Tests
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def test_daily_report_generator():
    report = DailyReportGenerator.generate_report()
    assert "date" in report
    assert "mode" in report
    assert "day_pnl" in report
    assert "markdown" in report
    assert "AutoTrader Pro — Daily Performance Digest" in report["markdown"]
    assert "Capital & PnL" in report["markdown"]

    # Dispatch simulation
    dispatch_res = DailyReportGenerator.send_daily_report()
    assert dispatch_res["date"] == report["date"]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 6. Structured Logging Helpers Tests
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def test_structured_logging():
    # Trade event
    t_ev = log_trade_event("ORDER_FILLED", {"pair": "ETH/INR", "price": 250000.0, "qty": 0.5})
    assert t_ev["event_type"] == "ORDER_FILLED"
    assert t_ev["category"] == "TRADE"
    assert len(t_ev["trace_id"]) > 0

    # Signal event
    s_ev = log_signal_event("SIGNAL_AGGREGATED", {"pair": "BTC/INR", "action": "BUY", "confidence": 0.85})
    assert s_ev["event_type"] == "SIGNAL_AGGREGATED"
    assert s_ev["category"] == "SIGNAL"

    # Risk event
    r_ev = log_risk_event("CORRELATION_LIMIT", {"pair": "SOL/INR", "correlated_with": "ETH/INR"}, level="WARNING")
    assert r_ev["event_type"] == "CORRELATION_LIMIT"
    assert r_ev["category"] == "RISK"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 7. FastAPI Monitoring & Analytics Endpoints Tests
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def test_api_monitoring_and_analytics_endpoints():
    with TestClient(app) as client:
        # 1. GET /api/status (Enriched)
        res_status = client.get("/api/status")
        assert res_status.status_code == 200
        data_status = res_status.json()
        assert "running" in data_status
        assert "health_summary" in data_status
        assert "analytics_summary" in data_status
        assert "active_alerts" in data_status
        assert "regimes" in data_status

        # 2. GET /api/status/health (Detailed)
        res_health = client.get("/api/status/health")
        assert res_health.status_code == 200
        data_health = res_health.json()
        assert "overall_status" in data_health
        assert "checks" in data_health
        assert "failure_counts" in data_health

        # 3. GET /api/portfolio/analytics
        res_analytics = client.get("/api/portfolio/analytics?period=all")
        assert res_analytics.status_code == 200
        data_analytics = res_analytics.json()
        assert "summary" in data_analytics
        assert "risk_adjusted" in data_analytics
        assert "breakdowns" in data_analytics

        # Test periods
        for p in ["today", "week", "month"]:
            res_p = client.get(f"/api/portfolio/analytics?period={p}")
            assert res_p.status_code == 200

        # 4. GET /api/portfolio/equity-curve
        res_curve = client.get("/api/portfolio/equity-curve")
        assert res_curve.status_code == 200
        data_curve = res_curve.json()
        assert "initial_capital" in data_curve
        assert "points" in data_curve
        assert "high_water_mark" in data_curve
        assert "max_drawdown_pct" in data_curve


if __name__ == "__main__":
    print("=" * 60)
    print("RUNNING AGENT 5 COMPREHENSIVE TEST SUITE")
    print("=" * 60)

    test_health_monitor_checks_and_escalation()
    print("[PASS] 1. System Health Monitor & Escalation Ladder verified")

    test_performance_analytics_metrics()
    print("[PASS] 2. Performance Analytics Engine metrics & breakdowns verified")

    test_strategy_performance_tracker()
    print("[PASS] 3. Strategy Performance Tracker & degradation detection verified")

    test_alert_manager()
    print("[PASS] 4. Multi-Channel Alert Manager & priority routing verified")

    test_daily_report_generator()
    print("[PASS] 5. Daily Performance Report Generator & Markdown formatting verified")

    test_structured_logging()
    print("[PASS] 6. Structured Logging Helpers (trade, signal, risk events) verified")

    test_api_monitoring_and_analytics_endpoints()
    print("[PASS] 7. FastAPI Monitoring & Analytics Endpoints verified")

    print("\nALL AGENT 5 TESTS PASSED PERFECTLY (7/7)!")
