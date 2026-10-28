"""
AutoTrader Pro — Monitoring, Analytics & Reporting Package
==========================================================
"""

from backend.monitoring.alert_manager import alert_manager, AlertManager
from backend.monitoring.health_monitor import health_monitor, SystemHealthMonitor
from backend.monitoring.performance_analytics import PerformanceAnalytics
from backend.monitoring.strategy_tracker import strategy_tracker, StrategyPerformanceTracker
from backend.monitoring.daily_report import DailyReportGenerator

__all__ = [
    "alert_manager",
    "AlertManager",
    "health_monitor",
    "SystemHealthMonitor",
    "PerformanceAnalytics",
    "strategy_tracker",
    "StrategyPerformanceTracker",
    "DailyReportGenerator",
]
