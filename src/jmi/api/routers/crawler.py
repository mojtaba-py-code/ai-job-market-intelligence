"""Crawler control endpoints (admin/analyst only)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...application.services import IngestService
from ...domain.enums import UserRole
from ...infrastructure.db.repositories import CrawlJobRepository
from ..deps import get_db, require_role
from ..schemas import CrawlJobOut, IngestRequest

router = APIRouter(prefix="/api/v1/crawler", tags=["crawler"])


@router.post("/ingest", response_model=CrawlJobOut, status_code=202)
def trigger_ingest(
    payload: IngestRequest,
    session: Session = Depends(get_db),
    _user=Depends(require_role(UserRole.admin, UserRole.analyst)),
) -> CrawlJobOut:
    """Trigger a crawl of a source and persist the results synchronously.

    In production this hands off to a Celery/APScheduler worker; here it runs
    inline so results are immediately queryable.
    """
    record = IngestService(session).ingest(payload.source, since=payload.since, limit=payload.limit)
    return CrawlJobOut(
        id=record.id,
        source=record.source,
        status=record.status.value,
        fetched=record.fetched,
        unique_count=record.unique_count,
        duplicates=record.duplicates,
        error=record.error,
    )


@router.get("/jobs", response_model=list[CrawlJobOut])
def crawl_history(
    session: Session = Depends(get_db),
    _user=Depends(require_role(UserRole.admin, UserRole.analyst)),
) -> list[CrawlJobOut]:
    """Recent crawl runs and their outcomes."""
    return [
        CrawlJobOut(
            id=record.id,
            source=record.source,
            status=record.status.value,
            fetched=record.fetched,
            unique_count=record.unique_count,
            duplicates=record.duplicates,
            error=record.error,
        )
        for record in CrawlJobRepository(session).recent()
    ]
