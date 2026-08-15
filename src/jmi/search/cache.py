"""Process-wide cache for the semantic search index.

Building the index fits the embedder over the whole corpus and then embeds every
document. Doing that per request turns a cheap, unauthenticated endpoint into an
amplification attack: one small HTTP call costs O(corpus) CPU and allocations,
so a handful of concurrent callers can saturate the process regardless of how
generous the rate limit is.

The index is therefore built once per corpus state and shared. A cheap
fingerprint (row count plus the highest id) detects rows appearing or
disappearing, and :func:`invalidate` is called by the ingestion pipeline for
in-place edits that leave both numbers unchanged.

The cache is per process. Multiple workers each hold their own copy, which costs
memory but keeps the design lock-free across processes; a shared vector store is
the answer at a scale where that matters.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .index import SemanticSearchIndex

#: Guards ``_index``/``_fingerprint``. Held across the rebuild so that a burst of
#: concurrent first-requests results in exactly one build rather than one per
#: caller — the stampede is the whole problem being solved here.
_lock = threading.Lock()
_index: SemanticSearchIndex | None = None
_fingerprint: object = None


def get_or_build(
    fingerprint: object,
    build: Callable[[], SemanticSearchIndex],
) -> SemanticSearchIndex:
    """Return the cached index, rebuilding it if *fingerprint* has changed.

    Args:
        fingerprint: a cheap, comparable summary of the corpus state.
        build: constructs and populates a fresh index. Called at most once per
            distinct fingerprint.

    Returns:
        An index reflecting the corpus as of *fingerprint*.
    """
    global _index, _fingerprint

    with _lock:
        if _index is None or _fingerprint != fingerprint:
            _index = build()
            _fingerprint = fingerprint
        return _index


def invalidate() -> None:
    """Drop the cached index, forcing a rebuild on the next search.

    Called after ingestion: an upsert can rewrite a posting's title, description
    or skills without changing the row count or the highest id, which the
    fingerprint alone cannot see.
    """
    global _index, _fingerprint

    with _lock:
        _index = None
        _fingerprint = None
