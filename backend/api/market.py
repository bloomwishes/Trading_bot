"""
AutoTrader Pro — Live Market Data Router
=========================================
GET /api/market/live       →  live prices for all INR crypto pairs (public, no auth)
GET /api/market/analyze    →  AI analysis of market using Ollama local LLM
"""

from __future__ import annotations

import time
import json
from typing import Any, Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
import pandas as pd
from fastapi import APIRouter, HTTPException, Query, Request

from backend.utils.logger import bot_logger
from backend.engine.indicators import calculate_rsi, calculate_ema, calculate_bollinger_bands

router = APIRouter(prefix="/api/market", tags=["market"])

# ── In-memory cache ──────────────────────────────────────────────────────────
_cache: Dict[str, tuple[float, Any]] = {}
CACHE_TTL = 30  # seconds


def _cache_get(key: str) -> Any | None:
    entry = _cache.get(key)
    if entry is None:
        return None
    ts, data = entry
    if time.time() - ts > CACHE_TTL:
        del _cache[key]
        return None
    return data


def _cache_set(key: str, data: Any) -> None:
    _cache[key] = (time.time(), data)


# ── CoinDCX Public API (no auth needed) ─────────────────────────────────────

COINDCX_TICKER_URL = "https://api.coindcx.com/exchange/ticker"
COINDCX_MARKETS_URL = "https://api.coindcx.com/exchange/v1/markets_details"
COINGECKO_SIMPLE_URL = "https://api.coingecko.com/api/v3/simple/price"
COINGECKO_MARKETS_URL = "https://api.coingecko.com/api/v3/coins/markets"

# Top crypto symbols to track (INR pairs)
TOP_COINS = [
    "BTC", "ETH", "SOL", "XRP", "DOGE", "ADA", "AVAX", "DOT", "MATIC", "LINK",
    "SHIB", "LTC", "UNI", "ATOM", "FIL", "NEAR", "APT", "ARB", "OP", "INJ",
    "SUI", "SEI", "TIA", "PEPE", "WIF", "BONK", "RENDER", "FET", "THETA", "SAND",
]


