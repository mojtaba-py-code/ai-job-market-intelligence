"""Tests for configuration and secret enforcement."""

from __future__ import annotations

import pytest

from jmi.config import Environment, Settings, generate_secret_key


def _production(**overrides):
    """Build production settings that are safe apart from the given overrides."""
    kwargs = {
        "env": Environment.production,
        "debug": False,
        "secret_key": generate_secret_key(),
        "admin_email": "ops@example.org",
        "admin_password": "a-real-strong-admin-password",
        **overrides,
    }
    return Settings(**kwargs)


def test_production_requires_strong_secret():
    with pytest.raises(ValueError, match="SECRET_KEY"):
        _production(secret_key="change-me-to-a-long-random-string")


def test_production_rejects_placeholder_admin_password():
    with pytest.raises(ValueError, match="ADMIN_PASSWORD"):
        _production(admin_password="change-me-strong-password")


def test_production_rejects_short_admin_password():
    with pytest.raises(ValueError, match="at least"):
        _production(admin_password="short")


def test_production_rejects_placeholder_admin_email():
    with pytest.raises(ValueError, match="ADMIN_EMAIL"):
        _production(admin_email="admin@example.com")


def test_production_rejects_wildcard_cors():
    with pytest.raises(ValueError, match="CORS_ORIGINS"):
        _production(cors_origins="*")


def test_production_rejects_debug():
    with pytest.raises(ValueError, match="DEBUG"):
        _production(debug=True)


def test_production_accepts_fully_configured_settings():
    settings = _production()
    assert settings.is_production is True


def test_placeholder_admin_credentials_are_fine_in_development():
    settings = Settings(env=Environment.development)
    assert settings.admin_password == "change-me-strong-password"


def test_cors_origins_parsed_into_list():
    settings = Settings(cors_origins="http://a.com, http://b.com ,http://c.com")
    assert settings.cors_origin_list == ["http://a.com", "http://b.com", "http://c.com"]


def test_sqlite_detection():
    assert Settings(database_url="sqlite:///./x.db").is_sqlite is True
    assert Settings(database_url="postgresql+psycopg://u@h/db").is_sqlite is False


def test_generated_secret_is_long_and_unique():
    assert generate_secret_key() != generate_secret_key()
    assert len(generate_secret_key()) >= 40
