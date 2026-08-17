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


def test_the_fields_saying_what_a_dataset_is_about_are_searched(tmp_path):
    """NHANES holds infant measures, but only its one_line says so, and
    one_line was not indexed — so the dataset was unfindable by that word."""
    engine = _engine(tmp_path, [
        _rows(dataset_id="demo", name="NHANES 2017-2018 Demographics",
              description="demographic records for survey participants",
              one_line="includes infant and household context variables",
              meaning_about="the demographic component of the survey cycle",
              keywords=["public-health", "biomarkers"],
              tags=["nhanes", "xpt"]),
    ])
    for term in ("infant", "biomarkers", "xpt", "demographic component"):
        assert [h["dataset_id"] for h in engine.search_datasets(q=term)] == ["demo"], term


def test_a_hyphenated_keyword_matches_either_half(tmp_path):
    engine = _engine(tmp_path, [_rows(dataset_id="demo", keywords=["public-health"])])
    assert engine.search_datasets(q="health")
    assert engine.search_datasets(q="public")


def test_list_fields_do_not_leak_python_syntax_into_the_text(tmp_path):
    engine = _engine(tmp_path, [_rows(dataset_id="demo", tags=["alpha", "beta"])])
    assert ResearchQueryEngine.searchable_text({"tags": ["alpha", "beta"]}) == "alpha beta"
    assert engine.search_datasets(q="alpha")


def test_an_empty_dataset_produces_empty_text():
    assert ResearchQueryEngine.searchable_text({}) == ""
    assert ResearchQueryEngine.searchable_text({"tags": [], "one_line": None}) == ""


def test_unified_search_carries_the_match_evidence(tmp_path):
    """Verified over HTTP first: /library/search returned the right datasets with
    match_terms None, because the unified layer rebuilds its own row and had
    dropped it. A one-of-three match must not look like a three-of-three.
    """
    from scripts.research_data_mcp.search import SearchService
    from scripts.research_data_mcp.unified_search import unified_search

    registry = tmp_path / "config/research_query_registry.json"
    registry.parent.mkdir(parents=True, exist_ok=True)
    registry.write_text(json.dumps({"datasets": [
        {"dataset_id": "usgs_earthquake_catalog", "name": "USGS earthquake catalog",
         "description": "event-level seismic history with earthquake activity per event",
         "domain": "geoscience", "grain": "event"},
        {"dataset_id": "daily_activity_index", "name": "Daily activity index",
         "description": "a broad daily activity measure", "domain": "macro", "grain": "day"},
    ]}), encoding="utf-8")
    engine = ResearchQueryEngine(registry, repo_root=tmp_path)
    service = SearchService(engine, registry, tmp_path)

    out = unified_search(service, "earthquake seismic activity",
                         limit=10, include_hf=False, include_datacite=False)
    rows = {r.get("dataset_id"): r for r in out["rows"] if r.get("kind") == "local_registry"}
    assert rows, "no local registry rows survived the unified layer"
    quake = rows["usgs_earthquake_catalog"]
    assert quake["match_terms"] == ["earthquake", "seismic", "activity"]
    assert quake["match_terms_total"] == 3
