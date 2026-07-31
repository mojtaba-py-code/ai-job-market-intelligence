"""Analytics endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ...application.services import AnalyticsService
from ..deps import get_db

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])


@router.get("/report")
def market_report(
    session: Session = Depends(get_db),
    top_n: int = Query(default=15, ge=1, le=50),
) -> dict:
    """Aggregate market intelligence: top skills, salaries, trends, rankings."""
    return AnalyticsService(session).market_report(top_n=top_n).as_dict()
