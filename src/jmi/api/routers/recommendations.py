"""Resume matching / recommendation endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...application.services import RecommendationService
from ..deps import get_current_user, get_db
from ..schemas import RecommendRequest

router = APIRouter(prefix="/api/v1/recommendations", tags=["recommendations"])


@router.post("/match")
def match_resume(
    payload: RecommendRequest,
    session: Session = Depends(get_db),
    _user=Depends(get_current_user),
) -> dict:
    """Match a resume against the job market (authenticated)."""
    result = RecommendationService(session).recommend(payload.resume_text, top_k=payload.top_k)
    return result.as_dict()
