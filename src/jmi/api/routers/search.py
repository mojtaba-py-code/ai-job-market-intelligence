"""Semantic search endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...application.services import SearchService
from ..deps import get_db
from ..schemas import SearchHitOut, SemanticSearchRequest

router = APIRouter(prefix="/api/v1/search", tags=["search"])


@router.post("/semantic", response_model=list[SearchHitOut])
def semantic_search(
    payload: SemanticSearchRequest, session: Session = Depends(get_db)
) -> list[dict]:
    """Natural-language job search, e.g. 'remote python jobs with fastapi'."""
    return SearchService(session).search(payload.query, top_k=payload.top_k)
