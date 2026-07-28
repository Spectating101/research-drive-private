"""Registry materialization sync — honest instant promotion/demotion."""

from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_sync_materialized_registry_dry_run():
    from scripts.sync_materialized_registry import sync_registry

    out = sync_registry(dry_run=True)
    assert "promoted_to_instant" in out
    assert "demoted_to_metadata" in out
    assert out.get("registry_total", 0) >= 100
    assert out.get("procurement_index") is None


def test_refresh_procurement_catalog_writes_index(tmp_path):
    from scripts.sync_materialized_registry import refresh_procurement_catalog

    (tmp_path / "config").mkdir(parents=True)
    (tmp_path / "config" / "research_query_registry.json").write_text(
        json.dumps({"datasets": []}), encoding="utf-8"
    )
    (tmp_path / "config" / "collection_partitions.json").write_text(
        json.dumps({"partitions": []}), encoding="utf-8"
    )
    (tmp_path / "config" / "data_collection_queue.json").write_text(
        json.dumps({"tasks": []}), encoding="utf-8"
    )
    stats = refresh_procurement_catalog(tmp_path)
    assert stats.get("index_path")


def test_storage_tiers_fallback_to_local_when_cache_missing(tmp_path):
    from scripts.research_data_mcp.storage_tiers import resolve_data_path_tiered

    repo = tmp_path / "repo"
    lake = repo / "data_lake" / "news_shock_taxonomy" / "processed"
    lake.mkdir(parents=True)
    panel = lake / "gdelt_asia_daily_country_panel.parquet"
    panel.write_bytes(b"stub")

    # No bulk mounted — should resolve to local
    resolved = resolve_data_path_tiered(repo, "data_lake/news_shock_taxonomy/processed/gdelt_asia_daily_country_panel.parquet")
    assert resolved == panel.resolve()
