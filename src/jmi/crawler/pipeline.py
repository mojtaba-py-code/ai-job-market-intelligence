"""Crawl pipeline: fetch -> clean -> enrich (skills) -> de-duplicate.

The pipeline is persistence-agnostic. It turns a source into a list of enriched,
unique :class:`JobPosting` objects plus a :class:`CrawlResult` summary. The
application layer (``IngestService``) is responsible for storing them.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..logging import get_logger
from ..nlp.cleaner import clean_text
from ..nlp.dedup import DuplicateDetector
from ..nlp.skills import SkillExtractor, get_default_extractor
from .base import BaseSource

logger = get_logger(__name__)


@dataclass(slots=True)
class CrawlResult:
    """Summary statistics for a single crawl run."""

    source: str
    fetched: int = 0
    duplicates: int = 0
    unique: int = 0
    postings: list = field(default_factory=list)


class CrawlPipeline:
    """Runs a source through cleaning, skill extraction and de-duplication."""

    def __init__(
        self,
        *,
        extractor: SkillExtractor | None = None,
        detector: DuplicateDetector | None = None,
    ) -> None:
        self._extractor = extractor or get_default_extractor()
        self._detector = detector or DuplicateDetector()

    def _enrich(self, posting):
        posting.description = clean_text(posting.description, keep_newlines=True)
        # Extract from title + description so short titles still contribute.
        text = f"{posting.title}\n{posting.description}"
        posting.skills = self._extractor.extract(text)
        return posting

    def run(
        self, source: BaseSource, *, since: str | None = None, limit: int | None = None
    ) -> CrawlResult:
        result = CrawlResult(source=source.name)
        for posting in source.fetch(since=since, limit=limit):
            result.fetched += 1
            posting = self._enrich(posting)
            if self._detector.is_duplicate(posting):
                result.duplicates += 1
                continue
            self._detector.add(posting)
            result.postings.append(posting)
        result.unique = len(result.postings)
        logger.info(
            "crawl_complete",
            source=source.name,
            fetched=result.fetched,
            unique=result.unique,
            duplicates=result.duplicates,
        )
        return result
