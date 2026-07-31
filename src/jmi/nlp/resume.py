"""Resume parsing.

Extracts a structured :class:`ResumeProfile` from raw resume text: canonical
skills (via the taxonomy), an estimated total years of experience, and contact
signals. Kept intentionally dependency-light; PDF/DOCX extraction can be layered
on top by the caller before passing plain text in.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .cleaner import clean_text
from .skills import SkillExtractor, get_default_extractor

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_YEARS = re.compile(r"(\d{1,2})\+?\s*(?:years|yrs)\b", re.IGNORECASE)


@dataclass(slots=True)
class ResumeProfile:
    """Structured view of a candidate resume."""

    raw_text: str
    skills: list[str] = field(default_factory=list)
    email: str | None = None
    years_experience: int | None = None

    @property
    def skill_set(self) -> set[str]:
        return set(self.skills)


def _estimate_years(text: str) -> int | None:
    matches = [int(m) for m in _YEARS.findall(text)]
    return max(matches) if matches else None


def parse_resume(text: str, extractor: SkillExtractor | None = None) -> ResumeProfile:
    """Parse raw resume *text* into a :class:`ResumeProfile`."""
    extractor = extractor or get_default_extractor()
    cleaned = clean_text(text, keep_newlines=True)
    skills = [s.name for s in extractor.extract(cleaned)]
    email_match = _EMAIL.search(text)
    return ResumeProfile(
        raw_text=cleaned,
        skills=skills,
        email=email_match.group(0) if email_match else None,
        years_experience=_estimate_years(cleaned),
    )
