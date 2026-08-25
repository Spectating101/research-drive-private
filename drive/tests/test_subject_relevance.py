"""Cosine similarity matches form as readily as subject.

"i need dataset regarding forest fire and economic changes" returned Mauna Loa
CO2, a Keeling curve, an earthquake catalog and two catalog indexes — a monthly
environmental panel *looks* like the answer. Measured over this registry,
rarity-weighted subject overlap runs 0.885-0.986 where the desk holds the
subject and 0.25-0.65 where it does not, so unlike cosine the bands separate.
"""

from collections import Counter

import pytest

from scripts.research_data_mcp.gateway import _is_discovery_instrument, _subject_floor
from scripts.research_data_mcp.semantic_index import SemanticCatalogIndex, _tokenize


@pytest.fixture
def index():
    idx = SemanticCatalogIndex.__new__(SemanticCatalogIndex)
    # Rarity is 1 - df/total, so the floor is only meaningful against a corpus
    # of realistic size: a unique term scores 0.667 across three documents and
    # 0.993 across the ~139 the live registry carries.
    idx._docs = [
        {"id": "fire_econ_panel", "text": "forest fire economic loss panel by province"},
        {"id": "co2_monthly", "text": "Mauna Loa monthly carbon dioxide concentrations"},
        {"id": "quake_catalog", "text": "USGS earthquake catalog sample data"},
    ] + [
        {"id": f"filler_{i}", "text": f"unrelated holding number {i} with its own vocabulary token{i}"}
        for i in range(136)
    ]
    idx._df = Counter()
    for d in idx._docs:
        idx._df.update(set(_tokenize(d["text"])))
    return idx


def _score(index, query, dataset_id):
    return index.subject_overlap(query, index.doc_index_for(dataset_id))


def test_the_subject_bearing_dataset_wins(index):
    q = "forest fire and economic changes"
    assert _score(index, q, "fire_econ_panel") > _score(index, q, "co2_monthly")


def test_a_form_alike_scores_nothing(index):
    assert _score(index, "forest fire and economic changes", "co2_monthly") == 0.0


def test_the_form_alike_scores_below_a_working_threshold(index):
    assert _score(index, "forest fire and economic changes", "co2_monthly") < 0.75


def test_the_real_subject_scores_above_a_working_threshold(index):
    assert _score(index, "forest fire economic loss", "fire_econ_panel") >= 0.75


def test_a_query_about_a_held_subject_still_matches(index):
    assert _score(index, "carbon dioxide concentrations", "co2_monthly") >= 0.75


def test_doc_index_for_is_none_when_absent(index):
    assert index.doc_index_for("not_a_dataset") is None


def test_an_empty_query_scores_zero(index):
    assert _score(index, "   ", "fire_econ_panel") == 0.0


def test_catalog_indexes_are_never_evidence():
    for shape in ("metadata_index", "source_family_registry", "ops_status"):
        assert _is_discovery_instrument({"access_shape": shape})


def test_real_datasets_are_not_filtered():
    for shape in ("materialized_instant", "derived_internal", "live_connector", ""):
        assert not _is_discovery_instrument({"access_shape": shape})


def test_the_gate_is_off_by_default():
    # It is a ranking signal, not a filter: gating cosine's candidates removes
    # everything because the high-overlap document is never among them.
    assert _subject_floor() == 0.0


def test_floor_is_tunable(monkeypatch):
    monkeypatch.setenv("RESEARCH_SUBJECT_MIN_OVERLAP", "0.5")
    assert _subject_floor() == 0.5
    monkeypatch.setenv("RESEARCH_SUBJECT_MIN_OVERLAP", "junk")
    assert _subject_floor() == 0.0
