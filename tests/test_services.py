"""Tests for the application service layer."""

from __future__ import annotations

import pytest

from jmi.application.services import (
    AnalyticsService,
    AuthService,
    IngestService,
    JobService,
    RecommendationService,
    SearchService,
)
from jmi.domain.enums import CrawlJobStatus, ExportFormat, UserRole
from jmi.exceptions import AuthenticationError, ConflictError, NotFoundError
from jmi.infrastructure.db.repositories import JobFilter


@pytest.fixture()
def seeded(session):
    """Ingest the bundled sample source into the test DB."""
    IngestService(session).ingest("sample")
    session.flush()
    return session


# -- Ingest -----------------------------------------------------------------
def test_ingest_persists_and_records_crawl(session):
    record = IngestService(session).ingest("sample")
    session.flush()
    assert record.status is CrawlJobStatus.completed
    assert record.unique_count > 0
    assert JobService(session).search(JobFilter())[1] == record.unique_count


def test_ingest_second_run_is_idempotent(session):
    IngestService(session).ingest("sample")
    first = JobService(session).search(JobFilter())[1]
    IngestService(session).ingest("sample")
    session.flush()
    assert JobService(session).search(JobFilter())[1] == first


# -- Auth -------------------------------------------------------------------
def test_auth_register_and_login(session):
    auth = AuthService(session)
    auth.register(email="u@example.com", password="password123")
    session.flush()
    token = auth.login(email="u@example.com", password="password123")
    assert token


def test_auth_duplicate_email_conflicts(session):
    auth = AuthService(session)
    auth.register(email="u@example.com", password="password123")
    session.flush()
    with pytest.raises(ConflictError):
        auth.register(email="u@example.com", password="password123")


def test_auth_wrong_password_rejected(session):
    auth = AuthService(session)
    auth.register(email="u@example.com", password="password123")
    session.flush()
    with pytest.raises(AuthenticationError):
        auth.login(email="u@example.com", password="nope")


def test_auth_default_role_is_viewer(session):
    auth = AuthService(session)
    user = auth.register(email="v@example.com", password="password123")
    assert user.role is UserRole.viewer


# -- Jobs -------------------------------------------------------------------
def test_job_service_get_missing_raises(session):
    with pytest.raises(NotFoundError):
        JobService(session).get(9999)


def test_job_export_csv_and_json(seeded):
    svc = JobService(seeded)
    csv_bytes = svc.export(JobFilter(), ExportFormat.csv)
    assert b"title" in csv_bytes.lower()
    json_bytes = svc.export(JobFilter(), ExportFormat.json)
    assert json_bytes.strip().startswith(b"[")


# -- Analytics --------------------------------------------------------------
def test_analytics_report_has_expected_shape(seeded):
    report = AnalyticsService(seeded).market_report()
    assert report.total_jobs > 0
    assert 0.0 <= report.remote_percentage <= 100.0
    skill_names = {s["name"] for s in report.top_skills}
    assert "Python" in skill_names
    assert report.salary_by_currency  # at least one currency


# -- Search -----------------------------------------------------------------
def test_semantic_search_finds_relevant_jobs(seeded):
    results = SearchService(seeded).search("remote python fastapi postgresql", top_k=5)
    assert results
    assert "score" in results[0]
    # The top hit should be python/backend-flavoured.
    joined = (results[0]["title"] + " " + " ".join(s["name"] for s in results[0]["skills"])).lower()
    assert "python" in joined or "backend" in joined


def test_semantic_search_empty_when_no_data(session):
    assert SearchService(session).search("anything") == []


# -- Recommendations --------------------------------------------------------
def test_recommendation_matches_resume(seeded):
    resume = "Backend engineer with 5 years of Python, FastAPI, PostgreSQL, Docker and AWS."
    result = RecommendationService(seeded).recommend(resume, top_k=5)
    assert result.years_experience == 5
    assert "Python" in result.resume_skills
    assert result.matches
    top = result.matches[0]
    assert 0.0 <= top.score <= 1.0
    assert isinstance(top.missing_skills, list)


def test_recommendation_salary_prediction(seeded):
    resume = "Senior Python engineer, FastAPI, PostgreSQL, AWS, Docker, Celery, Kubernetes."
    result = RecommendationService(seeded).recommend(resume, top_k=5)
    if result.salary_prediction:
        assert result.salary_prediction["expected_min"] <= result.salary_prediction["expected_max"]
