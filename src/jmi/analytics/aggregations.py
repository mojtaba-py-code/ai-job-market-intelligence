"""Aggregations that turn raw job records into market intelligence.

Input is a list of plain dictionaries (produced by the service layer from the
ORM) so this module stays independent of the database. Everything is computed
with pandas for clarity and speed.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

import pandas as pd

from ..domain.enums import SkillKind


@dataclass(slots=True)
class MarketReport:
    """A structured snapshot of the job market."""

    total_jobs: int = 0
    remote_percentage: float = 0.0
    top_skills: list[dict] = field(default_factory=list)
    top_languages: list[dict] = field(default_factory=list)
    top_frameworks: list[dict] = field(default_factory=list)
    top_databases: list[dict] = field(default_factory=list)
    top_cloud: list[dict] = field(default_factory=list)
    salary_by_currency: list[dict] = field(default_factory=list)
    top_companies: list[dict] = field(default_factory=list)
    top_countries: list[dict] = field(default_factory=list)
    top_cities: list[dict] = field(default_factory=list)
    monthly_trend: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "total_jobs": self.total_jobs,
            "remote_percentage": self.remote_percentage,
            "top_skills": self.top_skills,
            "top_languages": self.top_languages,
            "top_frameworks": self.top_frameworks,
            "top_databases": self.top_databases,
            "top_cloud": self.top_cloud,
            "salary_by_currency": self.salary_by_currency,
            "top_companies": self.top_companies,
            "top_countries": self.top_countries,
            "top_cities": self.top_cities,
            "monthly_trend": self.monthly_trend,
        }


class AnalyticsEngine:
    """Computes market analytics from job records.

    Each record is a dict with keys: ``remote_status``, ``company``,
    ``country``, ``city``, ``salary_min``, ``salary_max``, ``currency``,
    ``posted_at`` (date/str) and ``skills`` (list of ``{"name", "kind"}``).
    """

    def __init__(self, records: list[dict]) -> None:
        self._records = records
        self._df = pd.DataFrame(records)

    # -- helpers ------------------------------------------------------------
    def _skill_counter(self, kind: SkillKind | None = None) -> Counter[str]:
        counter: Counter[str] = Counter()
        for record in self._records:
            for skill in record.get("skills", []):
                if kind is None or skill.get("kind") == kind.value:
                    counter[skill["name"]] += 1
        return counter

    @staticmethod
    def _top(counter: Counter[str], limit: int) -> list[dict]:
        return [{"name": name, "count": count} for name, count in counter.most_common(limit)]

    def _top_column(self, column: str, limit: int) -> list[dict]:
        if self._df.empty or column not in self._df:
            return []
        counts = self._df[column].dropna().value_counts().head(limit)
        return [{"name": str(name), "count": int(count)} for name, count in counts.items()]

    # -- public metrics -----------------------------------------------------
    def total_jobs(self) -> int:
        return len(self._records)

    def remote_percentage(self) -> float:
        if self._df.empty or "remote_status" not in self._df:
            return 0.0
        remote = self._df["remote_status"].isin(["remote", "hybrid"]).sum()
        return round(100.0 * remote / len(self._df), 2)

    def top_skills(self, limit: int = 15) -> list[dict]:
        return self._top(self._skill_counter(), limit)

    def top_by_kind(self, kind: SkillKind, limit: int = 10) -> list[dict]:
        return self._top(self._skill_counter(kind), limit)

    def salary_by_currency(self) -> list[dict]:
        if self._df.empty or "currency" not in self._df:
            return []
        df = self._df.dropna(subset=["currency"]).copy()
        if df.empty:
            return []
        df["salary_mid"] = df[["salary_min", "salary_max"]].mean(axis=1, skipna=True)
        grouped = df.dropna(subset=["salary_mid"]).groupby("currency")["salary_mid"]
        out = []
        for currency, series in grouped:
            out.append(
                {
                    "currency": str(currency),
                    "count": int(series.count()),
                    "avg": round(float(series.mean()), 2),
                    "median": round(float(series.median()), 2),
                    "min": round(float(series.min()), 2),
                    "max": round(float(series.max()), 2),
                }
            )
        return sorted(out, key=lambda item: item["count"], reverse=True)

    def monthly_trend(self) -> list[dict]:
        if self._df.empty or "posted_at" not in self._df:
            return []
        dates = pd.to_datetime(self._df["posted_at"], errors="coerce").dropna()
        if dates.empty:
            return []
        by_month = dates.dt.to_period("M").value_counts().sort_index()
        return [{"month": str(period), "count": int(count)} for period, count in by_month.items()]

    def build_report(self, *, top_n: int = 15) -> MarketReport:
        return MarketReport(
            total_jobs=self.total_jobs(),
            remote_percentage=self.remote_percentage(),
            top_skills=self.top_skills(top_n),
            top_languages=self.top_by_kind(SkillKind.language, 10),
            top_frameworks=self.top_by_kind(SkillKind.framework, 10),
            top_databases=self.top_by_kind(SkillKind.database, 10),
            top_cloud=self.top_by_kind(SkillKind.cloud, 10),
            salary_by_currency=self.salary_by_currency(),
            top_companies=self._top_column("company", 10),
            top_countries=self._top_column("country", 10),
            top_cities=self._top_column("city", 10),
            monthly_trend=self.monthly_trend(),
        )
