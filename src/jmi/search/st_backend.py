"""Optional dense embedding backend (sentence-transformers + numpy).

Imported lazily by :func:`jmi.search.embeddings.get_embedder` only when the
``jmi[semantic]`` extra is installed. Kept in its own module so the core package
never imports heavy ML dependencies at import time.
"""

from __future__ import annotations

import numpy as np
from sentence_transformers import SentenceTransformer


class SentenceTransformerEmbedder:
    """Dense-vector embedder using a sentence-transformers model."""

    def __init__(self, model_name: str) -> None:
        self._model = SentenceTransformer(model_name)

    def fit(self, documents: list[str]) -> None:
        """No-op: transformer models are pre-trained."""

    def transform(self, text: str) -> np.ndarray:
        vector = self._model.encode([text], normalize_embeddings=True)[0]
        return np.asarray(vector, dtype="float32")

    def similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        return float(np.dot(a, b))
