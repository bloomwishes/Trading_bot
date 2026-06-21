"""
AutoTrader Pro - Pydantic Schemas
Request / response models for the FastAPI layer.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════════════════════
# Trade
# ═══════════════════════════════════════════════════════════════════════════
class TradeCreate(BaseModel):
    """Body for manually opening a trade."""
    pair: str = Field(..., examples=["BTC/INR"])
    side: str = Field(..., pattern="^(BUY|SELL)$", examples=["BUY"])
    quantity: float = Field(..., gt=0, examples=[0.001])
    strategy: str = Field(default="manual", examples=["manual"])


class TradeResponse(BaseModel):
    id: int
    pair: str
    strategy: str
    side: str
    entry_price: float
    exit_price: Optional[float] = None
    quantity: float
    pnl: Optional[float] = None
    status: str
    paper_mode: bool
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    trailing_stop: Optional[float] = None
    created_at: datetime
    closed_at: Optional[datetime] = None

    class Config:
        from_attributes = True          # Pydantic v2 (orm_mode equivalent)
        json_encoders = {datetime: lambda v: v.isoformat()}


# ═══════════════════════════════════════════════════════════════════════════
# Signal
# ═══════════════════════════════════════════════════════════════════════════
class SignalResponse(BaseModel):
    id: int
    pair: str
    strategy: str
    signal_type: str
    strength: float
    metadata_json: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True
        json_encoders = {datetime: lambda v: v.isoformat()}


# ═══════════════════════════════════════════════════════════════════════════
# Opportunity
# ═══════════════════════════════════════════════════════════════════════════
class OpportunityResponse(BaseModel):
    id: int
    pair: str
    score: float
    signals_triggered: Optional[str] = None
    scanner_data: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True
        json_encoders = {datetime: lambda v: v.isoformat()}


# ═══════════════════════════════════════════════════════════════════════════
# Portfolio Snapshot
# ═══════════════════════════════════════════════════════════════════════════
class PortfolioSnapshotResponse(BaseModel):
    id: int
    total_value: float
    cash: float
    positions_json: Optional[str] = None
    paper_mode: bool
    created_at: datetime

    class Config:
        from_attributes = True
        json_encoders = {datetime: lambda v: v.isoformat()}


# ═══════════════════════════════════════════════════════════════════════════
# LLM Decision
# ═══════════════════════════════════════════════════════════════════════════
class LLMDecisionResponse(BaseModel):
    id: int
    pair: str
    prompt: str
    response: str
    action: str
    confidence: float
    reason: Optional[str] = None
    acted_on: bool
    created_at: datetime

    class Config:
        from_attributes = True
        json_encoders = {datetime: lambda v: v.isoformat()}


# ═══════════════════════════════════════════════════════════════════════════
# Bot Log
# ═══════════════════════════════════════════════════════════════════════════
class BotLogResponse(BaseModel):
    id: int
    level: str
    message: str
    created_at: datetime

    class Config:
        from_attributes = True
        json_encoders = {datetime: lambda v: v.isoformat()}


# ═══════════════════════════════════════════════════════════════════════════
# Strategy Configuration
# ═══════════════════════════════════════════════════════════════════════════
class StrategyConfig(BaseModel):
    name: str = Field(..., examples=["rsi_macd"])
    enabled: bool = True
    params: Dict[str, Any] = Field(default_factory=dict)


# ═══════════════════════════════════════════════════════════════════════════
# Risk Settings
# ═══════════════════════════════════════════════════════════════════════════
class RiskSettings(BaseModel):
    max_position_pct: float = Field(default=5.0, ge=0.1, le=100.0)
    max_open_trades: int = Field(default=5, ge=1, le=50)
    daily_loss_limit_pct: float = Field(default=3.0, ge=0.1, le=100.0)
    default_stop_loss_pct: float = Field(default=1.5, ge=0.1, le=50.0)
    default_take_profit_pct: float = Field(default=3.0, ge=0.1, le=100.0)
    trailing_stop_activate_pct: float = Field(default=1.5, ge=0.1, le=50.0)
    trailing_stop_trail_pct: float = Field(default=0.5, ge=0.1, le=50.0)


# ═══════════════════════════════════════════════════════════════════════════
# Bot Status
# ═══════════════════════════════════════════════════════════════════════════
class BotStatus(BaseModel):
    running: bool = False
    mode: str = Field(default="paper", pattern="^(paper|live)$")
    uptime: float = 0.0                     # seconds
    active_trades: int = 0
    portfolio_value: float = 0.0


class PortfolioSummary(BaseModel):
    total_value: float = 0.0
    cash: float = 0.0
    invested: float = 0.0
    unrealised_pnl: float = 0.0
    realised_pnl: float = 0.0
    positions: List[Dict[str, Any]] = Field(default_factory=list)


class StatusResponse(BaseModel):
    status: BotStatus
    portfolio: PortfolioSummary
