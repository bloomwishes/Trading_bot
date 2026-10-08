"""
AutoTrader Pro - ORM Models
Six SQLAlchemy tables with proper indexes for the trading bot.
"""

from datetime import datetime

from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    Boolean,
    Text,
    DateTime,
    Index,
)

from backend.database import Base


# ═══════════════════════════════════════════════════════════════════════════
# 1. Trade
# ═══════════════════════════════════════════════════════════════════════════
class Trade(Base):
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True, autoincrement=True)
    pair = Column(String(32), nullable=False, index=True)
    strategy = Column(String(64), nullable=False, default="manual")
    side = Column(String(4), nullable=False)            # BUY / SELL
    entry_price = Column(Float, nullable=False)
    exit_price = Column(Float, nullable=True)
    quantity = Column(Float, nullable=False)
    pnl = Column(Float, nullable=True)
    status = Column(String(12), nullable=False, default="OPEN")  # OPEN / CLOSED / CANCELLED
    paper_mode = Column(Boolean, nullable=False, default=True)
    stop_loss = Column(Float, nullable=True)
    take_profit = Column(Float, nullable=True)
    trailing_stop = Column(Float, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    closed_at = Column(DateTime, nullable=True)
    entry_reason = Column(String(256), nullable=True)
    exit_reason = Column(String(256), nullable=True)

    __table_args__ = (
        Index("ix_trades_pair_created", "pair", "created_at"),
        Index("ix_trades_status", "status"),
    )

    @property
    def amount_inr(self) -> float:
        """Calculate notional amount in INR."""
        return round(self.entry_price * self.quantity, 2)

    @property
    def pnl_pct(self) -> float:
        """Calculate PnL percentage."""
        if not self.entry_price or self.exit_price is None:
            return 0.0
        if self.side.upper() == "BUY":
            return round(((self.exit_price - self.entry_price) / self.entry_price) * 100.0, 2)
        else:
            return round(((self.entry_price - self.exit_price) / self.entry_price) * 100.0, 2)

    def __repr__(self) -> str:
        return (
            f"<Trade id={self.id} {self.side} {self.pair} "
            f"qty={self.quantity} status={self.status}>"
        )



# ═══════════════════════════════════════════════════════════════════════════
# 2. Signal
# ═══════════════════════════════════════════════════════════════════════════
class Signal(Base):
    __tablename__ = "signals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    pair = Column(String(32), nullable=False, index=True)
    strategy = Column(String(64), nullable=False)
    signal_type = Column(String(4), nullable=False)     # BUY / SELL / HOLD
    strength = Column(Float, nullable=False, default=0.0)  # 0.0 – 1.0
    metadata_json = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)

    __table_args__ = (
        Index("ix_signals_pair_created", "pair", "created_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<Signal id={self.id} {self.signal_type} {self.pair} "
            f"strength={self.strength:.2f}>"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 3. Opportunity
# ═══════════════════════════════════════════════════════════════════════════
class Opportunity(Base):
    __tablename__ = "opportunities"

    id = Column(Integer, primary_key=True, autoincrement=True)
    pair = Column(String(32), nullable=False, index=True)
    score = Column(Float, nullable=False, default=0.0)
    signals_triggered = Column(Text, nullable=True)     # JSON array of signal names
    scanner_data = Column(Text, nullable=True)           # JSON blob from scanner
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)

    __table_args__ = (
        Index("ix_opportunities_pair_created", "pair", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<Opportunity id={self.id} {self.pair} score={self.score:.2f}>"


# ═══════════════════════════════════════════════════════════════════════════
# 4. PortfolioSnapshot
# ═══════════════════════════════════════════════════════════════════════════
class PortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    total_value = Column(Float, nullable=False)
    cash = Column(Float, nullable=False)
    positions_json = Column(Text, nullable=True)        # JSON dict of positions
    paper_mode = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)

    def __repr__(self) -> str:
        return (
            f"<PortfolioSnapshot id={self.id} value=₹{self.total_value:,.2f} "
            f"paper={self.paper_mode}>"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 5. LLMDecision
# ═══════════════════════════════════════════════════════════════════════════
class LLMDecision(Base):
    __tablename__ = "llm_decisions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    pair = Column(String(32), nullable=False, index=True)
    prompt = Column(Text, nullable=False)
    response = Column(Text, nullable=False)
    action = Column(String(12), nullable=False)         # BUY / SELL / HOLD
    confidence = Column(Float, nullable=False, default=0.0)
    reason = Column(Text, nullable=True)
    acted_on = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)

    __table_args__ = (
        Index("ix_llm_pair_created", "pair", "created_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<LLMDecision id={self.id} {self.action} {self.pair} "
            f"confidence={self.confidence:.2f}>"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 6. BotLog
# ═══════════════════════════════════════════════════════════════════════════
class BotLog(Base):
    __tablename__ = "bot_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    level = Column(String(10), nullable=False, default="INFO")
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)

    def __repr__(self) -> str:
        return f"<BotLog id={self.id} [{self.level}] {self.message[:60]}>"
