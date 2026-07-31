"""Job query & export use-cases."""

from __future__ import annotations

from sqlalchemy.orm import Session

from ...domain.enums import ExportFormat
from ...exceptions import NotFoundError
from ...infrastructure.db.repositories import JobFilter, JobRepository
from ...infrastructure.export import export_jobs
from ..mappers import job_to_dict


class JobService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.jobs = JobRepository(session)

    def search(self, flt: JobFilter) -> tuple[list[dict], int]:
        rows, total = self.jobs.search(flt)
        return [job_to_dict(job, include_description=False) for job in rows], total

    def get(self, job_id: int) -> dict:
        job = self.jobs.get(job_id)
        if job is None:
            raise NotFoundError(f"Job {job_id} not found.")
        return job_to_dict(job)

    def export(self, flt: JobFilter, fmt: ExportFormat | str) -> bytes:
        # Export honours the same filter but ignores pagination limits.
        export_filter = JobFilter(
            query=flt.query,
            company=flt.company,
            country=flt.country,
            city=flt.city,
            remote_status=flt.remote_status,
            category=flt.category,
            skill=flt.skill,
            min_salary=flt.min_salary,
            sort=flt.sort,
            limit=10_000,
            offset=0,
        )
        rows, _ = self.jobs.search(export_filter)
        records = [job_to_dict(job, include_description=False) for job in rows]
        # Flatten skills to a comma-separated string for tabular formats.
        for record in records:
            record["skills"] = ", ".join(s["name"] for s in record["skills"])
        return export_jobs(records, fmt)
