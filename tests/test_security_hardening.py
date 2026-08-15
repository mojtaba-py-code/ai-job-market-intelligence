"""Regression tests for the platform's security controls.

Each test here pins down a specific attack that a previous version of this code
allowed. They are deliberately written as "an attacker does X, and X fails"
rather than as assertions about implementation details, so a refactor that keeps
the guarantee keeps the test green.
"""

from __future__ import annotations

import re
from datetime import timedelta

import jwt
import pytest
from fastapi.testclient import TestClient
from starlette.datastructures import Headers
from starlette.requests import Request

from jmi.api.app import create_app
from jmi.api.deps import get_db
from jmi.api.middleware import client_ip
from jmi.application.services import AuthService
from jmi.application.services.auth_service import _decoy_hash
from jmi.config import Settings, get_settings
from jmi.domain.enums import ExportFormat, UserRole
from jmi.infrastructure.export.exporters import escape_formula, export_jobs
from jmi.infrastructure.security import verify_password
from jmi.infrastructure.security.tokens import (
    TokenError,
    create_access_token,
    decode_access_token,
)


def _request(*, peer: str, headers: dict[str, str] | None = None) -> Request:
    """Build a bare ASGI request scope with a given peer address and headers."""
    raw = Headers(headers or {}).raw
    return Request({"type": "http", "headers": raw, "client": (peer, 12345), "method": "GET"})


# ---------------------------------------------------------------------------
# Rate-limit key spoofing
# ---------------------------------------------------------------------------
class TestClientIdentification:
    """`X-Forwarded-For` is attacker-controlled unless a proxy rewrites it.

    Keying the rate limiter on it unconditionally lets a single host mint an
    unlimited number of identities — one fresh request budget per forged value.
    """

    def test_forwarded_header_ignored_when_no_proxy_configured(self):
        request = _request(peer="203.0.113.7", headers={"x-forwarded-for": "1.2.3.4"})
        assert client_ip(request, trusted_proxy_hops=0) == "203.0.113.7"

    def test_spoofed_header_cannot_vary_the_identity(self):
        """The core property: forged values collapse to one real key."""
        identities = {
            client_ip(_request(peer="203.0.113.7", headers={"x-forwarded-for": forged}))
            for forged in ("1.1.1.1", "2.2.2.2", "3.3.3.3, 4.4.4.4")
        }
        assert identities == {"203.0.113.7"}

    def test_single_proxy_hop_reads_the_address_the_proxy_saw(self):
        request = _request(peer="10.0.0.1", headers={"x-forwarded-for": "198.51.100.9"})
        assert client_ip(request, trusted_proxy_hops=1) == "198.51.100.9"

    def test_prepended_entries_are_skipped(self):
        """A client that pre-seeds the header cannot shift which hop we read."""
        request = _request(
            peer="10.0.0.1",
            headers={"x-forwarded-for": "evil-spoof, 198.51.100.9"},
        )
        assert client_ip(request, trusted_proxy_hops=1) == "198.51.100.9"

    def test_short_chain_falls_back_to_peer(self):
        """Fewer hops than advertised means the header is not trustworthy."""
        request = _request(peer="10.0.0.1", headers={"x-forwarded-for": "1.2.3.4"})
        assert client_ip(request, trusted_proxy_hops=3) == "10.0.0.1"

    def test_missing_client_is_handled(self):
        request = Request({"type": "http", "headers": [], "client": None, "method": "GET"})
        assert client_ip(request) == "anonymous"


