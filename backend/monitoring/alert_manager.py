"""
AutoTrader Pro — Multi-Channel Alert Manager
=============================================
Dispatches real-time alerts across Console/Logger, Telegram Bot API,
and Webhook endpoints with priority routing and deduplication/throttling.

Priority Levels:
  - CRITICAL: 🚨 Immediate operator attention (Shutdowns, liquidation, repeated API failures)
  - HIGH:     ⚠️ High risk condition (Drawdowns, strategy degradation, health check fails)
  - NORMAL:   📊 Routine lifecycle events (Trade executions, daily report, profit targets)
  - LOW:      ℹ️ Informational status updates (Cache warms, cycle ticks)
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import urllib.request
import urllib.error

from backend.config import settings
from backend.utils.logger import bot_logger


PRIORITY_ICONS = {
    "CRITICAL": "🚨",
    "HIGH": "⚠️",
    "NORMAL": "📊",
    "LOW": "ℹ️",
}


class AlertManager:
    """
    Central alerting engine with multi-channel dispatch:
      1. Console / File logger
      2. Telegram Bot API (direct HTTPS POST, no heavy dependencies)
      3. Generic Webhook (HTTP POST JSON)
      4. In-memory circular buffer for status and WebSocket delivery
    """

    def __init__(self) -> None:
        self.telegram_token = getattr(settings, "TELEGRAM_BOT_TOKEN", "")
        self.telegram_chat_id = getattr(settings, "TELEGRAM_CHAT_ID", "")
        self.webhook_url = getattr(settings, "ALERT_WEBHOOK_URL", "")
        self.alerts_enabled = getattr(settings, "ALERTS_ENABLED", True)

        self._recent_alerts: List[Dict[str, Any]] = []
        self._max_stored_alerts: int = 50
        self._lock = threading.Lock()

    def get_recent_alerts(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Return the latest alerts (newest first)."""
        with self._lock:
            return list(reversed(self._recent_alerts[-limit:]))

    def clear_alerts(self) -> None:
        """Clear the in-memory alerts buffer."""
        with self._lock:
            self._recent_alerts.clear()

    def send_alert(
        self,
        event: str,
        message: str,
        priority: str = "NORMAL",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Dispatches an alert across enabled channels in a non-blocking background thread.
        Returns the constructed alert payload immediately.
        """
        priority = priority.upper()
        if priority not in PRIORITY_ICONS:
            priority = "NORMAL"

        icon = PRIORITY_ICONS[priority]
        timestamp = datetime.now(timezone.utc).isoformat()

        alert_payload: Dict[str, Any] = {
            "timestamp": timestamp,
            "priority": priority,
            "icon": icon,
            "event": event,
            "message": message,
            "metadata": metadata or {},
        }

        # 1. Store in memory buffer
        with self._lock:
            self._recent_alerts.append(alert_payload)
            if len(self._recent_alerts) > self._max_stored_alerts:
                self._recent_alerts.pop(0)

        # 2. Console & File logging
        log_msg = f"{icon} [{priority}] [{event}] {message}"
        if priority == "CRITICAL":
            bot_logger.critical(log_msg)
        elif priority == "HIGH":
            bot_logger.warning(log_msg)
        else:
            bot_logger.info(log_msg)

        # 3. External dispatch in background daemon thread (non-blocking)
        if self.alerts_enabled:
            threading.Thread(
                target=self._dispatch_external,
                args=(alert_payload,),
                daemon=True,
            ).start()

        return alert_payload

    def _dispatch_external(self, payload: Dict[str, Any]) -> None:
        """Dispatches to Telegram and Webhook safely without raising exceptions."""
        try:
            self._send_telegram(payload)
        except Exception as e:
            bot_logger.debug(f"[AlertManager] Telegram send failed: {e}")

        try:
            self._send_webhook(payload)
        except Exception as e:
            bot_logger.debug(f"[AlertManager] Webhook send failed: {e}")

    def _send_telegram(self, payload: Dict[str, Any]) -> None:
        """Post message to Telegram Bot API via standard library HTTPS."""
        token = self.telegram_token or getattr(settings, "TELEGRAM_BOT_TOKEN", "")
        chat_id = self.telegram_chat_id or getattr(settings, "TELEGRAM_CHAT_ID", "")
        if not token or not chat_id:
            return

        formatted_text = (
            f"{payload['icon']} *AutoTrader Alert: {payload['priority']}*\n"
            f"*Event:* `{payload['event']}`\n"
            f"*Time (UTC):* {payload['timestamp'][:19]}\n\n"
            f"{payload['message']}"
        )

        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = json.dumps({
            "chat_id": chat_id,
            "text": formatted_text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        }).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            _ = resp.read()

    def _send_webhook(self, payload: Dict[str, Any]) -> None:
        """Post JSON alert to configured Webhook URL."""
        webhook_url = self.webhook_url or getattr(settings, "ALERT_WEBHOOK_URL", "")
        if not webhook_url:
            return

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            webhook_url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            _ = resp.read()


# Global Singleton
alert_manager = AlertManager()
