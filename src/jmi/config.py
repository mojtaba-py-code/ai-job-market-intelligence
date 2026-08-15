"""Application configuration.

All settings are loaded from environment variables (optionally an ``.env`` file)
using ``pydantic-settings``.

Two rules govern this module:

* **Secrets are never plain strings.** Every credential is a ``SecretStr``, so an
  accidental ``print(settings)``, ``repr()`` in a traceback, or
  ``settings.model_dump()`` in a log line yields ``**********`` instead of the
  real value. Reading one requires an explicit ``.get_secret_value()``, which
  makes every use site greppable during review.
* **Unsafe production configurations refuse to boot.** A placeholder secret key,
  a default admin password, or a wildcard CORS policy combined with credentialed
  requests are all fatal in production rather than silently insecure.
"""

from __future__ import annotations

import secrets
from enum import Enum
from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
_PLACEHOLDER_SECRET = "change-me-to-a-long-random-string"
# Values the app refuses to run with in production, not credentials.
_PLACEHOLDER_ADMIN_PASSWORD = "change-me-strong-password"
_PLACEHOLDER_ADMIN_EMAIL = "admin@example.com"
_MIN_ADMIN_PASSWORD_LENGTH = 12
_MIN_PRODUCTION_SECRET_LENGTH = 32

