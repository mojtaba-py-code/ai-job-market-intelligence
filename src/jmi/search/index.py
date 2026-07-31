"""In-memory semantic search index.

Holds document vectors keyed by job id and answers nearest-neighbour queries by
cosine similarity. For the dense backend this is a brute-force scan, which is
perfectly adequate for tens of thousands of postings; swap in FAISS for millions
(the :class:`Embedder` interface stays the same).
"""

from __future__ import annotations

from dataclasses import dataclass

from .embeddings import Embedder, TfidfEmbedder


@dataclass(slots=True)
class SearchHit:
    """A single search result."""

    doc_id: int
    score: float


class SemanticSearchIndex:
    """A brute-force vector index over document embeddings."""

    def __init__(self, embedder: Embedder | None = None) -> None:
        self._embedder: Embedder = embedder or TfidfEmbedder()
        self._vectors: dict[int, object] = {}
        self._built = False

    @property
    def size(self) -> int:
        return len(self._vectors)

    @property
    def is_built(self) -> bool:
        return self._built

    def build(self, documents: dict[int, str]) -> None:
        """Fit the embedder on the corpus and embed every document."""
        corpus = list(documents.values())
        self._embedder.fit(corpus)
        self._vectors = {
            doc_id: self._embedder.transform(text) for doc_id, text in documents.items()
        }
        self._built = True

    def query(self, text: str, *, top_k: int = 10) -> list[SearchHit]:
        """Return the *top_k* most similar documents to *text*."""
        if not self._built or not self._vectors:
            return []
        query_vec = self._embedder.transform(text)
        scored = [
            SearchHit(doc_id=doc_id, score=self._embedder.similarity(query_vec, vec))
            for doc_id, vec in self._vectors.items()
        ]
        scored.sort(key=lambda hit: hit.score, reverse=True)
        return [hit for hit in scored[:top_k] if hit.score > 0.0]
