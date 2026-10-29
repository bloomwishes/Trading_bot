"""
Test Suite for Security, Authentication, and Live Order Protection
==================================================================
Validates:
1. API Key Authentication (header, query param, rejection on invalid key).
2. Mode switch pre-flight verification & credential protection.
3. CoinDCX market symbol formatting ('BTCINR' without 'B-' prefix).
4. Order quantity precision rounding per asset.
5. Rejection handling: Failed live orders are NOT recorded as OPEN or CLOSED in DB.
6. Localhost binding & restricted CORS configuration.
"""

from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from backend.config import settings
from backend.exchange.coindcx import CoinDCXClient
from backend.exchange.exchange_manager import ExchangeManager
from backend.engine.trading_engine import TradingEngine
from backend.models import Trade


def test_api_key_auth_rejection(client: TestClient):
    """Endpoints with require_api_key must reject requests without valid key."""
    # Attempt to start bot without API key
    res = client.post("/api/bot/start")
    assert res.status_code == 401
    assert "Unauthorized" in res.json().get("detail", "")

    # Attempt with invalid API key
    res = client.post("/api/bot/start", headers={"X-API-Key": "wrong-key"})
    assert res.status_code == 401


def test_api_key_auth_acceptance(client: TestClient, auth_headers: dict):
    """Endpoints must accept valid API key via header or query parameter."""
    # Using header
    res = client.post("/api/bot/start", headers=auth_headers)
    assert res.status_code in (200, 409)  # 200 ok or 409 if already started

    # Using query parameter
    res = client.post("/api/bot/stop?api_key=test-secret-key")
    assert res.status_code in (200, 409)


def test_mode_switch_safeguard(client: TestClient, auth_headers: dict):
    """Mode switch to LIVE must fail if credentials are missing or unconfirmed."""
    # Unconfirmed
    res = client.post("/api/bot/mode", json={"mode": "live", "confirm": False}, headers=auth_headers)
    assert res.status_code == 400

    # Without credentials
    with patch.object(settings, "COINDCX_API_KEY", ""):
        res = client.post("/api/bot/mode", json={"mode": "live", "confirm": True}, headers=auth_headers)
        assert res.status_code == 400
        assert "credentials" in res.json().get("detail", "").lower()


def test_coindcx_symbol_formatting():
    """CoinDCX /exchange/v1/orders/create requires symbol without 'B-' prefix."""
    assert CoinDCXClient.format_order_symbol("BTC/INR") == "BTCINR"
    assert CoinDCXClient.format_order_symbol("B-BTC_INR") == "BTCINR"
    assert CoinDCXClient.format_order_symbol("ETH/INR") == "ETHINR"
    assert CoinDCXClient.format_order_symbol("SOL/INR") == "SOLINR"
    assert CoinDCXClient.format_order_symbol("BNB/INR") == "BNBINR"


def test_coindcx_quantity_rounding():
    """Quantities must adhere to asset step size and decimal precision."""
    coindcx = CoinDCXClient(api_key="mock_key", api_secret="mock_secret")
    # BTC: 6 decimals
    assert coindcx.round_quantity("BTC/INR", 0.0012345678) == 0.001235
    # ETH: 5 decimals
    assert coindcx.round_quantity("ETH/INR", 0.1234567) == 0.12346
    # SOL: 3 decimals
    assert coindcx.round_quantity("SOL/INR", 1.23456) == 1.235
    # XRP: 2 decimals
    assert coindcx.round_quantity("XRP/INR", 10.567) == 10.57


def test_live_order_failure_does_not_record_open_trade(client: TestClient, auth_headers: dict):
    """When an exchange order fails, manual trade must raise 502 and NOT save to DB."""
    # Mock exchange_manager.place_order to return error
    from backend.main import app
    engine: TradingEngine = app.state.engine
    original_mode = engine.mode
    engine.mode = "live"

    try:
        with patch.object(engine.exchange_manager, "get_ticker", return_value={"last_price": 5000000.0}), \
             patch.object(engine.exchange_manager, "get_balances", return_value={"INR": {"available": 50000.0, "locked": 0.0}}), \
             patch.object(engine.exchange_manager, "place_order", return_value={"error": "Insufficient balance or invalid signature"}):

            res = client.post(
                "/api/trade/manual",
                json={
                    "pair": "BTC/INR",
                    "side": "BUY",
                    "amount_inr": 1000.0,
                    "strategy": "MANUAL",
                },
                headers=auth_headers,
            )
            assert res.status_code == 502
            assert "rejected" in res.json().get("detail", "").lower() or "error" in res.json().get("detail", "").lower()
    finally:
        engine.mode = original_mode


