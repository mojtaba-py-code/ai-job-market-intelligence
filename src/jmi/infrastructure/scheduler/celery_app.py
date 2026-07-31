"""Optional Celery application for distributed background crawling.

Activated by the ``jmi[tasks]`` extra (Celery + Redis). The task simply reuses
:class:`~jmi.application.services.ingest_service.IngestService`, so the crawl
logic is identical whether it runs inline (APScheduler) or on a worker.

Run a worker with::

    celery -A jmi.infrastructure.scheduler.celery_app.celery_app worker --loglevel=info
"""

from __future__ import annotations

from ...config import get_settings

try:
    from celery import Celery
except ImportError as exc:  # pragma: no cover - optional dependency
    raise ImportError(
        "Celery is not installed. Install the tasks extra: pip install '.[tasks]'"
    ) from exc

_settings = get_settings()

celery_app = Celery(
    "jmi",
    broker=_settings.redis_url,
    backend=_settings.redis_url,
)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    worker_max_tasks_per_child=100,
)


@celery_app.task(name="jmi.ingest_source", bind=True, max_retries=3, default_retry_delay=30)
def ingest_source(
    self, source_name: str, since: str | None = None, limit: int | None = None
) -> dict:
    """Celery task: crawl and persist a single source."""
    from ...application.services import IngestService
    from ...infrastructure.db.session import create_all, session_scope

    try:
        create_all()
        with session_scope() as session:
            record = IngestService(session).ingest(source_name, since=since, limit=limit)
            return {
                "source": record.source,
                "status": record.status.value,
                "fetched": record.fetched,
                "unique": record.unique_count,
                "duplicates": record.duplicates,
            }
    except Exception as exc:  # pragma: no cover - worker retry path
        raise self.retry(exc=exc) from exc
