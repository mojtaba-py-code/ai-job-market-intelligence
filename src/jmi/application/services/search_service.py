"""Semantic search use-case.

Answers natural-language queries such as *"remote python jobs with fastapi and
postgresql"* over the stored postings.

Building the index is expensive — it fits the embedder across the whole corpus
and embeds every document — so it is built once per corpus state and shared
process-wide via :mod:`jmi.search.cache`. Rebuilding per request would let an
unauthenticated caller spend O(corpus) CPU with a single small HTTP request.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from ...config import get_settings
from ...search import SemanticSearchIndex
from ...search import cache as index_cache
from ...search.embeddings import get_embedder
from ..mappers import job_to_dict


class SearchService:
    def __init__(self, session: Session, *, index: SemanticSearchIndex | None = None) -> None:
        """Create the service.

        Args:
            session: the request-scoped database session.
            index: an explicit index to use. Passing one opts out of the shared
                cache entirely, which is what tests want; production callers
                leave it unset so every request reuses the same built index.
        """
        self.session = session
        self._explicit_index = index

    # -- internals ----------------------------------------------------------
    def _repository(self):
        from ...infrastructure.db.repositories import JobRepository

        return JobRepository(self.session)

    def _load_documents(self) -> dict[int, str]:
        """Materialise the searchable text of every posting, keyed by job id."""
        documents: dict[int, str] = {}
        for job in self._repository().all_for_index():
            skills = " ".join(s.name for s in job.skills)
            company = job.company.name if job.company else ""
            documents[job.id] = " ".join(
                filter(None, [job.title, company, skills, job.description])
            )
        return documents

    def _build_index(self) -> SemanticSearchIndex:
        index = SemanticSearchIndex(get_embedder(get_settings().embedding_model))
        index.build(self._load_documents())
        return index

    def _index(self) -> SemanticSearchIndex:
        if self._explicit_index is not None:
            if not self._explicit_index.is_built:
                self._explicit_index.build(self._load_documents())
            return self._explicit_index
        return index_cache.get_or_build(
            self._repository().corpus_fingerprint(),
            self._build_index,
        )

    # -- API ----------------------------------------------------------------
    def refresh(self) -> int:
        """Rebuild the index from the database. Returns document count."""
        index_cache.invalidate()
        return self._index().size

    def search(self, query: str, *, top_k: int = 10) -> list[dict]:
        """Return the *top_k* best matches for *query*, best first."""
        hits = self._index().query(query, top_k=top_k)
        if not hits:
            return []

        # Only the returned rows are fetched, rather than the whole corpus.
        jobs = {job.id: job for job in self._repository().get_many([h.doc_id for h in hits])}

        results = []
        for hit in hits:
            job = jobs.get(hit.doc_id)
            if job is None:
                # Deleted between indexing and lookup — skip rather than fail.
                continue
            record = job_to_dict(job, include_description=False)
            record["score"] = round(hit.score, 4)
            results.append(record)
        return results
