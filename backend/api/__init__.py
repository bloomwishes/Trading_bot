# AutoTrader Pro - API Package
from backend.api.status import router as status_router
from backend.api.bot import router as bot_router
from backend.api.trades import router as trades_router
from backend.api.opportunities import router as opportunities_router
from backend.api.strategies import router as strategies_router
from backend.api.risk import router as risk_router
from backend.api.portfolio import router as portfolio_router
from backend.api.llm import router as llm_router
from backend.api.websockets import router as websockets_router

__all__ = [
    "status_router",
    "bot_router",
    "trades_router",
    "opportunities_router",
    "strategies_router",
    "risk_router",
    "portfolio_router",
    "llm_router",
    "websockets_router",
]
