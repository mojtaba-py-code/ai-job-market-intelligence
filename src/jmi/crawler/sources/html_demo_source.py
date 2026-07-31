"""Bundled HTML source demonstrating BeautifulSoup parsing + pagination.

Real-world HTML boards are parsed exactly like this: locate the container,
iterate over card elements, and map each to a :class:`JobPosting`. The bundled
fixture keeps the parser offline and deterministic for tests. A live version
would replace :meth:`_load_html` with paged ``self.http.get(...)`` calls,
following the ``a.next`` link until it disappears.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime
from pathlib import Path

from bs4 import BeautifulSoup

from ...domain.entities import JobPosting, Location, SalaryRange
from ...domain.enums import EmploymentType, RemoteStatus
from ..base import BaseSource, SourceMetadata
from ..registry import registry

_HTML_FILE = Path(__file__).with_name("sample_board.html")


def _to_float(value: str | None) -> float | None:
    try:
        return float(value) if value else None
    except ValueError:
        return None


@registry.register
class HtmlDemoSource(BaseSource):
    """Parses a paginated HTML board with BeautifulSoup."""

    metadata = SourceMetadata(
        name="html_demo",
        display_name="Demo HTML Board",
        base_url="https://board.example.com",
        supports_incremental=False,
        requires_javascript=False,
    )

    def __init__(self, http_client=None, html_file: Path | None = None) -> None:
        super().__init__(http_client)
        self._html_file = html_file or _HTML_FILE

    def _load_html(self) -> str:
        return self._html_file.read_text(encoding="utf-8")

    def _parse_card(self, card) -> JobPosting:
        loc = card.select_one(".location")
        salary = card.select_one(".salary")
        posted = card.select_one(".posted")
        posted_date: date | None = None
        if posted and posted.get("datetime"):
            try:
                posted_date = date.fromisoformat(posted["datetime"])
            except ValueError:
                posted_date = None

        return JobPosting(
            source=self.name,
            external_id=card.get("data-job-id", ""),
            title=card.select_one(".job-title").get_text(strip=True),
            company=card.select_one(".company").get_text(strip=True),
            description=card.select_one(".description").get_text(strip=True),
            employment_type=EmploymentType(
                card.select_one(".employment").get_text(strip=True) or "unknown"
            ),
            remote_status=RemoteStatus(
                card.select_one(".remote").get_text(strip=True) or "unknown"
            ),
            location=Location(
                country=loc.get("data-country") if loc else None,
                city=loc.get("data-city") if loc else None,
            ),
            salary=SalaryRange(
                min_amount=_to_float(salary.get("data-min")) if salary else None,
                max_amount=_to_float(salary.get("data-max")) if salary else None,
                currency=salary.get("data-currency") if salary else None,
                period="year",
            ),
            posted_at=posted_date,
            scraped_at=datetime.now(UTC),
        )

    def fetch(self, *, since: str | None = None, limit: int | None = None) -> Iterator[JobPosting]:
        soup = BeautifulSoup(self._load_html(), "lxml")
        for count, card in enumerate(soup.select("li.job-card"), start=1):
            yield self._parse_card(card)
            if limit is not None and count >= limit:
                return
        # A live crawler would follow soup.select_one("a.next") here to paginate.
