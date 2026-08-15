"""Database bootstrap: create tables, an admin user and demo data.

Run with ``jmi seed`` (or ``python -m jmi seed``). Idempotent: it will not
duplicate the admin user or re-insert postings that already exist.
"""

from __future__ import annotations

from .application.services import AuthService, IngestService
from .config import get_settings
from .crawler import sources  # noqa: F401  register bundled sources
from .crawler.registry import registry
from .domain.enums import UserRole
from .infrastructure.db.session import create_all, session_scope
from .logging import configure_logging, get_logger

logger = get_logger(__name__)


def seed(*, with_demo_data: bool = True) -> None:
    """Create schema, ensure an admin user, and optionally ingest demo sources."""
    settings = get_settings()
    configure_logging(debug=settings.debug)
    create_all()

    with session_scope() as session:
        auth = AuthService(session)
        if auth.users.get_by_email(settings.admin_email) is None:
            auth.register(
                email=settings.admin_email,
                password=settings.admin_password.get_secret_value(),
                role=UserRole.admin,
            )
            logger.info("admin_created", email=settings.admin_email)
        else:
            logger.info("admin_exists", email=settings.admin_email)

    if not with_demo_data:
        return

    with session_scope() as session:
        ingest = IngestService(session)
        for source_name in registry.names():
            record = ingest.ingest(source_name)
            logger.info(
                "seeded_source",
                source=source_name,
                unique=record.unique_count,
                duplicates=record.duplicates,
            )


if __name__ == "__main__":  # pragma: no cover
    seed()
