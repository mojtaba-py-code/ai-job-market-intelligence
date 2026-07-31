"""Base classes for pluggable job sources."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass

from ..domain.entities import JobPosting
from .http_client import HttpClient


@dataclass(frozen=True, slots=True)
class SourceMetadata:
    """Declarative description of a source, used by the registry and dashboard."""

    name: str
    display_name: str
    base_url: str
    supports_incremental: bool = True
    requires_javascript: bool = False


class BaseSource(ABC):
    """A single job portal integration.

    Concrete sources implement :meth:`fetch`, yielding domain
    :class:`JobPosting` objects. The pipeline is responsible for cleaning,
    skill extraction, de-duplication and persistence — sources only produce
    raw-but-structured postings, keeping each integration small and testable.
    """

    metadata: SourceMetadata

    def __init__(self, http_client: HttpClient | None = None) -> None:
        self._http = http_client

    @property
    def name(self) -> str:
        return self.metadata.name

    @property
    def http(self) -> HttpClient:
        if self._http is None:
            self._http = HttpClient()
        return self._http

    @abstractmethod
    def fetch(self, *, since: str | None = None, limit: int | None = None) -> Iterator[JobPosting]:
        """Yield job postings.

        Args:
            since: optional ISO date string for incremental crawling; sources
                should skip postings older than this when supported.
            limit: optional maximum number of postings to yield.
        """
        raise NotImplementedError
