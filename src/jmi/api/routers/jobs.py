"""Job listing, detail and export endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ...application.services import JobService
from ...domain.enums import ExportFormat
from ...infrastructure.db.repositories import JobFilter
from ...infrastructure.export.exporters import content_type_for
from ..deps import get_current_user, get_db
from ..schemas import JobDetail, PaginatedJobs

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])

_EXPORT_EXTENSION = {
    ExportFormat.csv: "csv",
    ExportFormat.json: "json",
    ExportFormat.excel: "xlsx",
}


def _filter_from_query(
    q: str | None,
    company: str | None,
    country: str | None,
    city: str | None,
    remote_status: str | None,
    category: str | None,
    skill: str | None,
    min_salary: float | None,
    sort: str,
    limit: int,
    offset: int,
) -> JobFilter:
    return JobFilter(
        query=q,
        company=company,
        country=country,
        city=city,
        remote_status=remote_status,
        category=category,
        skill=skill,
        min_salary=min_salary,
        sort=sort,
        limit=limit,
        offset=offset,
    )


@router.get("", response_model=PaginatedJobs)
def list_jobs(
    session: Session = Depends(get_db),
    q: str | None = Query(default=None, description="Free-text search in title/description"),
    company: str | None = None,
    country: str | None = None,
    city: str | None = None,
    remote_status: str | None = Query(default=None, pattern="^(remote|hybrid|on_site|unknown)$"),
    category: str | None = None,
    skill: str | None = None,
    min_salary: float | None = Query(default=None, ge=0),
    sort: str = Query(default="-posted_at", pattern="^-?(posted_at|salary_max|created_at|title)$"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict:
    """Paginated, filterable, sortable job listing."""
    flt = _filter_from_query(
        q, company, country, city, remote_status, category, skill, min_salary, sort, limit, offset
    )
    items, total = JobService(session).search(flt)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/export")
def export_jobs_endpoint(
    session: Session = Depends(get_db),
    _user=Depends(get_current_user),
    fmt: ExportFormat = Query(default=ExportFormat.csv, alias="format"),
    q: str | None = None,
    company: str | None = None,
    country: str | None = None,
    skill: str | None = None,
    min_salary: float | None = Query(default=None, ge=0),
) -> Response:
    """Export the filtered job set as CSV, JSON or Excel (authenticated)."""
    flt = _filter_from_query(
        q, company, country, None, None, None, skill, min_salary, "-posted_at", 10_000, 0
    )
    payload = JobService(session).export(flt, fmt)
    filename = f"jobs.{_EXPORT_EXTENSION[fmt]}"
    return Response(
        content=payload,
        media_type=content_type_for(fmt),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{job_id}", response_model=JobDetail)
def get_job(job_id: int, session: Session = Depends(get_db)) -> dict:
    return JobService(session).get(job_id)
