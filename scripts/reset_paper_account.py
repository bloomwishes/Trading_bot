"""
AutoTrader Pro - Paper Trading Account Reset Utility
=====================================================
Clears historical paper trades and active positions in the database,
resetting the paper portfolio balance back to its default starting amount (₹10,000).
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import settings
from backend.database import SessionLocal
from backend.models import Trade, PortfolioSnapshot
from backend.utils.helpers import format_inr
from backend.utils.logger import bot_logger


def reset_paper_account(starting_balance: float = None):
    balance = starting_balance or settings.PAPER_BALANCE
    print(f"Resetting paper trading account to {format_inr(balance)}...")

    session = SessionLocal()
    try:
        # Delete paper trades
        deleted_trades = session.query(Trade).filter(Trade.paper_mode.is_(True)).delete()
        # Delete paper snapshots
        deleted_snaps = session.query(PortfolioSnapshot).filter(PortfolioSnapshot.paper_mode.is_(True)).delete()

        # Add initial snapshot
        initial_snap = PortfolioSnapshot(
            total_value=balance,
            cash=balance,
            positions_json="[]",
            paper_mode=True,
        )
        session.add(initial_snap)
        session.commit()

        print(f"Successfully cleared {deleted_trades} paper trades and {deleted_snaps} snapshots.")
        print(f"Paper balance reset to {format_inr(balance)}.")
        bot_logger.info(f"Manual script reset paper account to {format_inr(balance)}")
    except Exception as exc:
        session.rollback()
        print(f"Error resetting paper account: {exc}")
        sys.exit(1)
    finally:
        session.close()


if __name__ == "__main__":
    new_bal = float(sys.argv[1]) if len(sys.argv) > 1 else None
    reset_paper_account(new_bal)
