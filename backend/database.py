"""
AutoTrader Pro - Database Module
SQLAlchemy engine, session factory, declarative base, and FastAPI dependency.
"""

from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from typing import Generator

from backend.config import settings

# ---------------------------------------------------------------------------
# Engine – SQLite stored at BOT/autotrader.db
# ---------------------------------------------------------------------------
DATABASE_URL = f"sqlite:///{settings.DB_PATH}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},  # required for SQLite + threads
    echo=False,
    poolclass=NullPool,
)

# ---------------------------------------------------------------------------
# Session factory
# ---------------------------------------------------------------------------
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

# ---------------------------------------------------------------------------
# Declarative base for ORM models
# ---------------------------------------------------------------------------
Base = declarative_base()


# ---------------------------------------------------------------------------
# Table creation helper
# ---------------------------------------------------------------------------
def init_db() -> None:
    """Import all models and create tables that don't yet exist."""
    # Side-effect import to ensure every model is registered on Base.metadata
    import backend.models  # noqa: F401

    Base.metadata.create_all(bind=engine)

    # Dynamic SQLite migrations for new columns
    import sqlite3
    from backend.config import settings
    conn = sqlite3.connect(settings.DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("ALTER TABLE trades ADD COLUMN entry_reason VARCHAR(256)")
        conn.commit()
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE trades ADD COLUMN exit_reason VARCHAR(256)")
        conn.commit()
    except sqlite3.OperationalError:
        pass
    conn.close()


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------
def get_db() -> Generator[Session, None, None]:
    """Yield a DB session that is automatically closed after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
