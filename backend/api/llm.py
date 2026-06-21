"""
AutoTrader Pro — LLM Decisions Router
======================================
GET /api/llm/decisions  →  paginated LLM decision log with filters
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import LLMDecision
from backend.schemas import LLMDecisionResponse

router = APIRouter(prefix="/api/llm", tags=["llm"])


@router.get("/decisions", summary="LLM decision log", response_model=list[LLMDecisionResponse])
async def get_llm_decisions(
    pair: Optional[str] = Query(None, description="Filter by trading pair, e.g. BTC/INR"),
    acted_on: Optional[bool] = Query(None, description="Filter by whether the decision was acted on"),
    date_from: Optional[datetime] = Query(None, description="Start date (ISO-8601)"),
    date_to: Optional[datetime] = Query(None, description="End date (ISO-8601)"),
    limit: int = Query(50, ge=1, le=500, description="Page size"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    db: Session = Depends(get_db),
) -> list[LLMDecision]:
    """
    Returns LLM-generated trade decisions, newest first, with optional filters.

    Each record includes the LLM's reasoning, confidence score, recommended
    action, and whether the bot actually acted on the advice.
    """
    query = db.query(LLMDecision)

    if pair is not None:
        query = query.filter(LLMDecision.pair == pair.upper())
    if acted_on is not None:
        query = query.filter(LLMDecision.acted_on == acted_on)
    if date_from is not None:
        query = query.filter(LLMDecision.created_at >= date_from)
    if date_to is not None:
        query = query.filter(LLMDecision.created_at <= date_to)

    return query.order_by(desc(LLMDecision.created_at)).offset(offset).limit(limit).all()