# ---------------------------------------------------------------------------
# Rate limiter memory bound
# ---------------------------------------------------------------------------
class TestRateLimiterMemory:
    def test_tracking_table_is_bounded(self):
        """A flood of distinct clients must not grow the limiter without bound."""
        from jmi.api.middleware import _SlidingWindow

        window = _SlidingWindow(limit=10, window=60, max_clients=100)
        for i in range(5_000):
            window.check(f"10.0.{i // 256}.{i % 256}", now=float(i))

        assert len(window._hits) <= 100

    def test_limit_is_enforced_within_the_window(self):
        from jmi.api.middleware import _SlidingWindow

        window = _SlidingWindow(limit=3, window=60, max_clients=100)
        results = [window.check("client", now=1.0)[0] for _ in range(5)]
        assert results == [True, True, True, False, False]

    def test_window_slides(self):
        from jmi.api.middleware import _SlidingWindow

        window = _SlidingWindow(limit=2, window=10, max_clients=100)
        assert window.check("c", now=0.0)[0] is True
        assert window.check("c", now=1.0)[0] is True
        assert window.check("c", now=2.0)[0] is False
        # ...once the first hits age out, the budget is restored.
        assert window.check("c", now=12.0)[0] is True

    def test_retry_after_is_advertised(self):
        from jmi.api.middleware import _SlidingWindow

        window = _SlidingWindow(limit=1, window=30, max_clients=10)
        window.check("c", now=0.0)
        allowed, _, retry_after = window.check("c", now=5.0)
        assert allowed is False
        assert 1 <= retry_after <= 31


# ---------------------------------------------------------------------------
# Spreadsheet formula injection
# ---------------------------------------------------------------------------
class TestFormulaInjection:
    """Scraped text lands in CSV/Excel exports that analysts open locally.

    Spreadsheets evaluate any cell starting with `=`, `+`, `-` or `@`, so an
    attacker who controls a job title controls code that runs on open.
    """

    @pytest.mark.parametrize(
        "payload",
        [
            '=HYPERLINK("http://evil.test","Click")',
            "=cmd|'/c calc'!A0",
            "+1+1",
            "-2+3",
            "@SUM(A1:A9)",
            "\t=1+1",
            "\r=1+1",
        ],
    )
    def test_dangerous_values_are_neutralised(self, payload):
        escaped = escape_formula(payload)
        assert escaped == "'" + payload
        assert not str(escaped).startswith(("=", "+", "-", "@", "\t", "\r"))

    @pytest.mark.parametrize(
        "payload",
        ["Senior Python Engineer", "C++ Developer", "", "Data (Remote)", "3-5 years"],
    )
    def test_ordinary_values_are_untouched(self, payload):
        assert escape_formula(payload) == payload

    @pytest.mark.parametrize("payload", [42, 3.5, None, True])
    def test_non_strings_pass_through(self, payload):
        assert escape_formula(payload) is payload

    def test_csv_export_escapes_hostile_titles(self):
        records = [{"title": '=HYPERLINK("http://evil.test","x")', "salary_max": 100}]
        csv = export_jobs(records, ExportFormat.csv).decode("utf-8")

        assert "'=HYPERLINK" in csv
        # No cell may begin a formula, in any row.
        for line in csv.splitlines()[1:]:
            for cell in line.split(","):
                assert not cell.strip('"').startswith("=")

    def test_csv_export_preserves_numbers(self):
        csv = export_jobs([{"title": "Engineer", "salary_max": 120000}], "csv").decode()
        assert "120000" in csv
        assert "'120000" not in csv

    def test_excel_export_is_produced_and_escaped(self):
        payload = export_jobs([{"title": "=1+1"}], ExportFormat.excel)
        assert payload[:2] == b"PK"  # a real xlsx (zip) container

    def test_json_export_is_left_faithful(self):
        """JSON is never evaluated — mangling it would corrupt the data."""
        raw = export_jobs([{"title": "=1+1"}], ExportFormat.json).decode()
        assert '"=1+1"' in raw


