"""A search hit must say which words matched, and not match inside a word.

`election` appearing inside `stock-selection` scored the same as a real hit,
so a query for election polling returned Indonesian microstructure and the
caller had no way to tell that apart from a dataset that matched every word.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.research_query_engine.engine import ResearchQueryEngine


def _engine(tmp_path: Path, datasets: list[dict]) -> ResearchQueryEngine:
    path = tmp_path / "registry.json"
    path.write_text(json.dumps({"datasets": datasets}), encoding="utf-8")
    return ResearchQueryEngine(path, repo_root=tmp_path)


def _rows(**over):
    row = {"dataset_id": "d1", "name": "d1", "description": "", "grain": "row"}
    row.update(over)
    return row


def test_a_word_inside_a_longer_word_is_not_a_match(tmp_path):
    engine = _engine(tmp_path, [
        _rows(dataset_id="microstructure",
              description="train monthly stock-selection and return-forecast signals"),
    ])
    assert engine.search_datasets(q="presidential election polling") == []


def test_a_real_word_still_matches_with_a_plural_suffix(tmp_path):
    engine = _engine(tmp_path, [
        _rows(dataset_id="polls", description="national election results by county"),
    ])
    hits = engine.search_datasets(q="election")
    assert [h["dataset_id"] for h in hits] == ["polls"]


def test_every_hit_reports_which_query_words_matched(tmp_path):
    engine = _engine(tmp_path, [
        _rows(dataset_id="quakes", description="usgs earthquake catalog of seismic activity"),
        _rows(dataset_id="weather", description="daily activity index"),
    ])
    hits = {h["dataset_id"]: h for h in engine.search_datasets(q="earthquake seismic activity")}
    assert hits["quakes"]["match_terms"] == ["earthquake", "seismic", "activity"]
    assert hits["quakes"]["match_terms_total"] == 3
    assert hits["weather"]["match_terms"] == ["activity"]
    assert hits["weather"]["match_terms_total"] == 3


def test_the_dataset_matching_more_words_ranks_first(tmp_path):
    engine = _engine(tmp_path, [
        _rows(dataset_id="weather", description="daily activity index"),
        _rows(dataset_id="quakes", description="usgs earthquake catalog of seismic activity"),
    ])
    assert [h["dataset_id"] for h in engine.search_datasets(q="earthquake seismic activity")] == [
        "quakes", "weather",
    ]


def test_a_query_with_nothing_behind_it_returns_nothing(tmp_path):
    engine = _engine(tmp_path, [
        _rows(dataset_id="quakes", description="usgs earthquake catalog of seismic activity"),
    ])
    assert engine.search_datasets(q="container shipping freight rates") == []


def test_search_does_not_mutate_the_registry_rows(tmp_path):
    engine = _engine(tmp_path, [
        _rows(dataset_id="quakes", description="usgs earthquake catalog"),
    ])
    engine.search_datasets(q="earthquake")
    assert "match_terms" not in engine.list_datasets()[0]


def test_an_unfiltered_listing_carries_no_match_evidence(tmp_path):
    engine = _engine(tmp_path, [_rows(dataset_id="quakes", description="usgs earthquake")])
    assert "match_terms" not in engine.search_datasets(q="")[0]
