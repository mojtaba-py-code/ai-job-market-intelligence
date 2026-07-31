"""APScheduler-based crawl scheduler."""

from __future__ import annotations

from collections.abc import Callable

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from ...logging import get_logger

logger = get_logger(__name__)


class CrawlScheduler:
    """Thin wrapper around APScheduler for periodic crawl jobs."""

    def __init__(self, scheduler: BackgroundScheduler | None = None) -> None:
        self._scheduler = scheduler or BackgroundScheduler(timezone="UTC")

    def add_interval_job(
        self,
        func: Callable[[], None],
        *,
        minutes: int,
        job_id: str,
        replace_existing: bool = True,
    ) -> None:
        self._scheduler.add_job(
            func,
            trigger=IntervalTrigger(minutes=minutes),
            id=job_id,
            replace_existing=replace_existing,
            max_instances=1,
            coalesce=True,
        )
        logger.info("scheduled_job_added", job_id=job_id, minutes=minutes)

    def start(self) -> None:
        if not self._scheduler.running:
            self._scheduler.start()
            logger.info("scheduler_started")

    def shutdown(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("scheduler_stopped")

    @property
    def jobs(self) -> list[str]:
        return [job.id for job in self._scheduler.get_jobs()]


def build_scheduler() -> CrawlScheduler:
    return CrawlScheduler()
