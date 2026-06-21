"""
AutoTrader Pro — Opportunities Router
======================================
GET /api/opportunities       →  latest scanner results (top N by score)
GET /api/opportunities/scan  →  trigger immediate scan & return results
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from backend.schemas import OpportunityResponse

router = APIRouter(prefix="/api/opportunities", tags=["opportunities"])


@router.get("", summary="Latest scanned opportunities", response_model=list[OpportunityResponse])
async def get_opportunities(
    limit: int = Query(10, ge=1, le=100, description="Max number of results"),
    request: Request = None,  # type: ignore[assignment]
) -> list[Any]:
    """
    Returns the most recent scanner results, sorted by score descending.
    Defaults to top-10; configurable via the ``limit`` query param.
    """
    scanner = request.app.state.scanner

    try:
        opportunities = scanner.get_latest_opportunities()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to fetch opportunities: {exc}") from exc

    if not opportunities:
        return []

    # Sort by score descending (highest-confidence first)
    sorted_opps = sorted(
        opportunities,
        key=lambda o: getattr(o, "score", 0) if hasattr(o, "score") else o.get("score", 0) if isinstance(o, dict) else 0,
        reverse=True,
    )

    return sorted_opps[:limit]


@router.get("/scan", summary="Trigger immediate scan", response_model=list[OpportunityResponse])
async def trigger_scan(
    limit: int = Query(10, ge=1, le=100, description="Max results to return"),
    request: Request = None,  # type: ignore[assignment]
) -> list[Any]:
    """
    Triggers the OpportunityScanner to run a full scan right now
    and returns the fresh results.
    """
    scanner = request.app.state.scanner

    try:
        results = scanner.scan_all_pairs()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Scan failed: {exc}") from exc

    if not results:
        return []

    sorted_results = sorted(
        results,
        key=lambda o: getattr(o, "score", 0) if hasattr(o, "score") else o.get("score", 0) if isinstance(o, dict) else 0,
        reverse=True,
    )

    return sorted_results[:limit]
