"""End-to-end API tests via FastAPI's TestClient.

The app's ``get_db`` dependency is overridden to use the in-memory test engine,
so the full HTTP stack (routing, validation, auth, serialization) is exercised
without touching a real database.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from jmi.api.app import create_app
from jmi.api.deps import get_db
from jmi.application.services import AuthService, IngestService
from jmi.domain.enums import UserRole


@pytest.fixture()
def client(session_factory):
    app = create_app()

    def _override_get_db():
        db = session_factory()
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db

    # Seed an admin and demo data through the same factory the app now uses.
    seed_session = session_factory()
    AuthService(seed_session).register(
        email="admin@example.com", password="adminpass123", role=UserRole.admin
    )
    IngestService(seed_session).ingest("sample")
    seed_session.commit()
    seed_session.close()

    with TestClient(app) as test_client:
        yield test_client


def _admin_token(client: TestClient) -> str:
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "adminpass123"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def test_health_and_ready(client):
    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/api/v1/ready").json()["status"] == "ready"


def test_dashboard_served(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Job Market Intelligence" in resp.text


def test_security_headers_present(client):
    resp = client.get("/health")
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"


def test_list_sources(client):
    names = {s["name"] for s in client.get("/api/v1/sources").json()}
    assert {"sample", "html_demo"} <= names


def test_jobs_listing_and_filtering(client):
    resp = client.get("/api/v1/jobs", params={"limit": 5})
    body = resp.json()
    assert resp.status_code == 200
    assert body["total"] > 0
    assert len(body["items"]) <= 5

    filtered = client.get("/api/v1/jobs", params={"skill": "Python"}).json()
    assert filtered["total"] >= 1


def test_job_detail_and_404(client):
    listing = client.get("/api/v1/jobs").json()
    job_id = listing["items"][0]["id"]
    detail = client.get(f"/api/v1/jobs/{job_id}")
    assert detail.status_code == 200
    assert detail.json()["id"] == job_id
    assert client.get("/api/v1/jobs/999999").status_code == 404


def test_register_defaults_to_viewer_and_cannot_ingest(client):
    client.post(
        "/api/v1/auth/register",
        json={"email": "viewer@example.com", "password": "viewerpass123"},
    )
    token = client.post(
        "/api/v1/auth/login",
        json={"email": "viewer@example.com", "password": "viewerpass123"},
    ).json()["access_token"]

    resp = client.post(
        "/api/v1/crawler/ingest",
        json={"source": "sample"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


def test_ingest_requires_auth(client):
    assert client.post("/api/v1/crawler/ingest", json={"source": "sample"}).status_code == 401


def test_admin_can_ingest_and_view_history(client):
    token = _admin_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.post("/api/v1/crawler/ingest", json={"source": "html_demo"}, headers=headers)
    assert resp.status_code == 202, resp.text
    assert resp.json()["status"] == "completed"

    history = client.get("/api/v1/crawler/jobs", headers=headers).json()
    assert any(h["source"] == "html_demo" for h in history)


def test_semantic_search_endpoint(client):
    resp = client.post(
        "/api/v1/search/semantic",
        json={"query": "remote python fastapi postgresql", "top_k": 3},
    )
    assert resp.status_code == 200
    hits = resp.json()
    assert hits and "score" in hits[0]


def test_analytics_report_endpoint(client):
    report = client.get("/api/v1/analytics/report").json()
    assert report["total_jobs"] > 0
    assert isinstance(report["top_skills"], list)


def test_recommendations_require_auth(client):
    assert (
        client.post(
            "/api/v1/recommendations/match",
            json={"resume_text": "Python engineer with FastAPI and PostgreSQL experience."},
        ).status_code
        == 401
    )


def test_recommendations_flow(client):
    token = _admin_token(client)
    resp = client.post(
        "/api/v1/recommendations/match",
        json={
            "resume_text": "Backend engineer, 5 years Python, FastAPI, PostgreSQL, Docker, AWS.",
            "top_k": 5,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "Python" in body["resume_skills"]
    assert body["matches"]


def test_export_endpoint_requires_auth_and_returns_csv(client):
    assert client.get("/api/v1/jobs/export", params={"format": "csv"}).status_code == 401
    token = _admin_token(client)
    resp = client.get(
        "/api/v1/jobs/export",
        params={"format": "csv"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")


def test_validation_error_on_bad_payload(client):
    # password too short -> 422 from pydantic
    resp = client.post(
        "/api/v1/auth/register", json={"email": "x@example.com", "password": "short"}
    )
    assert resp.status_code == 422
