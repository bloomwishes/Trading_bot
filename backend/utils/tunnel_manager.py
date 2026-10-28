"""
AutoTrader Pro - Cloudflare Mobile Tunnel Manager
==================================================
Manages the cloudflared background tunnel, detects the active public trycloudflare.com
URL from logs or subprocess output, and exposes status/QR link to the API and frontend.
"""

from __future__ import annotations

import re
import socket
import threading
from pathlib import Path
from typing import Optional, Dict, Any

from backend.config import settings
from backend.utils.logger import bot_logger

TUNNEL_LOG_PATH = settings.LOG_DIR / "tunnel.log"
CLOUDFLARE_URL_REGEX = re.compile(r"https://[a-zA-Z0-9\-]+\.trycloudflare\.com")


def get_local_ip() -> str:
    """Detect LAN Wi-Fi / Ethernet IP address for local network connection."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        # Use common internal DNS to discover outgoing interface
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "127.0.0.1"


class TunnelManager:
    """Manages active Cloudflare tunnel metadata and URL extraction."""

    def __init__(self) -> None:
        self._url: Optional[str] = None
        self._lock = threading.Lock()
        self.local_ip: str = get_local_ip()

    def set_tunnel_url(self, url: str) -> None:
        with self._lock:
            self._url = url
            bot_logger.info(f"[TunnelManager] Cloudflare Tunnel URL set: {url}")

    def get_tunnel_url(self) -> Optional[str]:
        with self._lock:
            if self._url:
                return self._url

        # Check tunnel.log file if available
        if TUNNEL_LOG_PATH.exists():
            try:
                # Read last 8KB of log to find the latest trycloudflare URL
                content = TUNNEL_LOG_PATH.read_text(encoding="utf-8", errors="ignore")
                matches = CLOUDFLARE_URL_REGEX.findall(content)
                if matches:
                    latest = matches[-1]
                    with self._lock:
                        self._url = latest
                    return latest
            except Exception as e:
                bot_logger.debug(f"[TunnelManager] Error reading tunnel.log: {e}")

        return None

    def get_info(self) -> Dict[str, Any]:
        url = self.get_tunnel_url()
        local_port = getattr(settings, "FRONTEND_PORT", 3000)
        local_link = f"http://{self.local_ip}:{local_port}"
        return {
            "active": bool(url),
            "tunnel_url": url,
            "local_url": local_link,
            "dashboard_url": url or local_link,
            "ip": self.local_ip,
            "port": local_port,
        }


tunnel_manager = TunnelManager()
