"""Nearest-neighbour retrieval always returns its top-k, so a query with no
subject in the corpus came back with a full page of confident-looking results.
Measured on this corpus: real subject queries top out at 0.26-0.48, nonsense at
0.12-0.24. The gate is on the query, so anything that clears it keeps its tail."""

import os
from pathlib import Path

import pytest

from scripts.research_data_mcp.semantic_index import (
    SemanticCatalogIndex,
    _query_has_subject_signal,
    _semantic_relevance_floor,
    _semantic_tail_drop,
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

    def __init__(self, scores, vocabulary=()):
        super().__init__(Path("."))
        self._built = True
        self._docs = [{"id": f"d{i}", "kind": "dataset", "metadata": {}} for i in range(len(scores))]
        self._embeddings = [[s] for s in scores]
        self._embedding_model = "stub"
        self._scores = scores
        self._df.update(vocabulary)

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


def _search(scores, query="anything", vocabulary=(), **kw):
    return _Idx(scores, vocabulary).semantic_search(query, model_name="stub", **kw)


def test_a_query_with_no_real_match_returns_nothing():
    assert _search([0.24, 0.20, 0.12]) == []


def test_a_real_query_keeps_only_its_coherent_tail():
    rows = _search([0.47, 0.31, 0.30, 0.08], limit=8)
    assert len(rows) == 2
    assert rows[0]["score"] == pytest.approx(0.47, abs=1e-6)


def test_embedding_shaped_keyboard_noise_is_rejected_even_above_the_score_floor():
    assert _search([0.72, 0.61], query="zzqvjjk plmxxc") == []


def test_an_exact_index_identifier_remains_semantically_eligible():
    rows = _search([0.42], query="JKSE", vocabulary={"jkse"})
    assert len(rows) == 1


def test_subject_signal_accepts_natural_language_and_cjk_but_not_random_consonants():
    assert _query_has_subject_signal("daily returns") is True
    assert _query_has_subject_signal("台灣公司治理") is True
    assert _query_has_subject_signal("zzqvjjk plmxxc") is False


def test_boundary_is_inclusive_at_the_floor():
    assert len(_search([0.25])) == 1
    assert _search([0.2499]) == []


def test_floor_is_tunable_at_runtime():
    os.environ["RESEARCH_SEMANTIC_QUERY_FLOOR"] = "0.45"
    try:
        assert _search([0.30, 0.10]) == []
    finally:
        os.environ.pop("RESEARCH_SEMANTIC_QUERY_FLOOR", None)


def test_tail_drop_default_and_override():
    prior = os.environ.pop("RESEARCH_SEMANTIC_TAIL_DROP", None)
    try:
        assert _semantic_tail_drop() == 0.16
        os.environ["RESEARCH_SEMANTIC_TAIL_DROP"] = "0.08"
        assert _semantic_tail_drop() == 0.08
        os.environ["RESEARCH_SEMANTIC_TAIL_DROP"] = "junk"
        assert _semantic_tail_drop() == 0.16
    finally:
        os.environ.pop("RESEARCH_SEMANTIC_TAIL_DROP", None)
        if prior is not None:
            os.environ["RESEARCH_SEMANTIC_TAIL_DROP"] = prior


def test_empty_index_is_still_safe():
    assert _search([]) == []
