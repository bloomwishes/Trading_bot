"""
AutoTrader Pro — Daily Performance Report Generator
===================================================
Produces a comprehensive end-of-day trading digest in structured Markdown format.
Summarizes:
  - Portfolio performance & Day PnL (₹ and %)
  - Trade execution stats, win rate, and profit factor
  - Best and worst trades of the day
  - Strategy performance attribution
  - System health and alert occurrences
Dispatches report via AlertManager (Telegram, Webhook, Logger).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend.database import SessionLocal
from backend.models import PortfolioSnapshot, Trade
from backend.monitoring.alert_manager import alert_manager
from backend.monitoring.health_monitor import health_monitor
from backend.monitoring.performance_analytics import PerformanceAnalytics
from backend.utils.helpers import format_inr
from backend.utils.logger import bot_logger


class DailyReportGenerator:
    """
    Assembles daily trade logs and portfolio snapshots into a clean,
    informative Markdown report suitable for Telegram or dashboard viewing.
    """

    @classmethod
    def generate_report(
        cls,
        engine: Optional[Any] = None,
        date_for: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Gathers daily data from database and engine, producing structured
        dictionary and formatted markdown text.
        """
        now = date_for or datetime.now(timezone.utc)
        mode = getattr(engine, "mode", "paper").upper() if engine else "PAPER"

        db = SessionLocal()
        try:
            # 1. Fetch today's closed trades
            all_closed = db.query(Trade).filter(Trade.status == "CLOSED").all()
            today_trades = PerformanceAnalytics.filter_trades_by_period(all_closed, period="today", now=now)

            # 2. Open trades
            open_trades = db.query(Trade).filter(Trade.status == "OPEN").all()

            # 3. Analytics for today
            today_analytics = PerformanceAnalytics.calculate_full_report(
                trades=today_trades,
                period="today",
            )

            # 4. Starting and Ending Portfolio Values
            snapshots = db.query(PortfolioSnapshot).order_by(PortfolioSnapshot.created_at.asc()).all()
            today_snapshots = [
                s for s in snapshots
                if s.created_at and s.created_at.date() == now.date()
            ]

            start_val = today_snapshots[0].total_value if today_snapshots else 100000.0
            end_val = today_snapshots[-1].total_value if today_snapshots else start_val

            # If live engine available, read current portfolio value
            if engine:
                try:
                    if hasattr(engine, "paper_trader") and mode == "PAPER":
                        prices = engine.exchange_manager.get_current_prices() if hasattr(engine, "exchange_manager") else {}
                        end_val = engine.paper_trader.get_portfolio_value(prices)
                except Exception:
                    pass

            day_pnl = today_analytics["summary"]["total_pnl"]
            day_pnl_pct = (day_pnl / start_val * 100.0) if start_val > 0 else 0.0

            # 5. Best & Worst Trade
            best_trade = None
            worst_trade = None
            if today_trades:
                sorted_trades = sorted(today_trades, key=lambda t: float(t.pnl or 0.0))
                worst_trade = sorted_trades[0]
                best_trade = sorted_trades[-1]

            # 6. System Health
            health_stat = health_monitor.get_health_status()

            # 7. Build Markdown
            markdown = cls._format_markdown(
                date_str=now.strftime("%Y-%m-%d"),
                mode=mode,
                start_val=start_val,
                end_val=end_val,
                day_pnl=day_pnl,
                day_pnl_pct=day_pnl_pct,
                analytics=today_analytics,
                best_trade=best_trade,
                worst_trade=worst_trade,
                open_trades_count=len(open_trades),
                health=health_stat,
            )

            return {
                "date": now.strftime("%Y-%m-%d"),
                "mode": mode,
                "start_value": start_val,
                "end_value": end_val,
                "day_pnl": day_pnl,
                "day_pnl_pct": day_pnl_pct,
                "total_trades": today_analytics["summary"]["total_trades"],
                "win_rate": today_analytics["summary"]["win_rate"],
                "profit_factor": today_analytics["summary"]["profit_factor"],
                "open_trades_count": len(open_trades),
                "markdown": markdown,
            }
        finally:
            db.close()

    @classmethod
    def _format_markdown(
        cls,
        date_str: str,
        mode: str,
        start_val: float,
        end_val: float,
        day_pnl: float,
        day_pnl_pct: float,
        analytics: Dict[str, Any],
        best_trade: Optional[Trade],
        worst_trade: Optional[Trade],
        open_trades_count: int,
        health: Dict[str, Any],
    ) -> str:
        """Format the report into clean GitHub / Telegram markdown."""
        pnl_sign = "+" if day_pnl >= 0 else ""
        pnl_icon = "🟢" if day_pnl >= 0 else "🔴"
        summary = analytics["summary"]
        strats = analytics["breakdowns"].get("by_strategy", {})
        pairs = analytics["breakdowns"].get("by_pair", {})

        lines = [
            f"📊 *AutoTrader Pro — Daily Performance Digest*",
            f"📅 *Date:* {date_str} | *Mode:* `{mode}`",
            "",
            f"💰 *Capital & PnL:*",
            f"• Opening Balance: `{format_inr(start_val)}`",
            f"• Closing Balance: `{format_inr(end_val)}`",
            f"• Net Daily PnL: {pnl_icon} *{pnl_sign}{format_inr(day_pnl)} ({pnl_sign}{day_pnl_pct:.2f}%)*",
            "",
            f"📈 *Execution & Performance:*",
            f"• Total Trades: `{summary['total_trades']}` (Wins: {summary['winning_trades']}, Losses: {summary['losing_trades']})",
            f"• Win Rate: *{summary['win_rate']:.1f}%*",
            f"• Profit Factor: *{summary['profit_factor']:.2f}*",
            f"• Expectancy: `{format_inr(summary['expectancy'])}` / trade",
            f"• Active Open Positions: `{open_trades_count}`",
        ]

        if best_trade and float(best_trade.pnl or 0.0) > 0:
            lines.append(
                f"• 🌟 Best Trade: `{best_trade.pair}` ({best_trade.strategy}) -> +{format_inr(best_trade.pnl)} (+{best_trade.pnl_pct:.2f}%)"
            )
        if worst_trade and float(worst_trade.pnl or 0.0) < 0:
            lines.append(
                f"• ⚠️ Worst Trade: `{worst_trade.pair}` ({worst_trade.strategy}) -> {format_inr(worst_trade.pnl)} ({worst_trade.pnl_pct:.2f}%)"
            )

        if strats:
            lines.append("")
            lines.append("🤖 *Strategy Attribution:*")
            for sname, sdata in strats.items():
                s_sign = "+" if sdata["total_pnl"] >= 0 else ""
                lines.append(
                    f"• `{sname}`: {sdata['trades']} trades | WR: {sdata['win_rate']:.1f}% | PnL: {s_sign}{format_inr(sdata['total_pnl'])}"
                )

        if pairs:
            lines.append("")
            lines.append("🪙 *Pair Attribution:*")
            for pname, pdata in pairs.items():
                p_sign = "+" if pdata["total_pnl"] >= 0 else ""
                lines.append(
                    f"• `{pname}`: {pdata['trades']} trades | PnL: {p_sign}{format_inr(pdata['total_pnl'])}"
                )

        lines.append("")
        h_icon = "✅" if health.get("healthy", True) else "⚠️"
        lines.append(f"🩺 *System Health:* {h_icon} `{health.get('overall_status', 'healthy').upper()}`")

        return "\n".join(lines)

    @classmethod
    def send_daily_report(cls, engine: Optional[Any] = None) -> Dict[str, Any]:
        """Generate and dispatch daily report via AlertManager."""
        report = cls.generate_report(engine=engine)
        priority = "NORMAL"
        if report["day_pnl_pct"] < -3.0:
            priority = "HIGH"

        alert_manager.send_alert(
            event="DAILY_PERFORMANCE_REPORT",
            message=report["markdown"],
            priority=priority,
            metadata=report,
        )
        bot_logger.info(f"[DailyReport] Daily performance report dispatched for {report['date']}.")
        return report
