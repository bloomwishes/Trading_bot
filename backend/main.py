"""
AutoTrader Pro — FastAPI Application Entry Point
=================================================
Initializes the FastAPI app, wires up CORS, lifespan events,
all REST routers, and WebSocket endpoints.

Run with:
    uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
"""

from __future__ import annotations

import time
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import settings
from backend.database import init_db
from backend.engine.trading_engine import TradingEngine
from backend.scanner.opportunity_scanner import OpportunityScanner
from backend.scheduler.scheduler import BotScheduler
from backend.utils.auth import is_auth_enabled

# ── API Routers ──────────────────────────────────────────────────────────────
from backend.api.status import router as status_router
from backend.api.bot import router as bot_router
from backend.api.trades import router as trades_router
from backend.api.opportunities import router as opportunities_router
from backend.api.strategies import router as strategies_router
from backend.api.risk import router as risk_router
from backend.api.portfolio import router as portfolio_router
from backend.api.llm import router as llm_router
from backend.api.websockets import router as ws_router
from backend.api.market import router as market_router
from backend.api.diagnostics import router as diagnostics_router

logger = logging.getLogger("autotrader.main")


# ── Lifespan Context Manager ──────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise database, singletons, and manage graceful shutdown."""
    logger.info("AutoTrader Pro starting up …")

    # 1. Database
    init_db()
    logger.info("Database initialised.")

    # 2. Trading engine (singleton)
    engine = TradingEngine()
    app.state.engine = engine
    logger.info("TradingEngine ready (mode=%s).", engine.mode)

    # 3. Opportunity scanner (uses the engine's exchange manager)
    scanner = OpportunityScanner(exchange_manager=engine.exchange_manager)
    app.state.scanner = scanner
    logger.info("OpportunityScanner ready.")

    # 4. Scheduler (requires engine + scanner)
    scheduler = BotScheduler(trading_engine=engine, scanner=scanner)
    app.state.scheduler = scheduler
    logger.info("BotScheduler ready.")

    # 5. Bookkeeping
    app.state.start_time = time.time()

    logger.info("AutoTrader Pro API is live on %s:%s.", settings.BACKEND_HOST, settings.BACKEND_PORT)

    yield

    # Shutdown
    logger.info("AutoTrader Pro shutting down …")

    sched: BotScheduler | None = getattr(app.state, "scheduler", None)
    if sched is not None and sched.is_running:
        sched.stop()
        logger.info("Scheduler stopped.")

    eng: TradingEngine | None = getattr(app.state, "engine", None)
    if eng is not None and eng.running:
        eng.stop()
        logger.info("TradingEngine stopped.")

    logger.info("Shutdown complete.")


# ── FastAPI App ──────────────────────────────────────────────────────────────

app = FastAPI(
    title="AutoTrader Pro API",
    version="1.0.0",
    description="Autonomous crypto trading bot — REST & WebSocket API (INR ₹)",
    lifespan=lifespan,
)

# ── CORS ─────────────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Mount Routers ────────────────────────────────────────────────────────────

app.include_router(status_router)
app.include_router(bot_router)
app.include_router(trades_router)
app.include_router(opportunities_router)
app.include_router(strategies_router)
app.include_router(risk_router)
app.include_router(portfolio_router)
app.include_router(llm_router)
app.include_router(ws_router)
app.include_router(market_router)
app.include_router(diagnostics_router)


# ── Root Health-check & Auth status ──────────────────────────────────────────

@app.get("/", tags=["health"])
async def root() -> dict:
    """Lightweight health-check endpoint."""
    return {
        "app": "AutoTrader Pro",
        "version": "1.0.0",
        "status": "ok",
        "currency": "INR",
        "auth_enabled": is_auth_enabled(),
    }


@app.get("/api/auth/status", tags=["auth"])
async def get_auth_status() -> dict:
    """Returns whether authentication is enabled."""
    return {
        "auth_enabled": is_auth_enabled(),
    }
