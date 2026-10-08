import asyncio  
from backend.database import SessionLocal  
from backend.engine.trading_engine import TradingEngine  
from backend.scanner.opportunity_scanner import OpportunityScanner  
from backend.scheduler.scheduler import BotScheduler  
engine = TradingEngine()  
scanner = OpportunityScanner(exchange_manager=engine.exchange_manager)  
scheduler = BotScheduler(trading_engine=engine, scanner=scanner)  
from backend.api.diagnostics import run_diagnostics  
class MockApp:  
    state = type('State', (), {'engine': engine, 'scheduler': scheduler})()  
class MockReq:  
    app = MockApp()  
db = SessionLocal()  
print(asyncio.run(run_diagnostics(MockReq(), db)))  