#: JWT algorithms we are willing to sign and verify with. Anything outside this
#: set (notably ``none``, and the asymmetric families, which would let a token
#: signed with the *public* key be accepted) is rejected at startup.
ALLOWED_JWT_ALGORITHMS = frozenset({"HS256", "HS384", "HS512"})


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
    secret_key: SecretStr = SecretStr(_PLACEHOLDER_SECRET)
    access_token_ttl_minutes: int = Field(default=30, ge=1, le=60 * 24)
    algorithm: str = "HS256"
    jwt_issuer: str = "jmi-platform"
    jwt_audience: str = "jmi-api"

    #: Number of reverse proxies in front of the app. ``X-Forwarded-For`` is
    #: only trusted when this is greater than zero — see
    #: ``jmi.api.middleware.client_ip``.
    trusted_proxy_hops: int = Field(default=0, ge=0, le=8)

    #: Expose ``/docs``, ``/redoc`` and ``/openapi.json``. ``None`` means "use
    #: the safe default for this environment" (off in production).
    docs_enabled: bool | None = None

    # -- Database -----------------------------------------------------------
    database_url: str = "sqlite:///./data/runtime/jmi.sqlite3"

    # -- API ----------------------------------------------------------------
    api_host: str = "127.0.0.1"
    api_port: int = Field(default=8000, ge=1, le=65535)
    cors_origins: str = "http://localhost:3000"
    cors_allow_credentials: bool = True

    # -- Rate limiting ------------------------------------------------------
    rate_limit_requests: int = Field(default=120, ge=1)
    rate_limit_window_seconds: int = Field(default=60, ge=1)
    #: A much tighter budget for credential-accepting endpoints, so the global
    #: limit above cannot be used as a password-guessing allowance.
    auth_rate_limit_requests: int = Field(default=10, ge=1)
    auth_rate_limit_window_seconds: int = Field(default=300, ge=1)
    #: Upper bound on distinct clients tracked by the in-memory limiter. Keeps
    #: a flood of unique source addresses from exhausting memory.
    rate_limit_max_tracked_clients: int = Field(default=50_000, ge=128)

    # -- Crawler ------------------------------------------------------------
    crawler_user_agent: str = "JMIBot/1.0 (+https://example.com/bot)"
    crawler_respect_robots: bool = True
    crawler_request_delay_seconds: float = Field(default=1.0, ge=0.0)
    crawler_max_retries: int = Field(default=3, ge=0, le=10)
    crawler_timeout_seconds: float = Field(default=20.0, gt=0)
    #: Cap on a single downloaded response. Prevents a hostile or broken source
    #: from streaming an unbounded body into memory.
    crawler_max_response_bytes: int = Field(default=8 * 1024 * 1024, ge=1024)

    # -- Optional infrastructure -------------------------------------------
    redis_url: str = "redis://localhost:6379/0"
    embedding_model: str = "all-MiniLM-L6-v2"

    # -- Notifications ------------------------------------------------------
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: SecretStr = SecretStr("")
    smtp_from: str = "alerts@example.com"
    telegram_bot_token: SecretStr = SecretStr("")
    telegram_chat_id: str = ""

    # -- Bootstrap admin ----------------------------------------------------
    # The seed command creates this user with the ``admin`` role. Both values
    # are placeholders and are rejected outright in production (see
    # ``_enforce_production_hardening``) so a deployment can never silently ship
    # with the credentials printed in this repository.
    admin_email: str = _PLACEHOLDER_ADMIN_EMAIL
    admin_password: SecretStr = SecretStr(_PLACEHOLDER_ADMIN_PASSWORD)

    # ---------------------------------------------------------------------
    @field_validator("cors_origins")
    @classmethod
    def _strip_origins(cls, value: str) -> str:
        return value.strip()

    @field_validator("algorithm")
    @classmethod
    def _check_algorithm(cls, value: str) -> str:
        """Reject ``none`` and any algorithm outside the symmetric allowlist."""
        normalised = value.strip().upper()
        if normalised not in ALLOWED_JWT_ALGORITHMS:
            allowed = ", ".join(sorted(ALLOWED_JWT_ALGORITHMS))
            raise ValueError(f"JMI_ALGORITHM must be one of: {allowed} (got {value!r}).")
        return normalised

    @model_validator(mode="after")
    def _enforce_production_hardening(self) -> Settings:
        """Fail fast on configurations that are unsafe to expose publicly.

        Every credential with a development-friendly default is checked, not
        just the signing key: a deployment that sets a strong ``JMI_SECRET_KEY``
        but forgets the bootstrap admin password would otherwise seed an
        ``admin``-role account whose password is published in this repository.

        Problems are collected and reported together, so an operator fixes one
        round of them rather than rediscovering the next on each restart.
        """
        # A wildcard origin combined with credentialed requests lets *any* site
        # read authenticated responses: Starlette echoes the caller's Origin
        # back when credentials are allowed, so `*` stops being an
        # anonymous-only policy. This one is fatal in every environment, since
        # it is just as exploitable in staging.
        if "*" in self.cors_origin_list and self.cors_allow_credentials:
            raise ValueError(
                "JMI_CORS_ORIGINS='*' cannot be combined with "
                "JMI_CORS_ALLOW_CREDENTIALS=true — it would let any origin read "
                "authenticated responses. List explicit origins, or set "
                "JMI_CORS_ALLOW_CREDENTIALS=false for a public read-only API."
            )

        if self.env is not Environment.production:
            return self

        problems: list[str] = []
        secret = self.secret_key.get_secret_value()
        if secret in (_PLACEHOLDER_SECRET, ""):
            problems.append("JMI_SECRET_KEY must be set to a strong random value")
        elif len(secret) < _MIN_PRODUCTION_SECRET_LENGTH:
            problems.append(
                f"JMI_SECRET_KEY must be at least {_MIN_PRODUCTION_SECRET_LENGTH} "
                "characters (generate one with `python -m jmi secret-key`)"
            )

        admin_password = self.admin_password.get_secret_value()
        if admin_password in (_PLACEHOLDER_ADMIN_PASSWORD, ""):
            problems.append("JMI_ADMIN_PASSWORD must not be the placeholder value")
        elif len(admin_password) < _MIN_ADMIN_PASSWORD_LENGTH:
            problems.append(
                f"JMI_ADMIN_PASSWORD must be at least {_MIN_ADMIN_PASSWORD_LENGTH} characters"
            )

        if self.admin_email == _PLACEHOLDER_ADMIN_EMAIL:
            problems.append("JMI_ADMIN_EMAIL must not be the placeholder value")
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

    @property
    def expose_docs(self) -> bool:
        """Whether the OpenAPI docs should be served.

        Interactive docs advertise every endpoint and payload shape, so they are
        off by default in production unless explicitly re-enabled.
        """
        if self.docs_enabled is None:
            return not self.is_production
        return self.docs_enabled

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
