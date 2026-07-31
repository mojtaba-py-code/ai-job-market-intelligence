"""Mapping helpers between ORM models and plain dictionaries.

Keeping the ORM->dict mapping in one place means the API, analytics and export
layers all see a consistent, serialisable shape.
"""

from __future__ import annotations

from ..infrastructure.db.models import Job


def job_to_dict(job: Job, *, include_description: bool = True) -> dict:
    """Convert a :class:`Job` ORM row into a flat, JSON-serialisable dict."""
    data: dict = {
        "id": job.id,
        "source": job.source,
        "external_id": job.external_id,
        "title": job.title,
        "url": job.url,
        "company": job.company.name if job.company else None,
        "company_industry": job.company.industry if job.company else None,
        "company_size": job.company.size if job.company else None,
        "employment_type": job.employment_type.value,
        "remote_status": job.remote_status.value,
        "seniority": job.seniority.value,
        "category": job.category,
        "country": job.country,
        "city": job.city,
        "salary_min": job.salary_min,
        "salary_max": job.salary_max,
        "currency": job.currency,
        "salary_period": job.salary_period,
        "experience_years_min": job.experience_years_min,
        "education": job.education,
        "posted_at": job.posted_at.isoformat() if job.posted_at else None,
        "expires_at": job.expires_at.isoformat() if job.expires_at else None,
        "skills": [{"name": s.name, "kind": s.kind.value} for s in job.skills],
    }
    if include_description:
        data["description"] = job.description
    return data
