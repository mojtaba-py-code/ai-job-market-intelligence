"""Ingestion use-case: crawl a source and persist enriched postings."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from ...crawler.pipeline import CrawlPipeline
from ...crawler.registry import registry
from ...domain.enums import CrawlJobStatus
from ...infrastructure.db.models import CrawlJob
from ...infrastructure.db.repositories import CrawlJobRepository, JobRepository
from ...logging import get_logger
from ...search import cache as index_cache

logger = get_logger(__name__)


class IngestService:
    """Runs the crawl pipeline for a named source and stores the results."""

    def __init__(self, session: Session, *, pipeline: CrawlPipeline | None = None) -> None:
        self.session = session
        self.jobs = JobRepository(session)
        self.crawl_jobs = CrawlJobRepository(session)
        self.pipeline = pipeline or CrawlPipeline()

    def ingest(
        self, source_name: str, *, since: str | None = None, limit: int | None = None
    ) -> CrawlJob:
        """Crawl *source_name* and upsert the postings. Returns the crawl record."""
        crawl_record = self.crawl_jobs.create(source_name)
        crawl_record.status = CrawlJobStatus.running
        crawl_record.started_at = datetime.now(UTC)
        self.session.flush()

        try:
            source = registry.create(source_name)
            result = self.pipeline.run(source, since=since, limit=limit)
            created = 0
            for posting in result.postings:
                _, was_created = self.jobs.upsert_from_posting(posting)
                created += int(was_created)

            crawl_record.status = CrawlJobStatus.completed
            crawl_record.fetched = result.fetched
            crawl_record.unique_count = result.unique
            crawl_record.duplicates = result.duplicates
        except Exception as exc:
            crawl_record.status = CrawlJobStatus.failed
            crawl_record.error = str(exc)
            crawl_record.finished_at = datetime.now(UTC)
            self.session.flush()
            logger.error("ingest_failed", source=source_name, error=str(exc))
            raise
        else:
            crawl_record.finished_at = datetime.now(UTC)
            self.session.flush()
            # An upsert can rewrite a posting's title, description or skills
            # without changing the row count or the highest id, so the search
            # index's fingerprint cannot detect it. Drop the cache explicitly.
            index_cache.invalidate()
            logger.info(
                "ingest_completed",
                source=source_name,
                fetched=crawl_record.fetched,
                unique=crawl_record.unique_count,
            )
            return crawl_record
