"""Regression tests for resource-exhaustion and disclosure defences.

Companion to ``test_security_hardening.py``, covering the controls that bound
what a single request can cost the server and what an unauthenticated caller can
learn about it. Same style: each test states an attack and asserts it fails.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from jmi.api.app import create_app
from jmi.api.deps import get_db
from jmi.application.services import AuthService, IngestService, SearchService
from jmi.application.services.login_throttle import LoginThrottle
from jmi.config import Settings
from jmi.exceptions import AuthenticationError, RateLimitedError
from jmi.search import cache as index_cache


def _settings(**overrides) -> Settings:
    defaults = {
        "secret_key": "x" * 64,
        "database_url": "sqlite://",
        "rate_limit_requests": 10_000,
    }
    return Settings(**{**defaults, **overrides})


def _app(session_factory, settings: Settings):
    app = create_app(settings)

    def _override_get_db():
        db = session_factory()
        try:
            yield db
            db.commit()
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    return app


@pytest.fixture()
def client(session_factory):
    with TestClient(_app(session_factory, _settings())) as test_client:
        yield test_client


# ---------------------------------------------------------------------------
# Request body size
# ---------------------------------------------------------------------------
class TestRequestBodyLimit:
    """Pydantic field caps only apply once the whole body is already buffered."""

    def test_oversized_body_is_refused(self, session_factory):
        app = _app(session_factory, _settings(max_request_body_bytes=2048))
        with TestClient(app) as client:
            resp = client.post(
                "/api/v1/search/semantic",
                json={"query": "x" * 50_000, "top_k": 5},
            )
        assert resp.status_code == 413

    def test_ordinary_body_still_accepted(self, session_factory):
        app = _app(session_factory, _settings(max_request_body_bytes=1024 * 1024))
        with TestClient(app) as client:
            resp = client.post(
                "/api/v1/search/semantic",
                json={"query": "remote python", "top_k": 5},
            )
        assert resp.status_code == 200

    def test_malformed_content_length_is_refused(self, session_factory):
        """A length we cannot parse is not something to guess about."""
        app = _app(session_factory, _settings(max_request_body_bytes=2048))
        with TestClient(app) as client:
            resp = client.request(
                "POST",
                "/api/v1/search/semantic",
                content=b'{"query":"hi","top_k":5}',
                headers={"Content-Length": "not-a-number", "Content-Type": "application/json"},
            )
        assert resp.status_code == 413


# ---------------------------------------------------------------------------
# Search index rebuild amplification
# ---------------------------------------------------------------------------
class TestSearchIndexCaching:
    """Rebuilding the index per request is unauthenticated CPU amplification.

    One small HTTP call previously fitted the embedder over the entire corpus
    and embedded every document, so cost scaled with the table while the request
    stayed the same size.
    """

    def test_corpus_is_embedded_once_not_per_request(self, session):
        IngestService(session).ingest("sample")
        session.commit()

        builds = 0
        original = SearchService._build_index

        def counting_build(self):
            nonlocal builds
            builds += 1
            return original(self)

        with patch.object(SearchService, "_build_index", counting_build):
            for _ in range(5):
                SearchService(session).search("python", top_k=3)

        assert builds == 1

    def test_ingestion_invalidates_the_cached_index(self, session):
        IngestService(session).ingest("sample")
        session.commit()
        SearchService(session).search("python", top_k=3)
        assert index_cache._index is not None

        # An upsert can rewrite a posting in place without changing the row
        # count or the highest id, so the fingerprint alone cannot see it.
        IngestService(session).ingest("sample")
        assert index_cache._index is None

    def test_new_postings_are_picked_up(self, session):
        IngestService(session).ingest("sample")
        session.commit()
        assert SearchService(session).search("python", top_k=5)

    def test_results_still_carry_scores(self, session):
        IngestService(session).ingest("sample")
        session.commit()
        hits = SearchService(session).search("python", top_k=5)
        assert hits
        assert all("score" in hit for hit in hits)

    def test_empty_corpus_is_handled(self, session):
        assert SearchService(session).search("anything") == []


# ---------------------------------------------------------------------------
# Distributed brute force
# ---------------------------------------------------------------------------
class TestLoginLockout:
    """The per-address limiter cannot see guesses spread across many addresses."""

    @staticmethod
    def _throttle(**overrides) -> LoginThrottle:
        return LoginThrottle(_settings(**overrides))

    def test_account_locks_after_repeated_failures(self, session):
        service = AuthService(session)
        service.register(email="target@example.com", password="correct-horse")
        throttle = self._throttle(login_max_failures=3)

        with patch(
            "jmi.application.services.auth_service.get_login_throttle", return_value=throttle
        ):
            for _ in range(3):
                with pytest.raises(AuthenticationError):
                    service.authenticate(email="target@example.com", password="wrong")

            # Budget spent: even the correct password is refused for now.
            with pytest.raises(RateLimitedError):
                service.authenticate(email="target@example.com", password="correct-horse")

    def test_unknown_accounts_are_throttled_identically(self, session):
        """Otherwise the lockout itself becomes an account-existence oracle."""
        service = AuthService(session)
        throttle = self._throttle(login_max_failures=2)

        with patch(
            "jmi.application.services.auth_service.get_login_throttle", return_value=throttle
        ):
            for _ in range(2):
                with pytest.raises(AuthenticationError):
                    service.authenticate(email="ghost@example.com", password="wrong")
            with pytest.raises(RateLimitedError):
                service.authenticate(email="ghost@example.com", password="wrong")

    def test_success_clears_the_failure_history(self, session):
        """So nobody can keep the real owner locked out by failing on their behalf."""
        service = AuthService(session)
        service.register(email="owner@example.com", password="correct-horse")
        throttle = self._throttle(login_max_failures=3)

        with patch(
            "jmi.application.services.auth_service.get_login_throttle", return_value=throttle
        ):
            for _ in range(2):
                with pytest.raises(AuthenticationError):
                    service.authenticate(email="owner@example.com", password="wrong")
            service.authenticate(email="owner@example.com", password="correct-horse")

        assert throttle.is_locked("owner@example.com") is False

    def test_lockout_is_case_insensitive(self):
        throttle = self._throttle(login_max_failures=1)
        throttle.record_failure("User@Example.com")
        assert throttle.is_locked("  user@example.com  ") is True

    def test_failures_age_out_of_the_window(self):
        throttle = self._throttle(login_max_failures=2, login_failure_window_seconds=60)
        throttle.record_failure("a@b.com", now=0.0)
        throttle.record_failure("a@b.com", now=1.0)
        assert throttle.is_locked("a@b.com", now=2.0) is True
        assert throttle.is_locked("a@b.com", now=120.0) is False

    def test_retry_after_is_advertised(self):
        throttle = self._throttle(login_max_failures=1, login_failure_window_seconds=60)
        throttle.record_failure("a@b.com", now=0.0)
        assert 1 <= throttle.retry_after("a@b.com", now=10.0) <= 61

    def test_tracking_table_is_bounded(self):
        """A flood of distinct identifiers must not grow the table without limit."""
        throttle = self._throttle(login_max_tracked_accounts=128)
        for i in range(3_000):
            throttle.record_failure(f"user{i}@example.com")
        assert len(throttle._failures) <= 128


# ---------------------------------------------------------------------------
# Information disclosure
# ---------------------------------------------------------------------------
class TestInformationDisclosure:
    @staticmethod
    def _production_client():
        settings = Settings(
            env="production",
            debug=False,
            secret_key="x" * 64,
            admin_email="ops@example.org",
            admin_password="a-real-strong-admin-password",
            database_url="sqlite://",
            cors_origins="https://app.example.com",
        )
        return TestClient(create_app(settings))

    def test_health_hides_the_version_in_production(self):
        """A public endpoint naming the build lets anyone match it to advisories."""
        with self._production_client() as client:
            body = client.get("/health").json()
        assert body["status"] == "ok"
        assert "version" not in body

    def test_health_reports_the_version_outside_production(self, client):
        assert "version" in client.get("/health").json()

    def test_server_banner_does_not_name_the_software(self, client):
        assert "uvicorn" not in client.get("/health").headers.get("server", "").lower()

    def test_api_responses_are_not_cached(self, client):
        """Job data and exports must not linger in shared or browser caches."""
        cache_control = client.get("/api/v1/jobs?limit=1").headers["cache-control"]
        assert "no-store" in cache_control
        assert "private" in cache_control

    def test_dashboard_is_still_cacheable(self, client):
        """The no-store rule is scoped to the API, not the static page."""
        assert "no-store" not in client.get("/").headers.get("cache-control", "")
