"""
AutoTrader Pro - Pydantic Schemas
Request / response models for the FastAPI layer.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_serializer


def _format_datetime_utc(v: Optional[datetime]) -> Optional[str]:
    """Ensure naive UTC datetimes are serialized with trailing 'Z' for accurate browser timezone conversion."""
    if v is None:
        return None
    if v.tzinfo is None:
        return v.isoformat() + "Z"
    return v.isoformat()


# ═══════════════════════════════════════════════════════════════════════════
# Trade
# ═══════════════════════════════════════════════════════════════════════════
class TradeCreate(BaseModel):
    """Body for manually opening a trade."""
    pair: str = Field(..., examples=["BTC/INR"])
    side: str = Field(..., pattern="^(BUY|SELL)$", examples=["BUY"])
    quantity: Optional[float] = Field(default=None, gt=0, examples=[0.001])
    amount_inr: Optional[float] = Field(default=None, gt=0, examples=[500.0])
    strategy: str = Field(default="manual", examples=["manual"])
    stop_loss: Optional[float] = Field(default=None, examples=[1.5])
    take_profit: Optional[float] = Field(default=None, examples=[3.0])


class StopLossUpdate(BaseModel):
    """Body for updating a trade's stop loss price."""
    stop_loss: float = Field(..., gt=0, description="New stop loss price in INR")


class TakeProfitUpdate(BaseModel):
    """Body for updating a trade's take profit price."""
    take_profit: float = Field(..., gt=0, description="New take profit price in INR")


class TradeResponse(BaseModel):
    id: int
    pair: str
    strategy: str
    side: str
    entry_price: float
    exit_price: Optional[float] = None
    quantity: float
    amount_inr: float
    pnl: Optional[float] = None
    pnl_pct: Optional[float] = None
    current_price: Optional[float] = None
    unrealized_pnl: Optional[float] = None
    unrealized_pnl_pct: Optional[float] = None
    status: str
    paper_mode: bool
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    trailing_stop: Optional[float] = None
    created_at: datetime
    closed_at: Optional[datetime] = None
    entry_reason: Optional[str] = None
    exit_reason: Optional[str] = None

    @field_serializer("created_at", "closed_at")
    def serialize_datetime(self, v: Optional[datetime]) -> Optional[str]:
        return _format_datetime_utc(v)

    class Config:
        from_attributes = True          # Pydantic v2 (orm_mode equivalent)
        json_encoders = {datetime: _format_datetime_utc}


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

    @field_serializer("created_at")
    def serialize_datetime(self, v: Optional[datetime]) -> Optional[str]:
        return _format_datetime_utc(v)

    class Config:
        from_attributes = True
        json_encoders = {datetime: _format_datetime_utc}


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

    @field_serializer("created_at")
    def serialize_datetime(self, v: Optional[datetime]) -> Optional[str]:
        return _format_datetime_utc(v)

    class Config:
        from_attributes = True
        json_encoders = {datetime: _format_datetime_utc}


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

    @field_serializer("created_at")
    def serialize_datetime(self, v: Optional[datetime]) -> Optional[str]:
        return _format_datetime_utc(v)

    class Config:
        from_attributes = True
        json_encoders = {datetime: _format_datetime_utc}


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

    @field_serializer("created_at")
    def serialize_datetime(self, v: Optional[datetime]) -> Optional[str]:
        return _format_datetime_utc(v)

    class Config:
        from_attributes = True
        json_encoders = {datetime: _format_datetime_utc}


# ═══════════════════════════════════════════════════════════════════════════
# Bot Log
# ═══════════════════════════════════════════════════════════════════════════
class BotLogResponse(BaseModel):
    id: int
    level: str
    message: str
    created_at: datetime

    @field_serializer("created_at")
    def serialize_datetime(self, v: Optional[datetime]) -> Optional[str]:
        return _format_datetime_utc(v)

    class Config:
        from_attributes = True
        json_encoders = {datetime: _format_datetime_utc}


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
    weekly_loss_limit_pct: float = Field(default=7.0, ge=0.1, le=100.0)
    total_drawdown_limit_pct: float = Field(default=15.0, ge=0.1, le=100.0)
    max_total_exposure_pct: float = Field(default=50.0, ge=0.1, le=100.0)
    max_single_direction_exposure_pct: float = Field(default=35.0, ge=0.1, le=100.0)
    min_risk_reward_ratio: float = Field(default=1.5, ge=0.1, le=20.0)
    max_correlated_positions: int = Field(default=2, ge=1, le=20)
    correlation_threshold: float = Field(default=0.7, ge=0.0, le=1.0)
    cooldown_after_consecutive_losses: int = Field(default=3, ge=1, le=20)
    cooldown_duration_minutes: int = Field(default=60, ge=1, le=1440)
    reduce_size_high_volatility: bool = Field(default=True)


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
