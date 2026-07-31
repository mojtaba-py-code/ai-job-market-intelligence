"""Analytics use-case: build a market report from stored jobs."""

from __future__ import annotations

from sqlalchemy.orm import Session

from ...analytics import AnalyticsEngine, MarketReport
from ...infrastructure.db.repositories import JobRepository
from ..mappers import job_to_dict


class AnalyticsService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.jobs = JobRepository(session)

    def _records(self) -> list[dict]:
        return [job_to_dict(job, include_description=False) for job in self.jobs.all_for_index()]

    def market_report(self, *, top_n: int = 15) -> MarketReport:
        engine = AnalyticsEngine(self._records())
        return engine.build_report(top_n=top_n)
