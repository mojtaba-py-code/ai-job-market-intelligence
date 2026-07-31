"""Bundled offline source that emulates a public JSON job API.

This source ships with the package so the whole pipeline — ingest, NLP, search,
analytics — can be demonstrated and tested without hitting the network or any
third-party Terms of Service. Real portal integrations follow the exact same
shape: fetch pages, map each record to a :class:`JobPosting`.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, date, datetime
from pathlib import Path

from ...domain.entities import JobPosting, Location, SalaryRange
from ...domain.enums import EmploymentType, RemoteStatus, SeniorityLevel
from ..base import BaseSource, SourceMetadata
from ..registry import registry

_DATA_FILE = Path(__file__).with_name("sample_data.json")


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


@registry.register
class SampleJsonSource(BaseSource):
    """Reads postings from the bundled JSON fixture (a stand-in JSON API)."""

    metadata = SourceMetadata(
        name="sample",
        display_name="Sample JSON Board",
        base_url="https://jobs.example.com",
        supports_incremental=True,
        requires_javascript=False,
    )

    def __init__(self, http_client=None, data_file: Path | None = None) -> None:
        super().__init__(http_client)
        self._data_file = data_file or _DATA_FILE

    def _load_records(self) -> list[dict]:
        return json.loads(self._data_file.read_text(encoding="utf-8"))

    def _to_posting(self, record: dict) -> JobPosting:
        return JobPosting(
            source=self.name,
            external_id=str(record["external_id"]),
            title=record["title"],
            company=record["company"],
            url=record.get("url"),
            description=record.get("description", ""),
            company_industry=record.get("company_industry"),
            company_size=record.get("company_size"),
            employment_type=EmploymentType(record.get("employment_type", "unknown")),
            remote_status=RemoteStatus(record.get("remote_status", "unknown")),
            seniority=SeniorityLevel(record.get("seniority", "unknown")),
            category=record.get("category"),
            location=Location(
                country=record.get("country"),
                city=record.get("city"),
            ),
            salary=SalaryRange(
                min_amount=record.get("salary_min"),
                max_amount=record.get("salary_max"),
                currency=record.get("currency"),
                period=record.get("salary_period"),
            ),
            benefits=list(record.get("benefits", [])),
            posted_at=_parse_date(record.get("posted_at")),
            scraped_at=datetime.now(UTC),
        )

    def fetch(self, *, since: str | None = None, limit: int | None = None) -> Iterator[JobPosting]:
        since_date = _parse_date(since)
        count = 0
        for record in self._load_records():
            posting = self._to_posting(record)
            if since_date and posting.posted_at and posting.posted_at < since_date:
                continue  # incremental crawl: skip already-seen postings
            yield posting
            count += 1
            if limit is not None and count >= limit:
                return
