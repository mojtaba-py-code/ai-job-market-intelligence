"""Engine and session management.

A single cached engine is created per process. SQLite gets the settings it needs
to behave well under an API server (foreign keys on, cross-thread sharing).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from ...config import Settings, get_settings


@lru_cache
def get_engine(database_url: str | None = None) -> Engine:
    """Return a cached SQLAlchemy engine for the configured database."""
    settings: Settings = get_settings()
    url = database_url or settings.database_url

    connect_args: dict = {}
    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False

    engine = create_engine(
        url,
        echo=False,
        future=True,
        pool_pre_ping=True,
        connect_args=connect_args,
    )

    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, _record):  # pragma: no cover - trivial
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


@lru_cache
def get_sessionmaker(database_url: str | None = None) -> sessionmaker[Session]:
    """Return a cached session factory bound to the engine."""
    return sessionmaker(bind=get_engine(database_url), expire_on_commit=False, class_=Session)


@contextmanager
def session_scope(database_url: str | None = None) -> Iterator[Session]:
    """Provide a transactional scope around a series of operations."""
    factory = get_sessionmaker(database_url)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def create_all(database_url: str | None = None) -> None:
    """Create all tables (used for tests and quick-start; Alembic in prod)."""
    from . import models  # noqa: F401  ensure models are imported/registered
    from .base import Base

    Base.metadata.create_all(get_engine(database_url))
