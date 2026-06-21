import sys
sys.path.insert(0, '.')
try:
    from backend.database import Base, init_db
    print("OK: database module")
    from backend.models import Trade, Signal, Opportunity, PortfolioSnapshot, LLMDecision, BotLog
    print("OK: models (6 tables)")
    from backend.schemas import TradeResponse, TradeCreate, RiskSettings, StrategyConfig
    print("OK: schemas")
    from backend.config import settings
    print(f"OK: config (PAPER_MODE={settings.PAPER_MODE})")
    from backend.utils.logger import bot_logger
    print("OK: logger")
    from backend.utils.helpers import format_inr, calculate_pnl
    print(f"OK: helpers (format_inr works)")
    from backend.engine.indicators import calculate_ema, calculate_rsi, calculate_bollinger_bands
    print("OK: indicators")
    from backend.engine.strategy_base import StrategyBase, StrategySignal
    print("OK: strategy_base")
    from backend.engine.ma_pullback import MAPullbackStrategy
    print("OK: ma_pullback strategy")
    from backend.engine.breakout_hunter import BreakoutHunterStrategy
    print("OK: breakout_hunter strategy")
    from backend.engine.rsi_divergence import RSIDivergenceStrategy
    print("OK: rsi_divergence strategy")
    from backend.engine.grid_trading import GridTradingStrategy
    print("OK: grid_trading strategy")
    from backend.risk.risk_manager import RiskManager
    print("OK: risk_manager")
    from backend.paper.paper_trader import PaperTrader
    print("OK: paper_trader")
    from backend.main import app
    print("OK: FastAPI app loaded")
    print("\n=== ALL BACKEND MODULES VERIFIED ===")
except Exception as e:
    print(f"FAILED: {e}")
    import traceback
    traceback.print_exc()
