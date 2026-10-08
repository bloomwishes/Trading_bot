"""
AutoTrader Pro - Technical Indicator Calculation Library
========================================================
Provides all technical indicator calculations used by trading strategies.
Uses pandas and the `ta` library for robust, battle-tested computations.
All functions expect a DataFrame with columns: [timestamp, open, high, low, close, volume].
"""

import pandas as pd
import numpy as np
from ta.momentum import RSIIndicator, StochRSIIndicator
from ta.volatility import BollingerBands, AverageTrueRange
from ta.trend import EMAIndicator, SMAIndicator, MACD

from backend.utils.logger import bot_logger


def _validate_dataframe(df: pd.DataFrame, min_rows: int = 1) -> bool:
    """Validate that the DataFrame has the required columns and enough data."""
    required_columns = {"open", "high", "low", "close", "volume"}
    if df is None or df.empty:
        bot_logger.warning("Indicator calculation received empty DataFrame")
        return False
    missing = required_columns - set(df.columns)
    if missing:
        bot_logger.warning(f"DataFrame missing required columns: {missing}")
        return False
    if len(df) < min_rows:
        bot_logger.warning(
            f"DataFrame has {len(df)} rows, need at least {min_rows}"
        )
        return False
    return True


def calculate_ema(df: pd.DataFrame, period: int) -> pd.Series:
    """
    Calculate Exponential Moving Average.

    Args:
        df: OHLCV DataFrame.
        period: EMA lookback period.

    Returns:
        pd.Series with EMA values. Returns empty Series on error.
    """
    if not _validate_dataframe(df, min_rows=period):
        return pd.Series(dtype=float)
    try:
        ema = EMAIndicator(close=df["close"], window=period, fillna=False)
        return ema.ema_indicator()
    except Exception as e:
        bot_logger.error(f"EMA({period}) calculation failed: {e}")
        return pd.Series(dtype=float)


def calculate_sma(df: pd.DataFrame, period: int) -> pd.Series:
    """
    Calculate Simple Moving Average.

    Args:
        df: OHLCV DataFrame.
        period: SMA lookback period.

    Returns:
        pd.Series with SMA values. Returns empty Series on error.
    """
    if not _validate_dataframe(df, min_rows=period):
        return pd.Series(dtype=float)
    try:
        sma = SMAIndicator(close=df["close"], window=period, fillna=False)
        return sma.sma_indicator()
    except Exception as e:
        bot_logger.error(f"SMA({period}) calculation failed: {e}")
        return pd.Series(dtype=float)


