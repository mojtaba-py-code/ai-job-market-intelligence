"""Tests for configuration and secret enforcement."""

from __future__ import annotations

import pytest

from jmi.config import Environment, Settings, generate_secret_key


def test_production_requires_strong_secret():
    with pytest.raises(ValueError, match="SECRET_KEY"):
        Settings(env=Environment.production, secret_key="change-me-to-a-long-random-string")


def test_production_accepts_strong_secret():
    settings = Settings(env=Environment.production, secret_key=generate_secret_key())
    assert settings.is_production is True


def test_cors_origins_parsed_into_list():
    settings = Settings(cors_origins="http://a.com, http://b.com ,http://c.com")
    assert settings.cors_origin_list == ["http://a.com", "http://b.com", "http://c.com"]


def test_sqlite_detection():
    assert Settings(database_url="sqlite:///./x.db").is_sqlite is True
    assert Settings(database_url="postgresql+psycopg://u@h/db").is_sqlite is False


def test_generated_secret_is_long_and_unique():
    assert generate_secret_key() != generate_secret_key()
    assert len(generate_secret_key()) >= 40
