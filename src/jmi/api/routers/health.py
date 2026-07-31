"""Health & metadata endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from ... import __version__
from ...crawler.registry import registry
from ..deps import get_db
from ..schemas import SourceOut

router = APIRouter(tags=["system"])


@router.get("/health")
def health() -> dict:
    """Liveness probe."""
    return {"status": "ok", "version": __version__}


@router.get("/api/v1/ready")
def ready(session: Session = Depends(get_db)) -> dict:
    """Readiness probe — verifies the database is reachable."""
    session.execute(text("SELECT 1"))
    return {"status": "ready"}


@router.get("/api/v1/sources", response_model=list[SourceOut], tags=["crawler"])
def list_sources() -> list[SourceOut]:
    """List the registered job sources."""
    return [
        SourceOut(
            name=meta.name,
            display_name=meta.display_name,
            base_url=meta.base_url,
            requires_javascript=meta.requires_javascript,
        )
        for meta in registry.all_metadata()
    ]