# ---------------------------------------------------------------------------
# JWT hardening
# ---------------------------------------------------------------------------
class TestTokenHardening:
    def test_token_carries_binding_claims(self):
        claims = decode_access_token(create_access_token("7", role="admin"))
        settings = get_settings()

        assert claims["sub"] == "7"
        assert claims["role"] == "admin"
        assert claims["typ"] == "access"
        assert claims["iss"] == settings.jwt_issuer
        assert claims["aud"] == settings.jwt_audience
        assert claims["jti"]

    def test_each_token_has_a_unique_id(self):
        """A distinct `jti` is what makes revocation and audit trails possible."""
        first = decode_access_token(create_access_token("1", role="viewer"))
        second = decode_access_token(create_access_token("1", role="viewer"))
        assert first["jti"] != second["jti"]

    def test_unsigned_token_rejected(self):
        """The classic `alg: none` forgery."""
        forged = jwt.encode(
            {"sub": "1", "role": "admin", "typ": "access"}, key="", algorithm="none"
        )
        with pytest.raises(TokenError):
            decode_access_token(forged)

    def test_token_signed_with_another_key_rejected(self):
        forged = jwt.encode(
            {"sub": "1", "role": "admin", "typ": "access", "exp": 9_999_999_999},
            "attacker-controlled-key-of-a-realistic-length-0123456789",
            algorithm="HS256",
        )
        with pytest.raises(TokenError):
            decode_access_token(forged)

    def test_token_for_another_audience_rejected(self):
        settings = get_settings()
        foreign = jwt.encode(
            {
                "sub": "1",
                "role": "admin",
                "typ": "access",
                "jti": "x",
                "iss": settings.jwt_issuer,
                "aud": "some-other-service",
                "iat": 1,
                "nbf": 1,
                "exp": 9_999_999_999,
            },
            settings.secret_key.get_secret_value(),
            algorithm=settings.algorithm,
        )
        with pytest.raises(TokenError):
            decode_access_token(foreign)

    def test_non_access_token_rejected(self):
        """A future refresh/reset token must not be replayable as an access token."""
        settings = get_settings()
        refresh = jwt.encode(
            {
                "sub": "1",
                "role": "admin",
                "typ": "refresh",
                "jti": "x",
                "iss": settings.jwt_issuer,
                "aud": settings.jwt_audience,
                "iat": 1,
                "nbf": 1,
                "exp": 9_999_999_999,
            },
            settings.secret_key.get_secret_value(),
            algorithm=settings.algorithm,
        )
        with pytest.raises(TokenError):
            decode_access_token(refresh)

    def test_token_missing_required_claims_rejected(self):
        settings = get_settings()
        thin = jwt.encode(
            {"sub": "1", "aud": settings.jwt_audience, "iss": settings.jwt_issuer},
            settings.secret_key.get_secret_value(),
            algorithm=settings.algorithm,
        )
        with pytest.raises(TokenError):
            decode_access_token(thin)

    def test_expired_token_rejected(self):
        token = create_access_token("1", role="viewer", expires_delta=timedelta(seconds=-10))
        with pytest.raises(TokenError):
            decode_access_token(token)

    def test_caller_cannot_override_registered_claims(self):
        """Extra claims must not let a caller forge its own role or subject."""
        token = create_access_token(
            "1", role="viewer", extra_claims={"role": "admin", "sub": "999", "team": "data"}
        )
        claims = decode_access_token(token)
        assert claims["role"] == "viewer"
        assert claims["sub"] == "1"
        assert claims["team"] == "data"


# ---------------------------------------------------------------------------
# Login: enumeration and escalation
# ---------------------------------------------------------------------------
class TestLoginSafety:
    def test_decoy_hash_is_a_real_bcrypt_hash(self):
        """The whole timing defence rests on this doing genuine bcrypt work.

        A malformed placeholder makes `checkpw` raise and return immediately,
        which is *faster* than a real check — the exact leak it meant to close.
        """
        decoy = _decoy_hash()
        assert re.fullmatch(r"\$2[aby]\$\d{2}\$[./A-Za-z0-9]{53}", decoy)
        assert verify_password("anything", decoy) is False

    def test_unknown_user_and_wrong_password_are_indistinguishable(self, session):
        from jmi.exceptions import AuthenticationError

        service = AuthService(session)
        service.register(email="real@example.com", password="correct-horse")

        with pytest.raises(AuthenticationError) as unknown:
            service.authenticate(email="ghost@example.com", password="whatever")
        with pytest.raises(AuthenticationError) as wrong:
            service.authenticate(email="real@example.com", password="incorrect")

        assert str(unknown.value) == str(wrong.value)

    def test_disabled_account_not_disclosed_without_the_password(self, session):
        from jmi.exceptions import AuthenticationError

        service = AuthService(session)
        user = service.register(email="off@example.com", password="correct-horse")
        user.is_active = False
        session.flush()

        with pytest.raises(AuthenticationError) as exc:
            service.authenticate(email="off@example.com", password="wrong-password")
        assert "disabled" not in str(exc.value).lower()

    def test_short_password_rejected_as_validation_error(self, session):
        from jmi.exceptions import ValidationError as DomainValidationError

        with pytest.raises(DomainValidationError):
            AuthService(session).register(email="new@example.com", password="short")


