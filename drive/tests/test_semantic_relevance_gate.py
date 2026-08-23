"""Nearest-neighbour retrieval always returns its top-k, so a query with no
subject in the corpus came back with a full page of confident-looking results.
Measured on this corpus: real subject queries top out at 0.26-0.48, nonsense at
0.12-0.24. The gate is on the query, so anything that clears it keeps its tail."""

import os
from pathlib import Path

import pytest

from scripts.research_data_mcp.semantic_index import (
    SemanticCatalogIndex,
    _semantic_relevance_floor,
)


def test_floor_default_and_override():
    prior = os.environ.pop("RESEARCH_SEMANTIC_QUERY_FLOOR", None)
    try:
        assert _semantic_relevance_floor() == 0.25
        os.environ["RESEARCH_SEMANTIC_QUERY_FLOOR"] = "0.4"
        assert _semantic_relevance_floor() == 0.4
        os.environ["RESEARCH_SEMANTIC_QUERY_FLOOR"] = "junk"
        assert _semantic_relevance_floor() == 0.25
    finally:
        os.environ.pop("RESEARCH_SEMANTIC_QUERY_FLOOR", None)
        if prior is not None:
            os.environ["RESEARCH_SEMANTIC_QUERY_FLOOR"] = prior


class _Idx(SemanticCatalogIndex):
    """Drive scoring directly: unit vectors give an exact, readable cosine."""

    def __init__(self, scores):
        super().__init__(Path("."))
        self._built = True
        self._docs = [{"id": f"d{i}", "kind": "dataset", "metadata": {}} for i in range(len(scores))]
        self._embeddings = [[s] for s in scores]
        self._embedding_model = "stub"
        self._scores = scores

    def _ensure_embeddings(self, *, model_name="stub"):
        return None

    def _embedding_model_instance(self, model_name):
        class M:
            @staticmethod
            def encode(_q, **_k):
                return [1.0]

        return M()

    def embeddings_ready(self, *, model_name="stub"):
        return True


def _search(scores, **kw):
    return _Idx(scores).semantic_search("anything", model_name="stub", **kw)


def test_a_query_with_no_real_match_returns_nothing():
    assert _search([0.24, 0.20, 0.12]) == []


def test_a_real_query_keeps_its_whole_tail():
    rows = _search([0.47, 0.19, 0.08], limit=8)
    assert len(rows) == 3, "the gate is per-query; it must not filter individual rows"
    assert rows[0]["score"] == pytest.approx(0.47, abs=1e-6)


def test_boundary_is_inclusive_at_the_floor():
    assert len(_search([0.25])) == 1
    assert _search([0.2499]) == []


def test_floor_is_tunable_at_runtime():
    os.environ["RESEARCH_SEMANTIC_QUERY_FLOOR"] = "0.45"
    try:
        assert _search([0.30, 0.10]) == []
    finally:
        os.environ.pop("RESEARCH_SEMANTIC_QUERY_FLOOR", None)


def test_empty_index_is_still_safe():
    assert _search([]) == []
