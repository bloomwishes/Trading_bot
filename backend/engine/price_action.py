"""
AutoTrader Pro - Price Action Strategy
=======================================
Strategy 5: Uses pure price action (candlestick patterns + support/resistance)
to generate high-probability reversal signals.

Optional AI Approval Gate:
  If enabled, queries the local Ollama LLM to review the candlestick pattern
  and verify the setup before executing the trade.
"""

import re
from typing import Optional
import pandas as pd
import requests
from backend.engine.strategy_base import StrategyBase, StrategySignal
from backend.utils.logger import bot_logger
from backend.utils.helpers import safe_json_loads

class PriceActionStrategy(StrategyBase):
    """
    Price Action Strategy - trade key levels using candlestick reversals.
    """

    DEFAULT_PARAMS = {
        "lookback": 30,             # Candles to calculate support/resistance
        "proximity_pct": 1.0,       # Max distance from S/R to validate setups
        "profit_target_pct": 2.0,   # Used in signal metadata
        "ai_confirm": True,         # Query Ollama for validation before trading
        "model": "llama3",
        "fallback_model": "mistral",
        "ollama_url": "http://localhost:11434",
        "timeout": 30,
        "temperature": 0.2
    }

    def __init__(self, params: dict = None):
        merged = {**self.DEFAULT_PARAMS, **(params or {})}
        super().__init__(name="Price_Action", default_params=merged)

    def _call_ollama_for_approval(
        self,
        pair: str,
        action: str,
        pattern_name: str,
        support_level: float,
        resistance_level: float,
        close_p: float,
        candles_summary: str,
        model: str
    ) -> Optional[bool]:
        """
        Query Ollama model to approve or reject the trade based on price action.
        Returns True if approved, False if rejected, None if request failed.
        """
        url = f"{self.params['ollama_url']}/api/generate"
        prompt = (
            "You are an expert crypto chart analyst.\n"
            f"I have detected a {pattern_name} near support/resistance boundaries for {pair}.\n\n"
            "Details:\n"
            f"- Action: {action}\n"
            f"- Candlestick Pattern: {pattern_name}\n"
            f"- Support Level: {support_level:.2f}\n"
            f"- Resistance Level: {resistance_level:.2f}\n"
            f"- Current Price: {close_p:.2f}\n\n"
            "Recent candles (OHLCV):\n"
            f"{candles_summary}\n\n"
            f"Verify if this candlestick pattern is valid and represents a high-probability reversal. "
            f"Should we execute this {action} trade?\n"
            "Reply ONLY with valid JSON — no other text, no markdown code blocks:\n"
            '{"approved": true/false, "reason": "brief explanation of your decision"}'
        )

        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": self.params["temperature"],
            },
        }

        try:
            resp = requests.post(url, json=payload, timeout=self.params["timeout"])
            resp.raise_for_status()
            response_text = resp.json().get("response", "").strip()

            # Attempt parsing JSON directly or extract it from text
            parsed = safe_json_loads(response_text)
            if not parsed:
                # Try finding JSON within markdown code blocks or brackets
                code_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", response_text, re.DOTALL)
                if code_match:
                    parsed = safe_json_loads(code_match.group(1))
                else:
                    json_match = re.search(r"\{[^{}]*\}", response_text, re.DOTALL)
                    if json_match:
                        parsed = safe_json_loads(json_match.group(0))

            if parsed and isinstance(parsed, dict) and "approved" in parsed:
                approved = bool(parsed["approved"])
                reason = parsed.get("reason", "No reason provided")
                bot_logger.info(
                    f"[Price_Action] AI Agent [{model}] validation result: "
                    f"approved={approved}, reason: {reason}"
                )
                return approved

            bot_logger.warning(
                f"[Price_Action] Failed to parse AI Agent approval response: {response_text[:150]}"
            )
            return None

        except requests.exceptions.RequestException as e:
            bot_logger.warning(f"[Price_Action] Ollama approval request failed for {model}: {e}")
            return None

    def analyze(self, df: pd.DataFrame, pair: str) -> Optional[StrategySignal]:
        """
        Analyze candle data for price action setups.

        Args:
            df: OHLCV DataFrame.
            pair: Trading pair string.

        Returns:
            StrategySignal if setup triggers, else None.
        """
        lookback = int(self.params["lookback"])
        proximity_pct = float(self.params["proximity_pct"])

        # We need at least lookback + 2 candles
        if df is None or len(df) < lookback + 2:
            return None

        try:
            # 1. Compute Support & Resistance levels over lookback window (excluding current candle)
            historical_df = df.iloc[-lookback-1:-1]
            support_level = float(historical_df["low"].min())
            resistance_level = float(historical_df["high"].max())

            # 2. Extract current and previous candle metrics
            latest = df.iloc[-1]
            prev = df.iloc[-2]

            open_p = float(latest["open"])
            high_p = float(latest["high"])
            low_p = float(latest["low"])
            close_p = float(latest["close"])
            range_p = high_p - low_p

            prev_open = float(prev["open"])
            prev_close = float(prev["close"])

            if range_p <= 0:
                return None

            body_p = abs(close_p - open_p)
            upper_shadow = high_p - max(open_p, close_p)
            lower_shadow = min(open_p, close_p) - low_p

            # 3. Detect Candlestick Patterns
            # Bullish Pin Bar: Small body at the top, long lower tail
            is_bull_pin = (
                body_p <= range_p * 0.3 and
                lower_shadow >= range_p * 0.6 and
                upper_shadow <= range_p * 0.15
            )

            # Bearish Pin Bar: Small body at the bottom, long upper tail
            is_bear_pin = (
                body_p <= range_p * 0.3 and
                upper_shadow >= range_p * 0.6 and
                lower_shadow <= range_p * 0.15
            )

            # Bullish Engulfing: Current bullish body fully engulfs previous bearish body
            is_bull_engulfing = (
                prev_close < prev_open and
                close_p > open_p and
                open_p <= prev_close and
                close_p >= prev_open
            )

            # Bearish Engulfing: Current bearish body fully engulfs previous bullish body
            is_bear_engulfing = (
                prev_close > prev_open and
                close_p < open_p and
                open_p >= prev_close and
                close_p <= prev_open
            )

            # 4. Check proximity to S/R levels
            # Support proximity check
            near_support = close_p <= support_level * (1.0 + proximity_pct / 100.0)
            # Resistance proximity check
            near_resistance = close_p >= resistance_level * (1.0 - proximity_pct / 100.0)

            # 5. Signal Triggering with AI Approval Gate
            # BUY Signal (Bullish reversal near support)
            if near_support and (is_bull_pin or is_bull_engulfing):
                pattern_name = "Bullish Pin Bar" if is_bull_pin else "Bullish Engulfing"
                
                # Check AI Approval if enabled
                if self.params["ai_confirm"]:
                    bot_logger.info(f"[Price_Action] Setup detected on {pair}. Querying AI agent for trade approval...")
                    
                    # Prepare candles summary (last 10 candles)
                    last_10 = df.tail(10)
                    candles_summary = "\n".join([
                        f"  O={float(row['open']):.2f} H={float(row['high']):.2f} "
                        f"L={float(row['low']):.2f} C={float(row['close']):.2f} "
                        f"V={float(row['volume']):.0f}"
                        for _, row in last_10.iterrows()
                    ])
                    
                    # Call primary model
                    approved = self._call_ollama_for_approval(
                        pair=pair,
                        action="BUY",
                        pattern_name=pattern_name,
                        support_level=support_level,
                        resistance_level=resistance_level,
                        close_p=close_p,
                        candles_summary=candles_summary,
                        model=self.params["model"]
                    )
                    
                    # Fallback to secondary model if primary fails
                    if approved is None:
                        bot_logger.info(f"[Price_Action] Falling back to {self.params['fallback_model']} for approval...")
                        approved = self._call_ollama_for_approval(
                            pair=pair,
                            action="BUY",
                            pattern_name=pattern_name,
                            support_level=support_level,
                            resistance_level=resistance_level,
                            close_p=close_p,
                            candles_summary=candles_summary,
                            model=self.params["fallback_model"]
                        )
                    
                    # Fail-secure check
                    if approved is not True:
                        reason_msg = "rejected by AI agent" if approved == False else "AI server offline (fail-secure)"
                        bot_logger.info(f"[Price_Action] BUY trade for {pair} suppressed: {reason_msg}")
                        return None

                strength = 0.85 if is_bull_pin else 0.80
                reason = (
                    f"Price Action BUY: {pattern_name} detected near support "
                    f"₹{support_level:.2f} (Current Price: ₹{close_p:.2f})"
                )
                bot_logger.info(f"[Price_Action] BUY signal APPROVED and executed for {pair}: {reason}")
                return StrategySignal(
                    pair=pair,
                    action="BUY",
                    strategy=self.name,
                    strength=strength,
                    reason=reason,
                    metadata={
                        "support_level": support_level,
                        "resistance_level": resistance_level,
                        "candlestick_pattern": pattern_name,
                        "profit_target_pct": self.params["profit_target_pct"]
                    }
                )

            # SELL Signal (Bearish reversal near resistance)
            if near_resistance and (is_bear_pin or is_bear_engulfing):
                pattern_name = "Bearish Pin Bar" if is_bear_pin else "Bearish Engulfing"
                
                # Check AI Approval if enabled
                if self.params["ai_confirm"]:
                    bot_logger.info(f"[Price_Action] Setup detected on {pair}. Querying AI agent for trade approval...")
                    
                    # Prepare candles summary
                    last_10 = df.tail(10)
                    candles_summary = "\n".join([
                        f"  O={float(row['open']):.2f} H={float(row['high']):.2f} "
                        f"L={float(row['low']):.2f} C={float(row['close']):.2f} "
                        f"V={float(row['volume']):.0f}"
                        for _, row in last_10.iterrows()
                    ])
                    
                    # Call primary model
                    approved = self._call_ollama_for_approval(
                        pair=pair,
                        action="SELL",
                        pattern_name=pattern_name,
                        support_level=support_level,
                        resistance_level=resistance_level,
                        close_p=close_p,
                        candles_summary=candles_summary,
                        model=self.params["model"]
                    )
                    
                    # Fallback to secondary model if primary fails
                    if approved is None:
                        bot_logger.info(f"[Price_Action] Falling back to {self.params['fallback_model']} for approval...")
                        approved = self._call_ollama_for_approval(
                            pair=pair,
                            action="SELL",
                            pattern_name=pattern_name,
                            support_level=support_level,
                            resistance_level=resistance_level,
                            close_p=close_p,
                            candles_summary=candles_summary,
                            model=self.params["fallback_model"]
                        )
                    
                    # Fail-secure check
                    if approved is not True:
                        reason_msg = "rejected by AI agent" if approved == False else "AI server offline (fail-secure)"
                        bot_logger.info(f"[Price_Action] SELL trade for {pair} suppressed: {reason_msg}")
                        return None

                strength = 0.85 if is_bear_pin else 0.80
                reason = (
                    f"Price Action SELL: {pattern_name} detected near resistance "
                    f"₹{resistance_level:.2f} (Current Price: ₹{close_p:.2f})"
                )
                bot_logger.info(f"[Price_Action] SELL signal APPROVED and executed for {pair}: {reason}")
                return StrategySignal(
                    pair=pair,
                    action="SELL",
                    strategy=self.name,
                    strength=strength,
                    reason=reason,
                    metadata={
                        "support_level": support_level,
                        "resistance_level": resistance_level,
                        "candlestick_pattern": pattern_name,
                        "profit_target_pct": self.params["profit_target_pct"]
                    }
                )

            return None

        except Exception as e:
            bot_logger.error(f"[Price_Action] Strategy analysis error for {pair}: {e}")
            return None
