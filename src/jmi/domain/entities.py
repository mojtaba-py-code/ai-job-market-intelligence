"""Core domain entities and value objects.

These are plain, framework-free dataclasses. The scraping and NLP layers produce
them; the persistence layer maps them to/from SQLAlchemy models. Keeping the
domain independent of SQLAlchemy/Pydantic is a deliberate Clean Architecture
choice that keeps business rules testable in isolation.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import date, datetime

from .enums import EmploymentType, RemoteStatus, SeniorityLevel, SkillKind

_WHITESPACE = re.compile(r"\s+")


def _norm(value: str | None) -> str:
    """Normalise a free-text token for hashing/dedup (lower, collapse spaces)."""
    if not value:
        return ""
    return _WHITESPACE.sub(" ", value).strip().lower()


@dataclass(frozen=True, slots=True)
class Skill:
    """An extracted, canonicalised skill token."""

    name: str
    kind: SkillKind = SkillKind.concept

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", self.name.strip())


@dataclass(slots=True)
class SalaryRange:
    """A salary observation, normalised to an annual range when possible."""

    min_amount: float | None = None
    max_amount: float | None = None
    currency: str | None = None
    period: str | None = None  # year | month | hour | day

    @property
    def midpoint(self) -> float | None:
        values = [v for v in (self.min_amount, self.max_amount) if v is not None]
        return sum(values) / len(values) if values else None


@dataclass(slots=True)
class Location:
    country: str | None = None
    city: str | None = None
    region: str | None = None


@dataclass(slots=True)
class JobPosting:
    """A single, source-agnostic job posting."""

    source: str
    external_id: str
    title: str
    company: str
    url: str | None = None

    description: str = ""
    company_industry: str | None = None
    company_size: str | None = None

    employment_type: EmploymentType = EmploymentType.unknown
    remote_status: RemoteStatus = RemoteStatus.unknown
    seniority: SeniorityLevel = SeniorityLevel.unknown
    category: str | None = None

    location: Location = field(default_factory=Location)
    salary: SalaryRange = field(default_factory=SalaryRange)

    skills: list[Skill] = field(default_factory=list)
    benefits: list[str] = field(default_factory=list)
    certificates: list[str] = field(default_factory=list)

    experience_years_min: int | None = None
    education: str | None = None

    posted_at: date | None = None
    expires_at: date | None = None
    scraped_at: datetime | None = None

    # -- Derived / identity -------------------------------------------------
    @property
    def content_hash(self) -> str:
        """Deterministic fingerprint used for exact-duplicate detection.

        Built from the fields that identify *the same posting* regardless of
        which source surfaced it: normalised title + company + location + a
        prefix of the description.
        """
        parts = [
            _norm(self.title),
            _norm(self.company),
            _norm(self.location.city),
            _norm(self.location.country),
            _norm(self.description)[:280],
        ]
        digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
        return digest

    @property
    def skill_names(self) -> list[str]:
        return [s.name for s in self.skills]

    def searchable_text(self) -> str:
        """Concatenated text used for embeddings and keyword search."""
        chunks = [
            self.title,
            self.company,
            self.category or "",
            " ".join(self.skill_names),
            self.description,
        ]
        return " ".join(c for c in chunks if c).strip()
