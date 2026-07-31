"""Semantic search over job postings.

Two backends are supported behind one interface:

* **TfidfEmbedder** — a dependency-light, deterministic default that works out of
  the box (pure-Python sparse TF-IDF + cosine similarity).
* **SentenceTransformerEmbedder** — activated automatically when the
  ``jmi[semantic]`` extra (sentence-transformers + faiss) is installed, giving
  true dense-vector semantic search.
"""

from .embeddings import Embedder, TfidfEmbedder, get_embedder
from .index import SearchHit, SemanticSearchIndex

__all__ = [
    "Embedder",
    "SearchHit",
    "SemanticSearchIndex",
    "TfidfEmbedder",
    "get_embedder",
]
