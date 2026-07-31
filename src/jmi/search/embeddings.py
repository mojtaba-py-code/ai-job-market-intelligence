"""Embedding backends for semantic search."""

from __future__ import annotations

import math
from collections import Counter
from typing import Any, Protocol, runtime_checkable

from ..logging import get_logger
from ..nlp.cleaner import tokenize

logger = get_logger(__name__)

# A sparse vector is a mapping term -> weight.
SparseVector = dict[str, float]


@runtime_checkable
class Embedder(Protocol):
    """Common interface for all embedding backends."""

    def fit(self, documents: list[str]) -> None: ...

    def transform(self, text: str) -> Any: ...

    def similarity(self, a: Any, b: Any) -> float: ...


class TfidfEmbedder:
    """Pure-Python TF-IDF vectoriser with cosine similarity.

    Deterministic and dependency-free, which keeps the default install light and
    the tests fast. It is fit on the corpus once, then used to embed queries and
    documents into L2-normalised sparse vectors.
    """

    def __init__(self) -> None:
        self._idf: dict[str, float] = {}
        self._n_docs = 0
        self._fitted = False

    def fit(self, documents: list[str]) -> None:
        self._n_docs = len(documents)
        doc_freq: Counter[str] = Counter()
        for doc in documents:
            for term in set(tokenize(doc)):
                doc_freq[term] += 1
        # Smoothed IDF so unseen/rare terms are handled gracefully.
        self._idf = {
            term: math.log((1 + self._n_docs) / (1 + df)) + 1.0 for term, df in doc_freq.items()
        }
        self._fitted = True
        logger.info("tfidf_fitted", documents=self._n_docs, vocabulary=len(self._idf))

    def transform(self, text: str) -> SparseVector:
        tokens = tokenize(text)
        if not tokens:
            return {}
        term_freq = Counter(tokens)
        total = len(tokens)
        vector: SparseVector = {}
        for term, count in term_freq.items():
            idf = self._idf.get(term)
            if idf is None:
                continue
            vector[term] = (count / total) * idf
        return _l2_normalize(vector)

    def similarity(self, a: SparseVector, b: SparseVector) -> float:
        if not a or not b:
            return 0.0
        # Iterate over the smaller vector for efficiency.
        if len(a) > len(b):
            a, b = b, a
        return sum(weight * b.get(term, 0.0) for term, weight in a.items())


def _l2_normalize(vector: SparseVector) -> SparseVector:
    norm = math.sqrt(sum(w * w for w in vector.values()))
    if norm == 0:
        return vector
    return {term: weight / norm for term, weight in vector.items()}


def _try_sentence_transformer(model_name: str) -> Embedder | None:
    """Return a dense embedder if sentence-transformers is installed, else None."""
    try:
        from .st_backend import SentenceTransformerEmbedder
    except Exception:
        return None
    try:
        return SentenceTransformerEmbedder(model_name)
    except Exception as exc:
        logger.warning("sentence_transformer_unavailable", error=str(exc))
        return None


def get_embedder(model_name: str | None = None) -> Embedder:
    """Return the best available embedder (dense if installed, else TF-IDF)."""
    if model_name:
        dense = _try_sentence_transformer(model_name)
        if dense is not None:
            logger.info("using_dense_embedder", model=model_name)
            return dense
    return TfidfEmbedder()