def _fetch_coindcx_tickers() -> List[Dict[str, Any]]:
    """Fetch all tickers from CoinDCX public endpoint."""
    try:
        resp = requests.get(COINDCX_TICKER_URL, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        bot_logger.warning(f"CoinDCX ticker fetch failed: {exc}")
        return []


def _fetch_coingecko_prices() -> List[Dict[str, Any]]:
    """Fallback: fetch from CoinGecko free API."""
    coin_ids = {
        "BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana", "XRP": "ripple",
        "DOGE": "dogecoin", "ADA": "cardano", "AVAX": "avalanche-2", "DOT": "polkadot",
        "MATIC": "matic-network", "LINK": "chainlink", "SHIB": "shiba-inu",
        "LTC": "litecoin", "UNI": "uniswap", "ATOM": "cosmos", "FIL": "filecoin",
        "NEAR": "near", "APT": "aptos", "ARB": "arbitrum", "OP": "optimism",
        "INJ": "injective-protocol", "SUI": "sui", "SEI": "sei-network",
        "TIA": "celestia", "PEPE": "pepe", "WIF": "dogwifcoin", "BONK": "bonk",
        "RENDER": "render-token", "FET": "artificial-superintelligence-alliance",
        "THETA": "theta-token", "SAND": "the-sandbox",
    }
    ids_str = ",".join(coin_ids.values())
    try:
        resp = requests.get(
            COINGECKO_MARKETS_URL,
            params={
                "vs_currency": "inr",
                "ids": ids_str,
                "order": "market_cap_desc",
                "sparkline": "false",
                "price_change_percentage": "24h",
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        # Reverse map id -> symbol
        id_to_symbol = {v: k for k, v in coin_ids.items()}
        results = []
        for coin in data:
            symbol = id_to_symbol.get(coin["id"], coin.get("symbol", "").upper())
            results.append({
                "market": f"{symbol}INR",
                "last_price": str(coin.get("current_price", 0)),
                "change_24_hour": str(coin.get("price_change_percentage_24h", 0)),
                "volume": str(coin.get("total_volume", 0)),
                "high": str(coin.get("high_24h", 0)),
                "low": str(coin.get("low_24h", 0)),
                "market_cap": coin.get("market_cap", 0),
                "source": "coingecko",
            })
        return results
    except Exception as exc:
        bot_logger.warning(f"CoinGecko fetch failed: {exc}")
        return []


def _compute_signal(change_24h: float, rsi: float = 50.0) -> Dict[str, Any]:
    """Compute a simple buy/hold/sell signal based on indicators."""
    score = 50  # neutral
    reasons = []

    # RSI component (0-30 points)
    if rsi < 30:
        score += 25
        reasons.append("RSI oversold")
    elif rsi < 40:
        score += 15
        reasons.append("RSI approaching oversold")
    elif rsi > 70:
        score -= 25
        reasons.append("RSI overbought")
    elif rsi > 60:
        score -= 10
        reasons.append("RSI elevated")

    # Momentum component (0-25 points)
    if change_24h > 5:
        score += 15
        reasons.append("Strong upward momentum")
    elif change_24h > 2:
        score += 10
        reasons.append("Positive momentum")
    elif change_24h < -5:
        score -= 15
        reasons.append("Strong downward pressure")
    elif change_24h < -2:
        score -= 10
        reasons.append("Negative momentum")

    # Clamp score
    score = max(0, min(100, score))

    # Generate recommendation
    if score >= 70:
        recommendation = "STRONG BUY"
        risk_level = "Medium"
    elif score >= 55:
        recommendation = "BUY"
        risk_level = "Low-Medium"
    elif score >= 45:
        recommendation = "HOLD"
        risk_level = "Low"
    elif score >= 30:
        recommendation = "SELL"
        risk_level = "Medium-High"
    else:
        recommendation = "STRONG SELL"
        risk_level = "High"

    return {
        "recommendation": recommendation,
        "score": score,
        "risk_level": risk_level,
        "reasons": reasons,
    }


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/live", summary="Live market data for all INR crypto pairs")
async def get_live_market() -> Dict[str, Any]:
    """
    Returns live market data for top crypto coins in INR.
    Uses CoinDCX public API (no authentication), falls back to CoinGecko.
    """
    cached = _cache_get("live_market")
    if cached is not None:
        return cached

    # Try CoinDCX first
    tickers = _fetch_coindcx_tickers()

    coins = []
    source = "coindcx"

    if tickers:
        # Filter for INR pairs only
        inr_tickers = [
            t for t in tickers
            if t.get("market", "").upper().endswith("INR")
        ]
        # Sort by volume
        inr_tickers.sort(
            key=lambda t: float(t.get("volume", 0) or 0), reverse=True
        )

        for t in inr_tickers:
            market = t.get("market", "").upper()
            symbol = market.replace("INR", "")
            if not symbol:
                continue

            last_price = float(t.get("last_price", 0) or 0)
            change_24h = float(t.get("change_24_hour", 0) or 0)
            volume = float(t.get("volume", 0) or 0)
            high = float(t.get("high", 0) or 0)
            low = float(t.get("low", 0) or 0)
            bid = float(t.get("bid", 0) or 0)
            ask = float(t.get("ask", 0) or 0)

            if last_price <= 0:
                continue

            signal = _compute_signal(change_24h)

            coins.append({
                "symbol": symbol,
                "pair": f"{symbol}/INR",
                "price": round(last_price, 2),
                "change_24h": round(change_24h, 2),
                "volume": round(volume, 2),
                "high_24h": round(high, 2),
                "low_24h": round(low, 2),
                "bid": round(bid, 2),
                "ask": round(ask, 2),
                "spread": round(ask - bid, 2) if ask > 0 and bid > 0 else 0,
                "recommendation": signal["recommendation"],
                "score": signal["score"],
                "risk_level": signal["risk_level"],
                "reasons": signal["reasons"],
                "source": source,
            })
    else:
        # Fallback to CoinGecko
        source = "coingecko"
        gecko_data = _fetch_coingecko_prices()
        for t in gecko_data:
            market = t.get("market", "").upper()
            symbol = market.replace("INR", "")
            if not symbol:
                continue

            last_price = float(t.get("last_price", 0) or 0)
            change_24h = float(t.get("change_24_hour", 0) or 0)
            volume = float(t.get("volume", 0) or 0)

            if last_price <= 0:
                continue

            signal = _compute_signal(change_24h)

            coins.append({
                "symbol": symbol,
                "pair": f"{symbol}/INR",
                "price": round(last_price, 2),
                "change_24h": round(change_24h, 2),
                "volume": round(volume, 2),
                "high_24h": float(t.get("high", 0) or 0),
                "low_24h": float(t.get("low", 0) or 0),
                "bid": 0,
                "ask": 0,
                "spread": 0,
                "market_cap": t.get("market_cap", 0),
                "recommendation": signal["recommendation"],
                "score": signal["score"],
                "risk_level": signal["risk_level"],
                "reasons": signal["reasons"],
                "source": source,
            })

    result = {
        "coins": coins[:50],  # Top 50
        "total_pairs": len(coins),
        "source": source,
        "timestamp": time.time(),
        "cached": False,
    }

    _cache_set("live_market", result)
    return result


@router.get("/analyze", summary="AI-powered market analysis using local LLM")
async def analyze_market(
    symbols: str = Query("BTC,ETH,SOL,XRP,DOGE", description="Comma-separated symbols to analyze"),
) -> Dict[str, Any]:
    """
    Uses Ollama local LLM to analyze market conditions and provide
    AI-powered trading recommendations.
    """
    # First get live data
    cached_market = _cache_get("live_market")
    if not cached_market:
        # Fetch fresh
        tickers = _fetch_coindcx_tickers()
        if not tickers:
            tickers = _fetch_coingecko_prices()
        cached_market = {"coins": tickers}

    symbol_list = [s.strip().upper() for s in symbols.split(",")]

    # Gather market data for requested symbols
    market_summary = []
    coins_data = cached_market.get("coins", [])

    for coin in coins_data:
        sym = coin.get("symbol", "").upper()
        if sym in symbol_list:
            market_summary.append(
                f"- {sym}/INR: Price ₹{coin.get('price', 'N/A')}, "
                f"24h Change: {coin.get('change_24h', 'N/A')}%, "
                f"Volume: ₹{coin.get('volume', 'N/A')}, "
                f"Signal: {coin.get('recommendation', 'N/A')} "
                f"(Score: {coin.get('score', 'N/A')}/100)"
            )

    if not market_summary:
        market_summary = [f"- {s}/INR: Data unavailable" for s in symbol_list]

    prompt = f"""You are a professional cryptocurrency trading analyst. Analyze the following live market data and provide actionable trading recommendations.

LIVE MARKET DATA (INR pairs):
{chr(10).join(market_summary)}

For EACH coin, provide:
1. **Action**: BUY / SELL / HOLD
2. **Confidence**: Low / Medium / High
3. **Risk Level**: 1-5 (1=lowest risk)
4. **Key Reason**: One sentence explaining why
5. **Target**: Suggested target price movement (%)

Also provide an overall MARKET SENTIMENT summary (Bullish/Bearish/Neutral).

Be concise and specific. Format as a structured analysis."""

    # Try Ollama
    analysis = None
    ai_source = "none"

    try:
        ollama_resp = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": "llama3",
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.3, "num_predict": 1024},
            },
            timeout=60,
        )
        if ollama_resp.status_code == 200:
            data = ollama_resp.json()
            analysis = data.get("response", "")
            ai_source = "ollama/llama3"
            bot_logger.info("AI analysis completed via Ollama")
    except Exception as exc:
        bot_logger.warning(f"Ollama analysis failed: {exc}")

    # If Ollama failed, try mistral model
    if not analysis:
        try:
            ollama_resp = requests.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": "mistral",
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.3, "num_predict": 1024},
                },
                timeout=60,
            )
            if ollama_resp.status_code == 200:
                data = ollama_resp.json()
                analysis = data.get("response", "")
                ai_source = "ollama/mistral"
        except Exception:
            pass

    # If still no AI, generate a rule-based analysis
    if not analysis:
        ai_source = "rule-based"
        lines = ["## Market Analysis (Algorithmic)\n"]
        for coin in coins_data:
            sym = coin.get("symbol", "").upper()
            if sym in symbol_list:
                rec = coin.get("recommendation", "HOLD")
                score = coin.get("score", 50)
                change = coin.get("change_24h", 0)
                risk = coin.get("risk_level", "Medium")
                confidence = "High" if abs(score - 50) > 20 else "Medium" if abs(score - 50) > 10 else "Low"

                lines.append(
                    f"**{sym}/INR** — {rec} | Confidence: {confidence} | "
                    f"Risk: {risk} | 24h: {change:+.2f}% | Score: {score}/100"
                )
                for reason in coin.get("reasons", []):
                    lines.append(f"  - {reason}")
                lines.append("")

        # Overall sentiment
        avg_change = sum(
            c.get("change_24h", 0) for c in coins_data
            if c.get("symbol", "").upper() in symbol_list
        ) / max(len(symbol_list), 1)

        sentiment = "Bullish" if avg_change > 2 else "Bearish" if avg_change < -2 else "Neutral"
        lines.append(f"\n**Overall Market Sentiment: {sentiment}** (Avg 24h change: {avg_change:+.2f}%)")
        analysis = "\n".join(lines)

    return {
        "analysis": analysis,
        "ai_source": ai_source,
        "symbols_analyzed": symbol_list,
        "timestamp": time.time(),
    }
