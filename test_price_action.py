import sys
import io
# Force UTF-8 encoding for stdout on Windows console
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from pathlib import Path
import pandas as pd
from unittest.mock import patch, MagicMock
import requests

# Adjust path to import backend modules
sys.path.append(str(Path(__file__).resolve().parent))

from backend.engine.price_action import PriceActionStrategy

def create_base_mock_data(lookback=30, support=100.0, resistance=200.0):
    """
    Creates lookback + 2 candles. Establishing support and resistance in historical bars.
    """
    data = []
    # Generate historical candles (lookback + 1 bars)
    for i in range(lookback + 1):
        # Establish support and resistance boundaries in history
        if i == 5:
            low = support
            high = support + 10.0
        elif i == 15:
            low = resistance - 10.0
            high = resistance
        else:
            low = 120.0
            high = 180.0
        
        open_val = (low + high) / 2
        close_val = open_val + 1.0
        data.append({
            "timestamp": i,
            "open": open_val,
            "high": high,
            "low": low,
            "close": close_val,
            "volume": 1000
        })
    return data

def run_test():
    print("==================================================")
    print("   Running Price Action Strategy Diagnostics      ")
    print("==================================================")

    # ----------------------------------------------------
    # TEST 1: Base Pattern Detection (ai_confirm = False)
    # ----------------------------------------------------
    print("\n--- Test 1: Base Pattern Detection (AI Confirm = False) ---")
    strategy_no_ai = PriceActionStrategy({"ai_confirm": False})

    # A. Bullish Pin Bar near Support
    data = create_base_mock_data()
    data.append({
        "timestamp": 32,
        "open": 100.5,
        "high": 100.9,
        "low": 99.8,
        "close": 100.8,
        "volume": 1500
    })
    df = pd.DataFrame(data)
    signal = strategy_no_ai.analyze(df, "BTC/INR")
    if signal and signal.action == "BUY":
        print("[OK] Bullish Pin Bar: Generated BUY signal without AI.")
    else:
        print("[FAIL] Bullish Pin Bar: Failed to generate BUY signal.")

    # B. Bearish Pin Bar near Resistance
    data = create_base_mock_data()
    data.append({
        "timestamp": 32,
        "open": 199.5,
        "high": 200.2,
        "low": 199.1,
        "close": 199.2,
        "volume": 1500
    })
    df = pd.DataFrame(data)
    signal = strategy_no_ai.analyze(df, "BTC/INR")
    if signal and signal.action == "SELL":
        print("[OK] Bearish Pin Bar: Generated SELL signal without AI.")
    else:
        print("[FAIL] Bearish Pin Bar: Failed to generate SELL signal.")

    # C. Flat market (No Signal)
    data = create_base_mock_data()
    data.append({
        "timestamp": 32,
        "open": 150.0,
        "high": 152.0,
        "low": 149.0,
        "close": 151.0,
        "volume": 1000
    })
    df = pd.DataFrame(data)
    signal = strategy_no_ai.analyze(df, "BTC/INR")
    if signal is None:
        print("[OK] Flat Market: Correctly ignored.")
    else:
        print(f"[FAIL] Flat Market: Unexpectedly generated {signal.action}.")


    # ----------------------------------------------------
    # TEST 2: AI Approval Gate - APPROVED
    # ----------------------------------------------------
    print("\n--- Test 2: AI Approval Gate - Approved ---")
    strategy_ai = PriceActionStrategy({"ai_confirm": True})

    # Prepare Bullish Pin Bar setup
    data = create_base_mock_data()
    data.append({
        "timestamp": 32,
        "open": 100.5,
        "high": 100.9,
        "low": 99.8,
        "close": 100.8,
        "volume": 1500
    })
    df = pd.DataFrame(data)

    # Mock Ollama responding with approval
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "response": '{"approved": true, "reason": "strong reversal shape at support"}'
    }

    with patch("requests.post", return_value=mock_resp) as mock_post:
        signal = strategy_ai.analyze(df, "BTC/INR")
        mock_post.assert_called_once()
        if signal and signal.action == "BUY":
            print("[OK] AI Approved: Correctly executed BUY signal.")
            print(f"     Reason: {signal.reason}")
        else:
            print("[FAIL] AI Approved: Failed to generate approved BUY signal.")


    # ----------------------------------------------------
    # TEST 3: AI Approval Gate - REJECTED
    # ----------------------------------------------------
    print("\n--- Test 3: AI Approval Gate - Rejected ---")
    
    # Mock Ollama responding with rejection
    mock_resp_reject = MagicMock()
    mock_resp_reject.status_code = 200
    mock_resp_reject.json.return_value = {
        "response": '{"approved": false, "reason": "volume too low for sustainable bounce"}'
    }

    with patch("requests.post", return_value=mock_resp_reject) as mock_post:
        signal = strategy_ai.analyze(df, "BTC/INR")
        mock_post.assert_called_once()
        if signal is None:
            print("[OK] AI Rejected: Correctly suppressed the BUY trade.")
        else:
            print(f"[FAIL] AI Rejected: Generated unexpected {signal.action} signal anyway.")


    # ----------------------------------------------------
    # TEST 4: AI Approval Gate - OFFLINE (Fail Secure)
    # ----------------------------------------------------
    print("\n--- Test 4: AI Approval Gate - Offline (Fail Secure) ---")
    
    # Mock requests throwing connection error (server offline)
    with patch("requests.post", side_effect=requests.exceptions.ConnectionError("Ollama server unreachable")) as mock_post:
        signal = strategy_ai.analyze(df, "BTC/INR")
        # Should call twice: primary model, then fallback model
        if mock_post.call_count == 2:
            print("[OK] AI Offline: Checked both primary and fallback models.")
        else:
            print(f"[FAIL] AI Offline: Call count was {mock_post.call_count} instead of 2.")

        if signal is None:
            print("[OK] AI Offline: Correctly suppressed trade (fail-secure).")
        else:
            print(f"[FAIL] AI Offline: Generated trade despite connection failure.")


    # ----------------------------------------------------
    # TEST 5: AI Approval Gate - Primary Offline, Fallback Approves
    # ----------------------------------------------------
    print("\n--- Test 5: AI Approval Gate - Primary Offline, Fallback Approves ---")
    
    # Define side effect to raise error on first call, return response on second
    def post_side_effect(*args, **kwargs):
        json_payload = kwargs.get("json", {})
        model_requested = json_payload.get("model")
        
        if model_requested == strategy_ai.params["model"]:
            # Primary model offline
            raise requests.exceptions.ConnectionError("Primary model offline")
        elif model_requested == strategy_ai.params["fallback_model"]:
            # Fallback model online
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = {
                "response": '{"approved": true, "reason": "fallback approved: bullish engulfing near key level"}'
            }
            return resp
        else:
            raise ValueError(f"Unexpected model queried: {model_requested}")

    with patch("requests.post", side_effect=post_side_effect) as mock_post:
        signal = strategy_ai.analyze(df, "BTC/INR")
        if mock_post.call_count == 2:
            print("[OK] AI Fallback: Correctly fell back from primary to secondary model.")
        else:
            print(f"[FAIL] AI Fallback: Call count was {mock_post.call_count} instead of 2.")

        if signal and signal.action == "BUY":
            print("[OK] AI Fallback: Correctly generated BUY signal from fallback model.")
            print(f"     Reason: {signal.reason}")
        else:
            print("[FAIL] AI Fallback: Failed to generate signal.")

if __name__ == "__main__":
    run_test()
