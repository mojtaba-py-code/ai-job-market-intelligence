"""Semantic search use-case.

Builds an in-memory index from stored jobs and answers natural-language queries
such as *"remote python jobs with fastapi and postgresql"*. The index is cached
on the service instance; call :meth:`refresh` after ingestion.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from ...config import get_settings
from ...search import SemanticSearchIndex
from ...search.embeddings import get_embedder
from ..mappers import job_to_dict


class SearchService:
    def __init__(self, session: Session, *, index: SemanticSearchIndex | None = None) -> None:
        self.session = session
        settings = get_settings()
        self._index = index or SemanticSearchIndex(get_embedder(settings.embedding_model))

    def _load_documents(self):
        from ...infrastructure.db.repositories import JobRepository

        jobs = JobRepository(self.session).all_for_index()
        documents: dict[int, str] = {}
        lookup = {}
        for job in jobs:
            skills = " ".join(s.name for s in job.skills)
            company = job.company.name if job.company else ""
            documents[job.id] = " ".join(
                filter(None, [job.title, company, skills, job.description])
            )
            lookup[job.id] = job
        return documents, lookup

    def refresh(self) -> int:
        """Rebuild the index from the database. Returns document count."""
        documents, _ = self._load_documents()
        self._index.build(documents)
        return self._index.size

    def search(self, query: str, *, top_k: int = 10) -> list[dict]:
        if not self._index.is_built:
            self.refresh()
        documents, lookup = self._load_documents()
        # Ensure the index reflects current data on first use.
        if self._index.size != len(documents):
            self._index.build(documents)
        hits = self._index.query(query, top_k=top_k)
        results = []
        for hit in hits:
            job = lookup.get(hit.doc_id)
            if job is None:
                continue
            record = job_to_dict(job, include_description=False)
            record["score"] = round(hit.score, 4)
            results.append(record)
        return results