def calculate_rsi(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Calculate Relative Strength Index.

    Args:
        df: OHLCV DataFrame.
        period: RSI lookback period (default 14).

    Returns:
        pd.Series with RSI values (0-100). Returns empty Series on error.
    """
    if not _validate_dataframe(df, min_rows=period + 1):
        return pd.Series(dtype=float)
    try:
        rsi = RSIIndicator(close=df["close"], window=period, fillna=False)
        return rsi.rsi()
    except Exception as e:
        bot_logger.error(f"RSI({period}) calculation failed: {e}")
        return pd.Series(dtype=float)


def calculate_stoch_rsi(
    df: pd.DataFrame,
    period: int = 14,
    smooth_k: int = 3,
    smooth_d: int = 3,
) -> tuple:
    """
    Calculate Stochastic RSI.

    Args:
        df: OHLCV DataFrame.
        period: RSI lookback period.
        smooth_k: %K smoothing period.
        smooth_d: %D smoothing period.

    Returns:
        Tuple of (k_series, d_series). Each is a pd.Series (0-100 scale).
        Returns (empty Series, empty Series) on error.
    """
    empty = (pd.Series(dtype=float), pd.Series(dtype=float))
    if not _validate_dataframe(df, min_rows=period + smooth_k + smooth_d):
        return empty
    try:
        stoch_rsi = StochRSIIndicator(
            close=df["close"],
            window=period,
            smooth1=smooth_k,
            smooth2=smooth_d,
            fillna=False,
        )
        k_series = stoch_rsi.stochrsi_k() * 100  # ta returns 0-1, scale to 0-100
        d_series = stoch_rsi.stochrsi_d() * 100
        return (k_series, d_series)
    except Exception as e:
        bot_logger.error(f"StochRSI({period}) calculation failed: {e}")
        return empty


def calculate_bollinger_bands(
    df: pd.DataFrame, period: int = 20, std_dev: int = 2
) -> tuple:
    """
    Calculate Bollinger Bands.

    Args:
        df: OHLCV DataFrame.
        period: Lookback period for the middle band (SMA).
        std_dev: Number of standard deviations for upper/lower bands.

    Returns:
        Tuple of (upper, middle, lower, bandwidth) — each a pd.Series.
        bandwidth = (upper - lower) / middle — a normalized measure of volatility.
        Returns four empty Series on error.
    """
    empty = (
        pd.Series(dtype=float),
        pd.Series(dtype=float),
        pd.Series(dtype=float),
        pd.Series(dtype=float),
    )
    if not _validate_dataframe(df, min_rows=period):
        return empty
    try:
        bb = BollingerBands(
            close=df["close"],
            window=period,
            window_dev=std_dev,
            fillna=False,
        )
        upper = bb.bollinger_hband()
        middle = bb.bollinger_mavg()
        lower = bb.bollinger_lband()
        # Bandwidth: (upper - lower) / middle
        bandwidth = bb.bollinger_wband()
        return (upper, middle, lower, bandwidth)
    except Exception as e:
        bot_logger.error(f"BollingerBands({period},{std_dev}) calculation failed: {e}")
        return empty


def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Calculate Average True Range.

    Args:
        df: OHLCV DataFrame.
        period: ATR lookback period.

    Returns:
        pd.Series with ATR values. Returns empty Series on error.
    """
    if not _validate_dataframe(df, min_rows=period + 1):
        return pd.Series(dtype=float)
    try:
        atr = AverageTrueRange(
            high=df["high"],
            low=df["low"],
            close=df["close"],
            window=period,
            fillna=False,
        )
        return atr.average_true_range()
    except Exception as e:
        bot_logger.error(f"ATR({period}) calculation failed: {e}")
        return pd.Series(dtype=float)


def calculate_volume_sma(df: pd.DataFrame, period: int = 20) -> pd.Series:
    """
    Calculate Simple Moving Average of volume.

    Args:
        df: OHLCV DataFrame.
        period: Volume SMA lookback period.

    Returns:
        pd.Series with volume SMA values. Returns empty Series on error.
    """
    if not _validate_dataframe(df, min_rows=period):
        return pd.Series(dtype=float)
    try:
        return df["volume"].rolling(window=period, min_periods=period).mean()
    except Exception as e:
        bot_logger.error(f"Volume SMA({period}) calculation failed: {e}")
        return pd.Series(dtype=float)


def calculate_macd(
    df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9
) -> tuple:
    """
    Calculate MACD (Moving Average Convergence Divergence).

    Args:
        df: OHLCV DataFrame.
        fast: Fast EMA period.
        slow: Slow EMA period.
        signal: Signal line EMA period.

    Returns:
        Tuple of (macd_line, signal_line, histogram) — each a pd.Series.
        Returns three empty Series on error.
    """
    empty = (
        pd.Series(dtype=float),
        pd.Series(dtype=float),
        pd.Series(dtype=float),
    )
    if not _validate_dataframe(df, min_rows=slow + signal):
        return empty
    try:
        macd_ind = MACD(
            close=df["close"],
            window_fast=fast,
            window_slow=slow,
            window_sign=signal,
            fillna=False,
        )
        macd_line = macd_ind.macd()
        signal_line = macd_ind.macd_signal()
        histogram = macd_ind.macd_diff()
        return (macd_line, signal_line, histogram)
    except Exception as e:
        bot_logger.error(f"MACD({fast},{slow},{signal}) calculation failed: {e}")
        return empty


def detect_swing_highs(df: pd.DataFrame, window: int = 5) -> list:
    """
    Detect swing highs in price data.

    A swing high is a bar whose high is greater than the highs of `window` bars
    on both sides of it.

    Args:
        df: OHLCV DataFrame.
        window: Number of bars on each side to compare.

    Returns:
        List of (index, price) tuples representing swing highs,
        ordered chronologically. Returns empty list on error.
    """
    if not _validate_dataframe(df, min_rows=window * 2 + 1):
        return []
    try:
        highs = df["high"].values
        swing_highs = []
        for i in range(window, len(highs) - window):
            is_swing = True
            for j in range(1, window + 1):
                if highs[i] <= highs[i - j] or highs[i] <= highs[i + j]:
                    is_swing = False
                    break
            if is_swing:
                idx = df.index[i]
                swing_highs.append((idx, float(highs[i])))
        return swing_highs
    except Exception as e:
        bot_logger.error(f"Swing high detection failed: {e}")
        return []


def detect_swing_lows(df: pd.DataFrame, window: int = 5) -> list:
    """
    Detect swing lows in price data.

    A swing low is a bar whose low is less than the lows of `window` bars
    on both sides of it.

    Args:
        df: OHLCV DataFrame.
        window: Number of bars on each side to compare.

    Returns:
        List of (index, price) tuples representing swing lows,
        ordered chronologically. Returns empty list on error.
    """
    if not _validate_dataframe(df, min_rows=window * 2 + 1):
        return []
    try:
        lows = df["low"].values
        swing_lows = []
        for i in range(window, len(lows) - window):
            is_swing = True
            for j in range(1, window + 1):
                if lows[i] >= lows[i - j] or lows[i] >= lows[i + j]:
                    is_swing = False
                    break
            if is_swing:
                idx = df.index[i]
                swing_lows.append((idx, float(lows[i])))
        return swing_lows
    except Exception as e:
        bot_logger.error(f"Swing low detection failed: {e}")
        return []
