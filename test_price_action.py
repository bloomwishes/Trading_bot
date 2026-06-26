import sys
import io
# Force UTF-8 encoding for stdout on Windows console
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from pathlib import Path
import pandas as pd
import numpy as np

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

    strategy = PriceActionStrategy()
    print(f"Strategy Name: {strategy.name}")
    print(f"Default Parameters: {strategy.get_config()}")

    # ----------------------------------------------------
    # TEST 1: Bullish Pin Bar at Support
    # ----------------------------------------------------
    print("\n--- Test 1: Bullish Pin Bar near Support ---")
    data = create_base_mock_data()
    # Modify the last candle to be a Bullish Pin Bar near support (100.0)
    data.append({
        "timestamp": 32,
        "open": 100.5,
        "high": 100.9,
        "low": 99.8,       # Deep tail down to support
        "close": 100.8,
        "volume": 1500
    })
    df = pd.DataFrame(data)
    signal = strategy.analyze(df, "BTC/INR")
    if signal and signal.action == "BUY":
        print(f"[OK] SUCCESS: Generated BUY signal! Reason: {signal.reason}")
        print(f"Metadata: {signal.metadata}")
    else:
        print("[FAIL] FAIL: Did not generate expected BUY signal.")

    # ----------------------------------------------------
    # TEST 2: Bullish Engulfing at Support
    # ----------------------------------------------------
    print("\n--- Test 2: Bullish Engulfing near Support ---")
    data = create_base_mock_data()
    # Modify last two candles to form an engulfing pattern near support (100.0)
    data[-1] = {
        "timestamp": 30,
        "open": 100.8,
        "high": 101.0,
        "low": 100.2,
        "close": 100.3,
        "volume": 1000
    }
    data.append({
        "timestamp": 31,
        "open": 100.2,     # Opens lower than prev close (100.3)
        "high": 101.1,
        "low": 100.1,
        "close": 100.9,    # Closes higher than prev open (100.8)
        "volume": 1500
    })
    df = pd.DataFrame(data)
    signal = strategy.analyze(df, "BTC/INR")
    if signal and signal.action == "BUY":
        print(f"[OK] SUCCESS: Generated BUY signal! Reason: {signal.reason}")
        print(f"Metadata: {signal.metadata}")
    else:
        print("[FAIL] FAIL: Did not generate expected BUY signal.")

    # ----------------------------------------------------
    # TEST 3: Bearish Pin Bar at Resistance
    # ----------------------------------------------------
    print("\n--- Test 3: Bearish Pin Bar near Resistance ---")
    data = create_base_mock_data()
    # Modify the last candle to be a Bearish Pin Bar near resistance (200.0)
    data.append({
        "timestamp": 32,
        "open": 199.5,
        "high": 200.2,      # Tail shoots up to resistance
        "low": 199.1,
        "close": 199.2,
        "volume": 1500
    })
    df = pd.DataFrame(data)
    signal = strategy.analyze(df, "BTC/INR")
    if signal and signal.action == "SELL":
        print(f"[OK] SUCCESS: Generated SELL signal! Reason: {signal.reason}")
        print(f"Metadata: {signal.metadata}")
    else:
        print("[FAIL] FAIL: Did not generate expected SELL signal.")

    # ----------------------------------------------------
    # TEST 4: No Signal
    # ----------------------------------------------------
    print("\n--- Test 4: Flat market (No Signal) ---")
    data = create_base_mock_data()
    # Latest candle has normal size in the middle of range (150.0)
    data.append({
        "timestamp": 32,
        "open": 150.0,
        "high": 152.0,
        "low": 149.0,
        "close": 151.0,
        "volume": 1000
    })
    df = pd.DataFrame(data)
    signal = strategy.analyze(df, "BTC/INR")
    if signal is None:
        print("[OK] SUCCESS: Correctly ignored flat market.")
    else:
        print(f"[FAIL] FAIL: Generated unexpected signal: {signal.action}")

if __name__ == "__main__":
    run_test()
