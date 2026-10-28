"""
AutoTrader Pro - Authentication & Security Module
=================================================
Provides API key verification for protecting mutating endpoints, bot controls,
and live trade operations. Supports 'X-API-Key' header or '?api_key=' query parameter.
"""

from __future__ import annotations

import secrets
from typing import Optional

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader, APIKeyQuery

from backend.config import settings
from backend.utils.logger import bot_logger

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
api_key_query = APIKeyQuery(name="api_key", auto_error=False)

_warned_unprotected = False


def is_auth_enabled() -> bool:
    """Return True if an API_KEY has been configured in the environment."""
    return bool(settings.API_KEY and settings.API_KEY.strip())


async def require_api_key(
    header_key: Optional[str] = Security(api_key_header),
    query_key: Optional[str] = Security(api_key_query),
) -> bool:
    """
    FastAPI dependency that enforces API key authentication on sensitive endpoints.
    
    If settings.API_KEY is configured:
      - Validates that either X-API-Key header or api_key query param matches settings.API_KEY
      - Raises 401 UNAUTHORIZED if missing or invalid.
    
    If settings.API_KEY is not configured:
      - Logs a warning once to console/logger about unauthenticated mode in local development.
      - Allows access (backward compatible with local offline dev).
    """
    global _warned_unprotected

    configured_key = settings.API_KEY.strip() if settings.API_KEY else ""

    if not configured_key:
        if not _warned_unprotected:
            bot_logger.warning(
                "[Security] API_KEY is NOT set in environment! Sensitive endpoints are currently "
                "unprotected. Set API_KEY in .env before using Cloudflare Tunnel or public access."
            )
            _warned_unprotected = True
        return True

    provided_key = header_key or query_key

    if not provided_key or not secrets.compare_digest(provided_key.strip(), configured_key):
        bot_logger.warning("[Security] Unauthorized request rejected: Invalid or missing API key.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: Invalid or missing API key. Provide via 'X-API-Key' header or '?api_key=' parameter.",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    return True
