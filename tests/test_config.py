"""Tests for configuration, secret handling and production hardening."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from jmi.config import Environment, Settings, generate_secret_key


def _production(**overrides) -> Settings:
    """Build production settings that are safe apart from the given overrides."""
    defaults = {
        "env": Environment.production,
        "debug": False,
        "secret_key": generate_secret_key(),
        "admin_email": "ops@example.org",
        "admin_password": "a-real-strong-admin-password",
    }
    return Settings(**{**defaults, **overrides})


# -- Production hardening ---------------------------------------------------
def test_production_requires_strong_secret():
    with pytest.raises(ValidationError, match="SECRET_KEY"):
        _production(secret_key="change-me-to-a-long-random-string")


def test_production_rejects_short_secret():
    with pytest.raises(ValidationError, match="SECRET_KEY"):
        _production(secret_key="tooshort")


def test_production_rejects_placeholder_admin_password():
    with pytest.raises(ValidationError, match="ADMIN_PASSWORD"):
        _production(admin_password="change-me-strong-password")


def test_production_rejects_short_admin_password():
    with pytest.raises(ValidationError, match="at least"):
        _production(admin_password="short")


def test_production_rejects_placeholder_admin_email():
    with pytest.raises(ValidationError, match="ADMIN_EMAIL"):
        _production(admin_email="admin@example.com")


def test_production_rejects_debug():
    with pytest.raises(ValidationError, match="DEBUG"):
        _production(debug=True)


def test_production_reports_every_problem_at_once():
    """An operator should fix one round of problems, not rediscover them singly."""
    with pytest.raises(ValidationError) as exc:
        _production(secret_key="change-me-to-a-long-random-string", debug=True)
    message = str(exc.value)
    assert "SECRET_KEY" in message
    assert "DEBUG" in message


def test_production_accepts_fully_configured_settings():
    assert _production().is_production is True


def test_development_tolerates_placeholders():
    """Local development must stay frictionless — the guards are production-only."""
    assert Settings(env=Environment.development).is_production is False


# -- Secrets are not printable ----------------------------------------------
def test_secrets_are_masked_in_repr_and_dump():
    """A stray log line or traceback must never carry the real value."""
    secret = generate_secret_key()
    settings = _production(secret_key=secret, smtp_password="smtp-pw")

    assert secret not in repr(settings)
    assert secret not in str(settings)
    assert secret not in str(settings.model_dump())
    assert "smtp-pw" not in repr(settings)

    # ...but the value is still reachable at the point of use.
    assert settings.secret_key.get_secret_value() == secret


# -- JWT algorithm allowlist ------------------------------------------------
@pytest.mark.parametrize("algorithm", ["none", "None", "RS256", "ES256", "HS128"])
def test_unsafe_jwt_algorithms_rejected(algorithm):
    with pytest.raises(ValidationError, match="ALGORITHM"):
        Settings(algorithm=algorithm)


def test_jwt_algorithm_normalised():
    assert Settings(algorithm="hs512").algorithm == "HS512"


# -- CORS -------------------------------------------------------------------
def test_wildcard_cors_with_credentials_is_rejected():
    """`*` plus credentials lets any site read authenticated responses."""
    with pytest.raises(ValidationError, match="CORS"):
        Settings(cors_origins="*", cors_allow_credentials=True)


def test_production_rejects_wildcard_cors_with_credentials():
    with pytest.raises(ValidationError, match="CORS_ORIGINS"):
        _production(cors_origins="*")


def test_wildcard_cors_allowed_without_credentials():
    """A public read-only API may serve any origin, as long as it is anonymous."""
    settings = Settings(cors_origins="*", cors_allow_credentials=False)
    assert settings.cors_origin_list == ["*"]


def test_placeholder_admin_credentials_are_fine_in_development():
    settings = Settings(env=Environment.development)
    assert settings.admin_password.get_secret_value() == "change-me-strong-password"


def test_cors_origins_parsed_into_list():
    settings = Settings(cors_origins="http://a.com, http://b.com ,http://c.com")
    assert settings.cors_origin_list == ["http://a.com", "http://b.com", "http://c.com"]


# -- Docs exposure ----------------------------------------------------------
def test_docs_hidden_in_production_by_default():
    assert _production().expose_docs is False


def test_docs_visible_in_development_by_default():
    assert Settings().expose_docs is True


def test_docs_can_be_forced_on_in_production():
    assert _production(docs_enabled=True).expose_docs is True


# -- Misc -------------------------------------------------------------------
def test_sqlite_detection():
    assert Settings(database_url="sqlite:///./x.db").is_sqlite is True
    assert Settings(database_url="postgresql+psycopg://u@h/db").is_sqlite is False


def test_proxy_hops_default_to_untrusted():
    """Trusting X-Forwarded-For must be an explicit operator decision."""
    assert Settings().trusted_proxy_hops == 0


def test_generated_secret_is_long_and_unique():
    assert generate_secret_key() != generate_secret_key()
    assert len(generate_secret_key()) >= 40
