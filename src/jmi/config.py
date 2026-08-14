"""Application configuration.

All settings are loaded from environment variables (optionally an ``.env`` file)
using ``pydantic-settings``. Secrets never have production-safe defaults: the
application refuses to start in production with a placeholder secret key.
"""

from __future__ import annotations

import secrets
from enum import Enum
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
_PLACEHOLDER_SECRET = "change-me-to-a-long-random-string"
# A value the app refuses to run with in production, not a credential.
_PLACEHOLDER_ADMIN_PASSWORD = "change-me-strong-password"
_PLACEHOLDER_ADMIN_EMAIL = "admin@example.com"
_MIN_ADMIN_PASSWORD_LENGTH = 12


class Environment(str, Enum):
    """Deployment environment."""

    development = "development"
    staging = "staging"
    production = "production"


class Settings(BaseSettings):
    """Strongly-typed application settings.

    Every field maps to an environment variable prefixed with ``JMI_``.
    """

    model_config = SettingsConfigDict(
        env_prefix="JMI_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # -- Core ---------------------------------------------------------------
    env: Environment = Environment.development
    debug: bool = True

    # -- Security -----------------------------------------------------------
    secret_key: str = _PLACEHOLDER_SECRET
    access_token_ttl_minutes: int = Field(default=30, ge=1, le=60 * 24)
    algorithm: str = "HS256"

    # -- Database -----------------------------------------------------------
    database_url: str = "sqlite:///./data/runtime/jmi.sqlite3"

    # -- API ----------------------------------------------------------------
    api_host: str = "127.0.0.1"
    api_port: int = Field(default=8000, ge=1, le=65535)
    cors_origins: str = "http://localhost:3000"

    # -- Rate limiting ------------------------------------------------------
    rate_limit_requests: int = Field(default=120, ge=1)
    rate_limit_window_seconds: int = Field(default=60, ge=1)

    # -- Crawler ------------------------------------------------------------
    crawler_user_agent: str = "JMIBot/1.0 (+https://example.com/bot)"
    crawler_respect_robots: bool = True
    crawler_request_delay_seconds: float = Field(default=1.0, ge=0.0)
    crawler_max_retries: int = Field(default=3, ge=0, le=10)
    crawler_timeout_seconds: float = Field(default=20.0, gt=0)

    # -- Optional infrastructure -------------------------------------------
    redis_url: str = "redis://localhost:6379/0"
    embedding_model: str = "all-MiniLM-L6-v2"

    # -- Notifications ------------------------------------------------------
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = "alerts@example.com"
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # -- Bootstrap admin ----------------------------------------------------
    # The seed command creates this user with the ``admin`` role. Both values
    # are placeholders and are rejected outright in production (see
    # ``_enforce_production_secrets``) so a deployment can never silently ship
    # with the credentials printed in this repository.
    admin_email: str = _PLACEHOLDER_ADMIN_EMAIL
    admin_password: str = _PLACEHOLDER_ADMIN_PASSWORD

    # ---------------------------------------------------------------------
    @field_validator("cors_origins")
    @classmethod
    def _strip_origins(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def _enforce_production_secrets(self) -> Settings:
        """Refuse to start in production with any placeholder credential.

        Every credential that has a development-friendly default is checked
        here, not just the signing key: a deployment that sets a strong
        ``JMI_SECRET_KEY`` but forgets the bootstrap admin password would
        otherwise seed an ``admin``-role account whose password is published in
        this repository.
        """
        if self.env is not Environment.production:
            return self

        problems: list[str] = []
        if self.secret_key in (_PLACEHOLDER_SECRET, ""):
            problems.append("JMI_SECRET_KEY must be set to a strong random value")
        if self.admin_password in (_PLACEHOLDER_ADMIN_PASSWORD, ""):
            problems.append("JMI_ADMIN_PASSWORD must not be the placeholder value")
        elif len(self.admin_password) < _MIN_ADMIN_PASSWORD_LENGTH:
            problems.append(
                f"JMI_ADMIN_PASSWORD must be at least {_MIN_ADMIN_PASSWORD_LENGTH} characters"
            )
        if self.admin_email == _PLACEHOLDER_ADMIN_EMAIL:
            problems.append("JMI_ADMIN_EMAIL must not be the placeholder value")
        if "*" in self.cors_origin_list:
            problems.append("JMI_CORS_ORIGINS must not be '*' while credentials are allowed")
        if self.debug:
            problems.append("JMI_DEBUG must be false")

        if problems:
            raise ValueError("Unsafe production configuration: " + "; ".join(problems) + ".")
        return self

    # -- Derived helpers ----------------------------------------------------
    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.env is Environment.production

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    def ensure_runtime_dirs(self) -> None:
        """Create local runtime directories for SQLite / indexes / logs."""
        if self.is_sqlite and ":memory:" not in self.database_url:
            db_path = self.database_url.split("///", 1)[-1]
            Path(db_path).resolve().parent.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    """Return a cached ``Settings`` instance (singleton per process)."""
    settings = Settings()
    settings.ensure_runtime_dirs()
    return settings


def generate_secret_key() -> str:
    """Convenience helper used by the CLI to mint a production secret."""
    return secrets.token_urlsafe(48)
