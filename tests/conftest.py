"""Shared pytest fixtures.

Every test runs against an isolated in-memory SQLite database, so the suite is
fast, hermetic and side-effect free. The API tests use FastAPI's dependency
override to bind the app to the same in-memory session factory.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

# Force a hermetic, in-memory configuration before anything imports settings.
os.environ.setdefault("JMI_ENV", "development")
os.environ.setdefault("JMI_SECRET_KEY", "test-secret-key-not-for-production-use-only")
os.environ.setdefault("JMI_DATABASE_URL", "sqlite://")  # in-memory
os.environ.setdefault("JMI_RATE_LIMIT_REQUESTS", "100000")

import pytest
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import Session, sessionmaker

from jmi.crawler import sources  # noqa: F401  register bundled sources
from jmi.infrastructure.db import models  # noqa: F401  register mappers
from jmi.infrastructure.db.base import Base


@pytest.fixture(autouse=True)
def _reset_process_state():
    """Clear process-wide caches between tests.

    Both the search index and the login throttle are deliberately global — they
    would count and cache nothing if scoped per request. Each test builds its own
    in-memory database, so leftovers would mean an index served against a corpus
    it was never built from, or a lockout inherited from an unrelated test.
    """
    from jmi.application.services.login_throttle import reset_login_throttle
    from jmi.search import cache as index_cache

    index_cache.invalidate()
    reset_login_throttle()
    yield
    index_cache.invalidate()
    reset_login_throttle()


@pytest.fixture()
def engine():
    """A shared in-memory SQLite engine (StaticPool keeps one connection)."""
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng)
    try:
        yield eng
    finally:
        Base.metadata.drop_all(eng)
        eng.dispose()


@pytest.fixture()
def session_factory(engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, class_=Session)


@pytest.fixture()
def session(session_factory) -> Iterator[Session]:
    db = session_factory()
    try:
        yield db
        db.commit()
    finally:
        db.close()
