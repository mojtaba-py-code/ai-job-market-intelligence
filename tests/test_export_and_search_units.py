"""Unit tests for exporters and the TF-IDF search primitives."""

from __future__ import annotations

import io
import json

import pandas as pd
import pytest

from jmi.domain.enums import ExportFormat
from jmi.infrastructure.export import export_jobs
from jmi.infrastructure.export.exporters import content_type_for
from jmi.search import SemanticSearchIndex, TfidfEmbedder

RECORDS = [
    {"id": 1, "title": "Python Dev", "company": "Acme", "skills": "Python, FastAPI"},
    {"id": 2, "title": "Java Dev", "company": "Globex", "skills": "Java, Spring"},
]


def test_export_json_roundtrips():
    payload = export_jobs(RECORDS, ExportFormat.json)
    assert json.loads(payload) == RECORDS


def test_export_csv_has_header_and_rows():
    payload = export_jobs(RECORDS, "csv").decode("utf-8")
    assert "title" in payload
    assert "Python Dev" in payload and "Java Dev" in payload


def test_export_excel_is_readable():
    payload = export_jobs(RECORDS, ExportFormat.excel)
    frame = pd.read_excel(io.BytesIO(payload))
    assert list(frame["title"]) == ["Python Dev", "Java Dev"]


def test_content_type_mapping():
    assert content_type_for("csv") == "text/csv"
    assert "spreadsheet" in content_type_for(ExportFormat.excel)


def test_tfidf_embedder_similarity_ranks_related_higher():
    emb = TfidfEmbedder()
    corpus = [
        "python backend engineer fastapi postgresql",
        "java spring boot developer",
        "frontend react typescript developer",
    ]
    emb.fit(corpus)
    query = emb.transform("python fastapi api")
    scores = [emb.similarity(query, emb.transform(doc)) for doc in corpus]
    assert scores[0] == max(scores)


def test_tfidf_unknown_terms_yield_zero_vector():
    emb = TfidfEmbedder()
    emb.fit(["hello world"])
    assert emb.transform("zzz qqq") == {}


def test_semantic_index_build_and_query():
    index = SemanticSearchIndex(TfidfEmbedder())
    index.build(
        {
            1: "python fastapi postgresql backend",
            2: "java spring developer",
            3: "react frontend typescript",
        }
    )
    assert index.size == 3
    hits = index.query("python backend api", top_k=2)
    assert hits and hits[0].doc_id == 1


def test_semantic_index_empty_returns_no_hits():
    index = SemanticSearchIndex(TfidfEmbedder())
    assert index.query("anything") == []


def test_export_invalid_format_raises():
    with pytest.raises(ValueError):
        export_jobs(RECORDS, "xml")
