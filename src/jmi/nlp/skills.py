"""Skill and technology extraction.

The default extractor is rule-based: it matches the curated taxonomy against the
text using boundary-aware regular expressions. This is fast, deterministic and
explainable. When the ``jmi[nlp]`` extra (spaCy) is installed, callers may layer
named-entity recognition on top; the rule-based layer alone already covers the
technologies the analytics module reports on.
"""

from __future__ import annotations

import re
from functools import lru_cache

from ..domain.entities import Skill
from ..domain.enums import SkillKind
from .cleaner import clean_text
from .taxonomy import Taxonomy, load_taxonomy

# Characters that count as part of a technology token. Boundaries are defined as
# "not one of these", which lets "c++" and "c#" match precisely without firing
# inside unrelated words. '.' is deliberately excluded so a trailing sentence
# period ("Docker.") does not block a match; dotted names like ".NET"/"node.js"
# are matched as explicit literal aliases instead.
_TOKEN_CHARS = r"\w+#"


def _alias_pattern(alias: str) -> str:
    escaped = re.escape(alias)
    return rf"(?<![{_TOKEN_CHARS}]){escaped}(?![{_TOKEN_CHARS}])"


class SkillExtractor:
    """Extract canonical skills from free text using a taxonomy."""

    def __init__(self, taxonomy: Taxonomy | None = None) -> None:
        self._taxonomy = taxonomy or Taxonomy()
        self._alias_to_canonical = self._taxonomy.alias_map()
        # Longest aliases first so "sql server" wins over "sql".
        aliases = sorted(self._alias_to_canonical, key=len, reverse=True)
        pattern = "|".join(_alias_pattern(a) for a in aliases)
        self._regex = re.compile(pattern, re.IGNORECASE)

    def extract(self, text: str | None) -> list[Skill]:
        """Return a de-duplicated, order-stable list of skills found in *text*."""
        if not text:
            return []
        cleaned = clean_text(text)
        seen: dict[str, Skill] = {}
        for match in self._regex.finditer(cleaned):
            alias = match.group(0).lower()
            canonical = self._alias_to_canonical.get(alias)
            if canonical is None:
                continue
            if canonical not in seen:
                seen[canonical] = Skill(name=canonical, kind=self._taxonomy.kind_of(canonical))
        return list(seen.values())

    def extract_by_kind(self, text: str | None) -> dict[SkillKind, list[str]]:
        """Group extracted skill names by their kind."""
        grouped: dict[SkillKind, list[str]] = {}
        for skill in self.extract(text):
            grouped.setdefault(skill.kind, []).append(skill.name)
        return grouped


@lru_cache
def get_default_extractor() -> SkillExtractor:
    """Cached extractor built from the default taxonomy."""
    return SkillExtractor(load_taxonomy())