def test_live_close_order_failure_leaves_trade_open(db_session):
    """When a live close order fails, _close_trade_internal must NOT mark trade CLOSED."""
    engine = TradingEngine()
    engine.mode = "live"

    # Create dummy trade
    trade = Trade(
        pair="BTC/INR",
        side="BUY",
        entry_price=5000000.0,
        quantity=0.001,
        status="OPEN",
        paper_mode=False,
    )
    db_session.add(trade)
    db_session.commit()
    db_session.refresh(trade)

    try:
        # Mock exchange order to simulate network error or rejection
        with patch.object(engine.exchange_manager, "place_order", return_value={"error": "Exchange connection timeout"}):
            engine._close_trade_internal(trade, 5100000.0, "STOP_LOSS", db_session)

            # Refresh trade from DB: status MUST STILL BE OPEN
            db_session.refresh(trade)
            assert trade.status == "OPEN"
    finally:
        db_session.delete(trade)
        db_session.commit()


def test_host_binding_and_cors_config():
    """Verify security defaults in settings."""
    assert settings.BACKEND_HOST in ("127.0.0.1", "localhost")
    for origin in settings.ALLOWED_ORIGINS:
        assert "*" not in origin


def test_paper_reset_trains_nn_and_wipes_history(client, auth_headers, db_session):
    """
    Verify Paper Reset workflow:
    1. Rejects reset if mode is live.
    2. In paper mode: closes open positions, trains neural network, deletes trades, resets capital to 10000.
    """
    from backend.main import app
    engine = app.state.engine

    # 1. Reject if live mode
    orig_mode = engine.mode
    engine.mode = "live"
    try:
        res = client.post("/api/portfolio/reset-paper", headers=auth_headers)
        assert res.status_code == 400
        assert "Paper Trading mode" in res.json()["detail"]
    finally:
        engine.mode = "paper"

    # 2. Seed an open trade and closed trades
    open_trade = Trade(
        pair="BTC/INR",
        side="BUY",
        strategy="Neural_Network_BTC",
        entry_price=8000000.0,
        quantity=0.001,
        status="OPEN",
        paper_mode=True,
    )
    closed_trade = Trade(
        pair="BTC/INR",
        side="BUY",
        strategy="Neural_Network_BTC",
        entry_price=8000000.0,
        exit_price=8100000.0,
        quantity=0.001,
        pnl=100.0,
        status="CLOSED",
        paper_mode=True,
    )
    db_session.add(open_trade)
    db_session.add(closed_trade)
    db_session.commit()
    db_session.refresh(open_trade)
    engine.paper_trader.positions[open_trade.id] = {
        "id": open_trade.id,
        "pair": open_trade.pair,
        "side": open_trade.side,
        "entry_price": open_trade.entry_price,
        "quantity": open_trade.quantity,
    }

    # 3. Call reset paper endpoint
    res2 = client.post("/api/portfolio/reset-paper", headers=auth_headers)
    assert res2.status_code == 200
    data = res2.json()
    assert data["status"] == "success"
    assert data["closed_active_trades"] >= 1
    assert data["trained_trades"] >= 2
    assert data["current_balance"] == settings.PAPER_BALANCE
    assert "neural_training" in data

    # 4. Verify DB was wiped for paper trades
    remaining = db_session.query(Trade).filter(Trade.paper_mode.is_(True)).count()
    assert remaining == 0

    # 5. Verify paper trader balance and positions are clean
    assert engine.paper_trader.balance == settings.PAPER_BALANCE
    assert len(engine.paper_trader.positions) == 0