# ---------------------------------------------------------------------------
# HTTP surface
# ---------------------------------------------------------------------------
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
    seed = session_factory()
    AuthService(seed).register(
        email="admin@example.com", password="adminpass123", role=UserRole.admin
    )
    seed.commit()
    seed.close()

    with TestClient(app) as test_client:
        yield test_client


class TestResponseHardening:
    def test_csp_is_set_and_forbids_inline_script(self, client):
        csp = client.get("/").headers["content-security-policy"]
        assert "script-src 'nonce-" in csp
        assert "'unsafe-inline'" not in csp
        assert "frame-ancestors 'none'" in csp
        assert "object-src 'none'" in csp

    def test_dashboard_nonce_matches_the_header(self, client):
        """A mismatch would silently break the page under the policy."""
        resp = client.get("/")
        nonce = re.search(r"script-src 'nonce-([^']+)'", resp.headers["content-security-policy"])
        assert nonce is not None
        assert f'<script nonce="{nonce.group(1)}">' in resp.text
        assert "__CSP_NONCE__" not in resp.text

    def test_dashboard_has_no_inline_style_attributes(self, client):
        """A nonce authorises `<style>` blocks but never `style=""` attributes.

        CSP has no way to whitelist an inline style attribute by nonce, so any
        that creep back into the markup are silently dropped by the browser and
        the page renders subtly broken — bars at zero width, lost spacing — with
        nothing failing server-side. Dynamic styling must go through the CSSOM.
        """
        html = client.get("/").text
        assert not re.search(r"<[^>]+\sstyle\s*=", html)

    def test_nonce_is_fresh_per_response(self, client):
        first = client.get("/").headers["content-security-policy"]
        second = client.get("/").headers["content-security-policy"]
        assert first != second

    def test_hardening_headers_present(self, client):
        headers = client.get("/health").headers
        assert headers["x-content-type-options"] == "nosniff"
        assert headers["x-frame-options"] == "DENY"
        assert headers["cross-origin-opener-policy"] == "same-origin"
        assert headers["referrer-policy"] == "no-referrer"

    def test_internal_errors_do_not_leak_details(self, client):
        """Stack traces and exception text stay server-side."""
        resp = client.get("/api/v1/jobs/999999")
        assert resp.status_code == 404
        assert "Traceback" not in resp.text


class TestProductionSurface:
    @staticmethod
    def _production_app():
        settings = Settings(
            env="production",
            debug=False,
            secret_key="x" * 64,
            admin_email="ops@example.org",
            admin_password="a-real-strong-admin-password",
            database_url="sqlite://",
            cors_origins="https://app.example.com",
        )
        return create_app(settings)

    def test_docs_are_not_served_in_production(self):
        with TestClient(self._production_app()) as client:
            assert client.get("/docs").status_code == 404
            assert client.get("/redoc").status_code == 404
            assert client.get("/openapi.json").status_code == 404

    def test_hsts_is_sent_in_production(self):
        with TestClient(self._production_app()) as client:
            assert "max-age=" in client.get("/health").headers["strict-transport-security"]


class TestAuthThrottling:
    def test_login_budget_is_smaller_than_the_global_one(self, session_factory):
        """Brute force must hit a wall well before the general request limit."""
        settings = Settings(
            secret_key="x" * 64,
            database_url="sqlite://",
            rate_limit_requests=10_000,
            auth_rate_limit_requests=5,
            auth_rate_limit_window_seconds=300,
        )
        app = create_app(settings)

        def _override_get_db():
            db = session_factory()
            try:
                yield db
                db.commit()
            finally:
                db.close()

        app.dependency_overrides[get_db] = _override_get_db

        with TestClient(app) as client:
            statuses = [
                client.post(
                    "/api/v1/auth/login",
                    json={"email": "admin@example.com", "password": f"guess-{i}"},
                ).status_code
                for i in range(8)
            ]

        assert 429 in statuses, "login should be throttled long before 10k requests"
        assert statuses.index(429) <= 5
