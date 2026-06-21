"""
AutoTrader Pro - Sentiment + LLM Agent Strategy
=================================================
Strategy 4: Uses a local Ollama LLM (llama3 / mistral) to analyze
market data and generate trading signals with a confidence score.

The strategy builds a rich prompt with current price metrics, recent
candle data, and computed technical indicators, then asks the LLM
to respond with a structured JSON decision.

If the Ollama server is unreachable the strategy logs a warning and
returns None — it never crashes the bot.
"""

import json
import re
from typing import Optional, Dict, Any

import pandas as pd
import requests

from backend.engine.strategy_base import StrategyBase, StrategySignal
from backend.engine.indicators import (
    calculate_rsi,
    calculate_macd,
    calculate_bollinger_bands,
    calculate_ema,
)
from backend.utils.logger import bot_logger
from backend.utils.helpers import timestamp_now, safe_json_loads
from backend.database import SessionLocal
from backend.models import LLMDecision


class SentimentLLMStrategy(StrategyBase):
    """
    Sentiment + LLM Agent — let a local large-language model weigh in.

    Default Parameters:
        confidence_threshold (float): Minimum LLM confidence to act on
            (default 0.75).
        model (str): Primary Ollama model name (default 'llama3').
        fallback_model (str): Model to try if primary fails (default 'mistral').
        ollama_url (str): Ollama API base URL (default 'http://localhost:11434').
        timeout (int): HTTP request timeout in seconds (default 120).
        temperature (float): LLM temperature setting (default 0.2 — deterministic).
    """

    DEFAULT_PARAMS = {
        "confidence_threshold": 0.75,
        "model": "llama3",
        "fallback_model": "mistral",
        "ollama_url": "http://localhost:11434",
        "timeout": 120,
        "temperature": 0.2,
    }

    PROMPT_TEMPLATE = (
        "You are a crypto trading analyst specializing in Indian INR markets. "
        "Based on this market data for {pair}, should I BUY, SELL, or HOLD?\n\n"
        "Data:\n{data}\n\n"
        "Reply ONLY with valid JSON — no other text, no markdown:\n"
        '{{"action": "BUY/SELL/HOLD", "confidence": 0.0-1.0, '
        '"reason": "brief explanation"}}'
    )

    def __init__(self, params: dict = None):
        merged = {**self.DEFAULT_PARAMS, **(params or {})}
        super().__init__(name="Sentiment_LLM", default_params=merged)

    # ------------------------------------------------------------------
    # Prompt building
    # ------------------------------------------------------------------
    def _build_market_summary(self, df: pd.DataFrame, pair: str) -> str:
        """Build a textual summary of the current market state."""
        latest = df.iloc[-1]
        prev = df.iloc[-2] if len(df) >= 2 else latest
        open_24h = df.iloc[0]["open"] if len(df) > 0 else latest["close"]

        current_price = float(latest["close"])
        change_24h_pct = (
            (current_price - float(open_24h)) / float(open_24h) * 100
            if float(open_24h) != 0
            else 0.0
        )
        current_volume = float(latest["volume"])

        # -- Technical indicators --
        rsi = calculate_rsi(df)
        macd_line, signal_line, histogram = calculate_macd(df)
        upper, middle, lower, bandwidth = calculate_bollinger_bands(df)
        ema_21 = calculate_ema(df, 21)

        latest_rsi = float(rsi.iloc[-1]) if not rsi.empty and not pd.isna(rsi.iloc[-1]) else None
        latest_macd = float(macd_line.iloc[-1]) if not macd_line.empty and not pd.isna(macd_line.iloc[-1]) else None
        latest_macd_signal = float(signal_line.iloc[-1]) if not signal_line.empty and not pd.isna(signal_line.iloc[-1]) else None
        latest_macd_hist = float(histogram.iloc[-1]) if not histogram.empty and not pd.isna(histogram.iloc[-1]) else None
        latest_bb_upper = float(upper.iloc[-1]) if not upper.empty and not pd.isna(upper.iloc[-1]) else None
        latest_bb_lower = float(lower.iloc[-1]) if not lower.empty and not pd.isna(lower.iloc[-1]) else None
        latest_bb_mid = float(middle.iloc[-1]) if not middle.empty and not pd.isna(middle.iloc[-1]) else None
        latest_ema21 = float(ema_21.iloc[-1]) if not ema_21.empty and not pd.isna(ema_21.iloc[-1]) else None

        # BB position: where is price relative to the bands?
        bb_position = "N/A"
        if latest_bb_upper is not None and latest_bb_lower is not None:
            bb_range = latest_bb_upper - latest_bb_lower
            if bb_range > 0:
                bb_pct = (current_price - latest_bb_lower) / bb_range * 100
                bb_position = f"{bb_pct:.1f}% (0%=lower, 100%=upper)"

        # Trend direction based on EMA21
        trend = "N/A"
        if latest_ema21 is not None:
            if current_price > latest_ema21 * 1.005:
                trend = "UPTREND (price above EMA21)"
            elif current_price < latest_ema21 * 0.995:
                trend = "DOWNTREND (price below EMA21)"
            else:
                trend = "SIDEWAYS (price near EMA21)"

        # -- Last 10 candles summary --
        last_10 = df.tail(10)
        candles_summary = []
        for _, row in last_10.iterrows():
            candles_summary.append(
                f"  O={float(row['open']):.2f} H={float(row['high']):.2f} "
                f"L={float(row['low']):.2f} C={float(row['close']):.2f} "
                f"V={float(row['volume']):.0f}"
            )

        lines = [
            f"Pair: {pair}",
            f"Current Price: ₹{current_price:.2f}",
            f"24-period Change: {change_24h_pct:+.2f}%",
            f"Current Volume: {current_volume:.0f}",
            f"Trend: {trend}",
            f"RSI(14): {latest_rsi:.1f}" if latest_rsi is not None else "RSI(14): N/A",
            f"MACD: {latest_macd:.4f}, Signal: {latest_macd_signal:.4f}, Histogram: {latest_macd_hist:.4f}"
            if latest_macd is not None
            else "MACD: N/A",
            f"Bollinger Bands: Upper=₹{latest_bb_upper:.2f}, Mid=₹{latest_bb_mid:.2f}, Lower=₹{latest_bb_lower:.2f}"
            if latest_bb_upper is not None
            else "Bollinger Bands: N/A",
            f"BB Position: {bb_position}",
            f"Last 10 candles (OHLCV):",
        ] + candles_summary

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Ollama API call
    # ------------------------------------------------------------------
    def _call_ollama(self, prompt: str, model: str) -> Optional[str]:
        """
        Call the Ollama /api/generate endpoint.

        Returns the full response text, or None on failure.
        """
        url = f"{self.params['ollama_url']}/api/generate"
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": self.params["temperature"],
            },
        }
        try:
            resp = requests.post(
                url,
                json=payload,
                timeout=self.params["timeout"],
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("response", "")
        except requests.exceptions.ConnectionError:
            bot_logger.warning(
                f"[Sentiment_LLM] Ollama server unreachable at {url}"
            )
            return None
        except requests.exceptions.Timeout:
            bot_logger.warning(
                f"[Sentiment_LLM] Ollama request timed out ({self.params['timeout']}s)"
            )
            return None
        except requests.exceptions.RequestException as e:
            bot_logger.warning(f"[Sentiment_LLM] Ollama request failed: {e}")
            return None

    # ------------------------------------------------------------------
    # Response parsing
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_llm_response(raw: str) -> Optional[Dict[str, Any]]:
        """
        Parse the LLM response text to extract the JSON decision.

        Handles:
          - Clean JSON
          - JSON wrapped in markdown code blocks
          - JSON embedded in free text
        """
        if not raw:
            return None

        # Try direct parse first
        parsed = safe_json_loads(raw.strip())
        if parsed and _is_valid_decision(parsed):
            return parsed

        # Try to find JSON inside markdown code fences
        code_block_match = re.search(
            r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL
        )
        if code_block_match:
            parsed = safe_json_loads(code_block_match.group(1))
            if parsed and _is_valid_decision(parsed):
                return parsed

        # Try to find any JSON object in the text
        json_match = re.search(r"\{[^{}]*\}", raw, re.DOTALL)
        if json_match:
            parsed = safe_json_loads(json_match.group(0))
            if parsed and _is_valid_decision(parsed):
                return parsed

        return None

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def _save_llm_decision(
        self,
        pair: str,
        model: str,
        prompt: str,
        raw_response: str,
        action: Optional[str],
        confidence: Optional[float],
        reason: Optional[str],
    ):
        """Persist the LLM decision to the database."""
        try:
            db = SessionLocal()
            decision = LLMDecision(
                pair=pair,
                model=model,
                prompt=prompt,
                raw_response=raw_response,
                action=action or "PARSE_ERROR",
                confidence=confidence or 0.0,
                reason=reason or "Failed to parse LLM response",
                created_at=timestamp_now(),
            )
            db.add(decision)
            db.commit()
            db.close()
        except Exception as e:
            bot_logger.error(
                f"[Sentiment_LLM] Failed to save LLM decision to DB: {e}"
            )

    # ------------------------------------------------------------------
    # Main analysis
    # ------------------------------------------------------------------
    def analyze(self, df: pd.DataFrame, pair: str) -> Optional[StrategySignal]:
        """
        Build a market-data prompt, send to Ollama, parse the result.

        Args:
            df: OHLCV DataFrame.
            pair: Trading pair string.

        Returns:
            StrategySignal if LLM responds with confidence above threshold,
            else None.
        """
        if df is None or len(df) < 30:
            return None

        try:
            # 1. Build prompt
            market_data = self._build_market_summary(df, pair)
            prompt = self.PROMPT_TEMPLATE.format(pair=pair, data=market_data)

            # 2. Call primary model
            model = self.params["model"]
            raw_response = self._call_ollama(prompt, model)

            # 3. Fallback to secondary model if primary fails
            if raw_response is None:
                model = self.params["fallback_model"]
                bot_logger.info(
                    f"[Sentiment_LLM] Falling back to {model}"
                )
                raw_response = self._call_ollama(prompt, model)

            if raw_response is None:
                bot_logger.warning(
                    f"[Sentiment_LLM] Both models unavailable for {pair}"
                )
                self._save_llm_decision(
                    pair=pair,
                    model=model,
                    prompt=prompt,
                    raw_response="",
                    action=None,
                    confidence=None,
                    reason="Ollama server unreachable",
                )
                return None

            # 4. Parse response
            decision = self._parse_llm_response(raw_response)

            if decision is None:
                bot_logger.warning(
                    f"[Sentiment_LLM] Could not parse LLM response for {pair}: "
                    f"{raw_response[:200]}"
                )
                self._save_llm_decision(
                    pair=pair,
                    model=model,
                    prompt=prompt,
                    raw_response=raw_response,
                    action=None,
                    confidence=None,
                    reason="Malformed LLM response",
                )
                return None

            action = str(decision.get("action", "HOLD")).upper().strip()
            confidence = float(decision.get("confidence", 0.0))
            reason = str(decision.get("reason", "No reason provided"))

            # Clamp confidence
            confidence = max(0.0, min(1.0, confidence))

            # Normalize action
            if action not in ("BUY", "SELL", "HOLD"):
                action = "HOLD"

            # 5. Save to DB
            self._save_llm_decision(
                pair=pair,
                model=model,
                prompt=prompt,
                raw_response=raw_response,
                action=action,
                confidence=confidence,
                reason=reason,
            )

            # 6. Only return a signal if confidence exceeds threshold
            threshold = self.params["confidence_threshold"]
            if confidence < threshold:
                bot_logger.info(
                    f"[Sentiment_LLM] {pair} — {action} with confidence "
                    f"{confidence:.2f} below threshold {threshold}. Skipping."
                )
                return None

            if action == "HOLD":
                return None

            bot_logger.info(
                f"[Sentiment_LLM] {action} signal for {pair} — "
                f"confidence={confidence:.2f}, reason: {reason}"
            )

            return StrategySignal(
                pair=pair,
                action=action,
                strategy=self.name,
                strength=confidence,
                reason=f"[LLM/{model}] {reason}",
                metadata={
                    "llm_model": model,
                    "llm_confidence": confidence,
                    "llm_action": action,
                    "llm_reason": reason,
                },
            )

        except Exception as e:
            bot_logger.error(
                f"[Sentiment_LLM] Analysis error for {pair}: {e}"
            )
            return None


# --------------------------------------------------------------------------
# Module-level helper
# --------------------------------------------------------------------------
def _is_valid_decision(d: Any) -> bool:
    """Check that a parsed dict has the three required decision keys."""
    if not isinstance(d, dict):
        return False
    return "action" in d and "confidence" in d and "reason" in d
