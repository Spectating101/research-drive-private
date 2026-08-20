#!/usr/bin/env python3
"""Semantic retrieval must widen recall, and degrade to keyword rather than to a wrong answer.

Measured on the real 60,610-document corpus: FTS retrieves 4 documents for "stock returns"
and 14 for "patent". Re-ranking those candidates moved precision 14/25 -> 15/25, because
ranking was never the constraint — the right documents were not retrieved. Scanning the
embedded corpus is the only thing that changes that.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.research_data_mcp.datacite_vault_search import search_curated_semantic


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    for var in ("DATACITE_TOPIC_INDEX_ON_BULK", "DATACITE_TOPIC_INDEX_ROOT", "RESEARCH_BULK_ROOT"):
        monkeypatch.delenv(var, raising=False)


def test_absent_vector_index_returns_nothing_rather_than_guessing(tmp_path):
    """A missing build must fall back to keyword, never fabricate a semantic answer."""
    (tmp_path / "data_lake/dataset_catalog/_topic_index").mkdir(parents=True)
    assert search_curated_semantic(tmp_path, "anything", limit=5) == []


def test_an_empty_query_is_refused(tmp_path):
    assert search_curated_semantic(tmp_path, "   ", limit=5) == []


def test_a_vector_count_mismatch_is_treated_as_stale(tmp_path):
    """Vectors that do not line up with the FTS rows would return the wrong documents."""
    import numpy as np

    root = tmp_path / "data_lake/dataset_catalog/_topic_index"
    root.mkdir(parents=True)
    import sqlite3

    conn = sqlite3.connect(root / "curated.sqlite3")
    conn.execute(
        "CREATE VIRTUAL TABLE curated_fts USING fts5(doi UNINDEXED, dataset_id UNINDEXED, "
        "source_dir UNINDEXED, title, body, payload_json UNINDEXED)"
    )
    conn.execute("INSERT INTO curated_fts VALUES ('d','x','s','t','b','{}')")
    conn.commit()
    conn.close()
    np.save(root / "curated_vectors.npy", np.zeros((7, 384), dtype="float32"))
    (root / "curated_vectors_meta.json").write_text(
        json.dumps({"model": "sentence-transformers/all-MiniLM-L6-v2", "rowids": [1]}),
        encoding="utf-8",
    )
    assert search_curated_semantic(tmp_path, "t", limit=3) == []
