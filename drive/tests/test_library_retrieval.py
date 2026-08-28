from __future__ import annotations

import json
from pathlib import Path

from scripts.research_data_mcp.library_retrieval import (
    rank_registry_assets,
    registry_search_document,
    score_registry_asset,
)
from scripts.research_query_engine.engine import ResearchQueryEngine


ROWS = [
    {
        "dataset_id": "gdelt_asia_daily_country_panel",
        "name": "Asia daily news-risk panel",
        "source": "GDELT GKG",
        "source_system": "GDELT news graph",
        "grain": "country_day",
        "coverage": "2018–2024",
        "join_keys": ["date", "country_iso3"],
        "description": "Daily country-level news intensity and risk measures for Asian economies.",
        "analysis_readiness": "instant",
    },
    {
        "dataset_id": "issuer_weekly_panel",
        "name": "Issuer weekly fundamentals",
        "source": "MOPS",
        "grain": "issuer_week",
        "coverage": "2015–2026",
        "join_keys": ["issuer_id", "week"],
        "description": "Taiwan issuer fundamentals aligned to weekly market observations.",
        "analysis_readiness": "instant",
    },
    {
        "dataset_id": "attention_methods_paper",
        "name": "Measuring public attention with news data",
        "asset_kind": "scholarly_work",
        "doi": "10.1234/attention",
        "source": "DataCite",
        "description": "Scholarly methods paper on public attention proxies.",
        "analysis_readiness": "registered",
    },
]


def test_natural_language_query_ranks_by_recorded_evidence() -> None:
    ranked = rank_registry_assets(ROWS, "daily Asian news risk", limit=10)
    assert ranked[0]["dataset_id"] == "gdelt_asia_daily_country_panel"
    assert ranked[0]["match_confidence"] == "high"
    assert ranked[0]["match_evidence"]


def test_schema_field_is_retrievable_even_when_title_never_mentions_it() -> None:
    ranked = rank_registry_assets(ROWS, "country_iso3", limit=10)
    assert ranked[0]["dataset_id"] == "gdelt_asia_daily_country_panel"
    assert any(item["kind"] == "structure" for item in ranked[0]["match_evidence"])


def test_source_and_coverage_are_first_class_match_evidence() -> None:
    ranked = rank_registry_assets(ROWS, "GDELT 2018 2024", limit=10)
    assert ranked[0]["dataset_id"] == "gdelt_asia_daily_country_panel"
    kinds = {item["kind"] for item in ranked[0]["match_evidence"]}
    assert "source" in kinds
    assert "coverage" in kinds


def test_scholarly_vocabulary_reaches_registered_paper() -> None:
    ranked = rank_registry_assets(ROWS, "attention literature", limit=10)
    assert ranked[0]["dataset_id"] == "attention_methods_paper"


def test_one_accidental_fragment_does_not_force_a_multi_term_result() -> None:
    assert rank_registry_assets(ROWS, "weekly plutonium avocado telescope", limit=10) == []


def test_nested_provenance_and_schema_are_in_semantic_document() -> None:
    row = {
        "dataset_id": "nested",
        "schema": {"fields": [{"name": "block_timestamp"}, {"name": "tx_hash"}]},
        "procurement": {"source_url": "https://example.org/archive.csv", "method": "http_manifest"},
    }
    text = registry_search_document(row)
    assert "block_timestamp" in text
    assert "archive.csv" in text
    assert "http_manifest" in text


def test_engine_search_exposes_match_evidence_and_preserves_filters(tmp_path: Path) -> None:
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps({"datasets": ROWS}), encoding="utf-8")
    engine = ResearchQueryEngine(registry_path=registry, repo_root=tmp_path)

    rows = engine.search_datasets(q="country_iso3", readiness="instant", limit=10)
    assert [row["dataset_id"] for row in rows] == ["gdelt_asia_daily_country_panel"]
    assert rows[0]["match_terms"] == ["country_iso3"]
    assert rows[0]["match_evidence"][0]["kind"] == "structure"


def test_score_reports_coverage_not_a_mysterious_similarity_only() -> None:
    result = score_registry_asset(ROWS[0], "country daily GDELT")
    assert result["score"] > 0
    assert result["coverage"] >= 2 / 3
    assert len(result["match_evidence"]) >= 2
