"""Tests for the persistence layer and repositories."""

from __future__ import annotations

from datetime import date

from jmi.domain.entities import JobPosting, Location, SalaryRange, Skill
from jmi.domain.enums import RemoteStatus, SkillKind
from jmi.infrastructure.db.repositories import JobFilter, JobRepository


def _posting(external_id="j1", title="Python Engineer", company="Acme", **kw) -> JobPosting:
    return JobPosting(
        source="sample",
        external_id=external_id,
        title=title,
        company=company,
        description=kw.get("description", "Work with python and fastapi"),
        remote_status=kw.get("remote_status", RemoteStatus.remote),
        location=Location(country=kw.get("country", "US"), city=kw.get("city", "NYC")),
        salary=SalaryRange(
            min_amount=kw.get("smin", 100), max_amount=kw.get("smax", 150), currency="USD"
        ),
        skills=kw.get("skills", [Skill("Python", SkillKind.language)]),
        posted_at=kw.get("posted_at", date(2026, 7, 20)),
    )


def test_upsert_creates_company_and_skills(session):
    repo = JobRepository(session)
    job, created = repo.upsert_from_posting(_posting())
    session.flush()
    assert created is True
    assert job.company.name == "Acme"
    assert {s.name for s in job.skills} == {"Python"}


def test_upsert_is_idempotent_on_hash(session):
    repo = JobRepository(session)
    repo.upsert_from_posting(_posting())
    _, created2 = repo.upsert_from_posting(_posting())
    session.flush()
    assert created2 is False
    assert repo.count() == 1


def test_company_deduplicated_across_jobs(session):
    repo = JobRepository(session)
    repo.upsert_from_posting(_posting(external_id="a", title="Role A"))
    repo.upsert_from_posting(_posting(external_id="b", title="Role B"))
    session.flush()
    assert repo.count() == 2
    from jmi.infrastructure.db.models import Company

    assert session.query(Company).count() == 1


def test_search_filters_by_skill_and_country(session):
    repo = JobRepository(session)
    repo.upsert_from_posting(_posting(external_id="a", title="Py", country="US"))
    repo.upsert_from_posting(
        _posting(
            external_id="b",
            title="Java Dev",
            country="DE",
            skills=[Skill("Java", SkillKind.language)],
            description="java spring work",
        )
    )
    session.flush()

    rows, total = repo.search(JobFilter(skill="Python"))
    assert total == 1 and rows[0].title == "Py"

    rows, total = repo.search(JobFilter(country="DE"))
    assert total == 1 and rows[0].title == "Java Dev"


def test_search_min_salary_and_sort(session):
    repo = JobRepository(session)
    repo.upsert_from_posting(_posting(external_id="low", title="Low", smax=90))
    repo.upsert_from_posting(_posting(external_id="high", title="High", smax=200))
    session.flush()

    rows, total = repo.search(JobFilter(min_salary=100))
    assert total == 1 and rows[0].title == "High"

    rows, _ = repo.search(JobFilter(sort="-salary_max"))
    assert rows[0].title == "High"


def test_search_pagination(session):
    repo = JobRepository(session)
    for i in range(5):
        repo.upsert_from_posting(_posting(external_id=f"j{i}", title=f"Role {i}"))
    session.flush()
    rows, total = repo.search(JobFilter(limit=2, offset=0))
    assert total == 5 and len(rows) == 2
