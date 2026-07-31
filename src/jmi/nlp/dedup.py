"""Duplicate and near-duplicate detection for job postings.

Two complementary strategies are used:

* **Exact duplicates** — the SHA-256 ``content_hash`` on :class:`JobPosting`.
* **Near duplicates** — token-set Jaccard similarity over the searchable text,
  which catches the same role cross-posted with minor wording changes.
"""

from __future__ import annotations

from collections.abc import Iterable

from ..domain.entities import JobPosting
from .cleaner import tokenize


def jaccard_similarity(a: str, b: str) -> float:
    """Return the Jaccard similarity (0..1) of the token sets of *a* and *b*."""
    set_a = set(tokenize(a))
    set_b = set(tokenize(b))
    if not set_a and not set_b:
        return 1.0
    if not set_a or not set_b:
        return 0.0
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union


class DuplicateDetector:
    """Stateful detector that remembers postings it has already seen."""

    def __init__(self, *, similarity_threshold: float = 0.9) -> None:
        if not 0.0 < similarity_threshold <= 1.0:
            raise ValueError("similarity_threshold must be in (0, 1].")
        self.similarity_threshold = similarity_threshold
        self._hashes: set[str] = set()
        self._signatures: list[tuple[str, str]] = []  # (company_key, text)

    def _company_key(self, posting: JobPosting) -> str:
        return posting.company.strip().lower()

    def is_duplicate(self, posting: JobPosting) -> bool:
        """Return ``True`` if *posting* duplicates one already registered."""
        if posting.content_hash in self._hashes:
            return True
        key = self._company_key(posting)
        text = posting.searchable_text()
        for existing_key, existing_text in self._signatures:
            if existing_key != key:
                continue
            if jaccard_similarity(text, existing_text) >= self.similarity_threshold:
                return True
        return False

    def add(self, posting: JobPosting) -> None:
        self._hashes.add(posting.content_hash)
        self._signatures.append((self._company_key(posting), posting.searchable_text()))

    def filter_unique(self, postings: Iterable[JobPosting]) -> list[JobPosting]:
        """Return only the first occurrence of each (near-)duplicate group."""
        unique: list[JobPosting] = []
        for posting in postings:
            if self.is_duplicate(posting):
                continue
            self.add(posting)
            unique.append(posting)
        return unique
