from __future__ import annotations

from pathlib import Path

import pytest

from scripts.research_query_engine.engine import ResearchQueryEngine


REPO_ROOT = Path(__file__).resolve().parents[1] / "drive"
REGISTRY = REPO_ROOT / "config/research_query_registry.json"


@pytest.fixture
def engine() -> ResearchQueryEngine:
    return ResearchQueryEngine(REGISTRY, repo_root=REPO_ROOT)


def test_registry_includes_fused_and_ticker_panels(engine: ResearchQueryEngine) -> None:
    ids = {d["dataset_id"] for d in engine.list_datasets()}
    assert "cross_asset_fused_primary_panel" in ids
    assert "ticker_week_entity_market_panel" in ids
    assert "collection_queue_status" in ids
    assert "investment_operator_dashboard" in ids
    assert "investment_accounting_bundle_latest" in ids
    assert "investment_repo_inventory_latest" in ids


@pytest.mark.skipif(
    not (REPO_ROOT / "data_lake/research_panels/cross_asset_fused/fused_20260610_v2/cross_asset_fused_primary_panel.parquet").exists(),
    reason="fused panel not built locally",
)
def test_query_cross_asset_panel(engine: ResearchQueryEngine) -> None:
    result = engine.query("cross_asset_fused_primary_panel", country="TWN", limit=3)
    assert result.rows
    assert "country_iso3" in result.rows[0]
    assert result.meta.get("run_id") == "fused_20260610_v2"


def test_collection_queue_status(engine: ResearchQueryEngine) -> None:
    result = engine.query("collection_queue_status")
    assert result.rows
    assert "task_count" in result.rows[0]


def test_plan_prefers_local_panels(engine: ResearchQueryEngine) -> None:
    result = engine.query("research_source_plan", q="asia news market crypto ticker panel")
    local = [r for r in result.rows if r.get("planning_source") == "local_parquet_panel"]
    assert local
    assert any("cross_asset" in r.get("dataset_id", "") or "ticker" in r.get("dataset_id", "") for r in local)


@pytest.mark.skipif(
    not (REPO_ROOT / "reports/investment_operator/latest.json").exists(),
    reason="investment operator report not built locally",
)
def test_query_investment_operator_dashboard(engine: ResearchQueryEngine) -> None:
    result = engine.query("investment_operator_dashboard", fields="status,warnings")
    assert result.rows
    assert "status" in result.rows[0]
    assert "warnings" in result.rows[0]


@pytest.mark.skipif(
    not (REPO_ROOT / "reports/repo_inventory/latest.json").exists(),
    reason="repo inventory report not built locally",
)
def test_query_investment_repo_inventory(engine: ResearchQueryEngine) -> None:
    result = engine.query("investment_repo_inventory_latest", fields="n_files,category_counts,disposition_counts")
    assert result.rows
    assert "n_files" in result.rows[0]
    assert "category_counts" in result.rows[0]
    assert "disposition_counts" in result.rows[0]
