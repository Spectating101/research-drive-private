from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.research_data_mcp.inventory_authority import (
    SCOPE_DESK_VISIBLE,
    SCOPE_REGISTRY_ALL,
    assert_same_authority,
    build_inventory_summary,
    inventory_compatible,
    is_excluded_operational_or_test,
)
from scripts.research_data_mcp.search import SearchService
from scripts.research_query_engine.engine import ResearchQueryEngine


def _write_registry(tmp_path: Path, rows: list[dict]) -> tuple[Path, Path]:
    config = tmp_path / "config"
    config.mkdir(parents=True, exist_ok=True)
    (config / "collection_partitions.json").write_text(
        json.dumps({"version": 1, "partitions": []}),
        encoding="utf-8",
    )
    registry = config / "research_query_registry.json"
    registry.write_text(
        json.dumps({"updated_at": "2026-07-25T00:00:00Z", "datasets": rows}),
        encoding="utf-8",
    )
    return tmp_path, registry


def _service(root: Path, registry: Path) -> SearchService:
    return SearchService(ResearchQueryEngine(registry, repo_root=root), registry, root)


def _rows() -> list[dict]:
    return [
        {
            "dataset_id": "desk_panel",
            "name": "Desk panel",
            "backend": "local_json_file",
            "analysis_readiness": "instant",
            "materialization": {"query_ready": True},
        },
        {
            "dataset_id": "desk_meta",
            "name": "Desk meta",
            "backend": "local_json_file",
            "analysis_readiness": "metadata_search",
            "materialization": {"query_ready": False},
        },
        {
            "dataset_id": "collection_queue_status",
            "name": "Queue status",
            "backend": "collection_ops_status",
            "access_shape": "ops_status",
            "analysis_readiness": "metadata_search",
        },
        {
            "dataset_id": "fixture_smoke_test",
            "name": "Fixture",
            "backend": "local_json_file",
            "analysis_readiness": "registered",
            "tags": ["test", "fixture"],
        },
    ]


def test_inventory_projection_separates_registered_visible_and_query_ready(tmp_path: Path) -> None:
    root, registry = _write_registry(tmp_path, _rows())
    service = _service(root, registry)

    inventory = service.inventory_summary(include_partition_lanes=False)
    overview = service.library_overview()
    listed = service.list_datasets(limit=50)

    assert inventory["version"] == 1
    assert inventory["totals"]["registered"] == 4
    assert inventory["totals"]["visible_to_desk"] == 2
    assert inventory["totals"]["excluded_operational_test"] == 2
    assert inventory["by_analysis_readiness"]["registered"]["instant"] == 1
    assert inventory["by_materialization_query_ready"]["registered"]["true"] == 1
    assert inventory["by_materialization_query_ready"]["registered"]["false"] == 1
    assert inventory["semantics"]["completed_ne_registered_ne_query_ready"] is True

    assert overview["view_scope"]["scope"] == SCOPE_DESK_VISIBLE
    assert overview["total_datasets"] == 2
    assert overview["registered_datasets"] == 4
    assert overview["inventory"]["registry_revision"]["fingerprint"] == inventory["registry_revision"]["fingerprint"]

    assert listed["inventory"]["registry_revision"]["fingerprint"] == inventory["registry_revision"]["fingerprint"]
    assert listed["authority_summary"]["registry_total"] == 4
    assert listed["view_scope"]["scope"] == SCOPE_DESK_VISIBLE
    assert listed["view_scope"]["primary_total"] == inventory["totals"]["visible_to_desk"]

    # The registry and desk list are projections of the same authority but
    # intentionally declare different scopes and primary totals.
    assert_same_authority(
        {"inventory": inventory, "view_scope": {"scope": SCOPE_REGISTRY_ALL, "primary_total": 4}},
        {"inventory": listed["inventory"], "view_scope": listed["view_scope"]},
        expect_same_scope=False,
    )
    assert inventory_compatible(overview, listed)

    # Registry file must remain untouched by readiness / inventory projection.
    on_disk = json.loads(registry.read_text(encoding="utf-8"))
    assert len(on_disk["datasets"]) == 4
    assert on_disk["datasets"][0]["analysis_readiness"] == "instant"


def test_silent_mismatch_is_detected_when_totals_diverge_under_shared_fingerprint(tmp_path: Path) -> None:
    root, registry = _write_registry(tmp_path, _rows())
    inventory = build_inventory_summary(
        _rows(),
        registry_path=registry,
        repo_root=root,
        include_partition_lanes=False,
    )
    left = {
        "inventory": inventory,
        "view_scope": {"scope": SCOPE_DESK_VISIBLE, "primary_total": inventory["totals"]["visible_to_desk"]},
    }
    right = {
        "inventory": inventory,
        "view_scope": {"scope": SCOPE_DESK_VISIBLE, "primary_total": 999},
    }
    with pytest.raises(AssertionError, match="silent primary_total mismatch"):
        assert_same_authority(left, right)

    # Different scopes are allowed to disagree on primary totals.
    assert_same_authority(
        left,
        {
            "inventory": inventory,
            "view_scope": {"scope": SCOPE_REGISTRY_ALL, "primary_total": inventory["totals"]["registered"]},
        },
        expect_same_scope=False,
    )


def test_excluded_operational_and_test_markers() -> None:
    assert is_excluded_operational_or_test({"access_shape": "ops_status", "dataset_id": "x"})
    assert is_excluded_operational_or_test({"backend": "collection_ops_status", "dataset_id": "x"})
    assert is_excluded_operational_or_test({"dataset_id": "demo_test", "tags": ["test"]})
    assert is_excluded_operational_or_test({"dataset_id": "fixture_smoke_test"})
    assert not is_excluded_operational_or_test(
        {"dataset_id": "asia_panel", "backend": "local_parquet_panel", "analysis_readiness": "instant"}
    )


def test_gateway_endpoints_share_inventory_fingerprint(tmp_path: Path) -> None:
    root, registry = _write_registry(tmp_path, _rows())
    # Minimal generated caches so platform/consolidated attach live inventory
    # without requiring full audit builders.
    generated = root / "drive/docs/status/generated"
    generated.mkdir(parents=True)
    (generated / "consolidated_state.json").write_text(
        json.dumps({"headline": {"registry_datasets": 1}, "generated_at": "stale"}),
        encoding="utf-8",
    )
    (root / "config/databank_source_map.json").write_text(
        json.dumps({"version": 1, "sources": [], "access_modes": {}, "capabilities_glossary": {}}),
        encoding="utf-8",
    )
    (root / "config/desk_sources.json").write_text(json.dumps({"sources": []}), encoding="utf-8")

    from scripts.research_data_mcp.gateway import ResearchDataGateway

    gateway = ResearchDataGateway(root, registry)
    datasets = gateway.list_datasets(limit=50)
    overview = gateway.library_overview()
    platform = gateway.platform_state()
    source_map = gateway.source_map_audit(live=True)
    consolidated = gateway.consolidated_state(live=False)

    fp = datasets["inventory"]["registry_revision"]["fingerprint"]
    assert fp
    assert overview["inventory"]["registry_revision"]["fingerprint"] == fp
    assert platform["inventory"]["registry_revision"]["fingerprint"] == fp
    assert source_map["inventory"]["registry_revision"]["fingerprint"] == fp
    assert consolidated["inventory"]["registry_revision"]["fingerprint"] == fp
    assert consolidated["headline"]["registry_datasets"] == 1  # cached headline may lag
    assert consolidated["inventory"]["totals"]["registered"] == 4  # live authority

    from scripts.research_data_mcp.consolidated_state import composer_procurement_snapshot

    snapshot = composer_procurement_snapshot(consolidated)
    assert snapshot["freshness"]["snapshot_stale"] is True
    assert snapshot["freshness"]["snapshot_registry_datasets"] == 1
    assert snapshot["freshness"]["live_registry_datasets"] == 4
    assert snapshot["freshness"]["authority"] == "inventory.registry_revision + inventory.totals"

    assert datasets["inventory"]["totals"] == overview["inventory"]["totals"]
    assert platform["view_scope"]["scope"] == SCOPE_REGISTRY_ALL
    assert overview["view_scope"]["scope"] == SCOPE_DESK_VISIBLE
    assert overview["total_datasets"] == datasets["inventory"]["totals"]["visible_to_desk"]
    assert datasets["view_scope"]["scope"] == SCOPE_DESK_VISIBLE
    assert datasets["view_scope"]["primary_total"] == datasets["inventory"]["totals"]["visible_to_desk"]

    # Catch a silent mismatch if an endpoint claims the same fingerprint but
    # mutates declared registered totals.
    broken = json.loads(json.dumps(overview))
    broken["inventory"]["totals"]["registered"] = 1
    with pytest.raises(AssertionError, match="inventory totals diverged"):
        assert_same_authority(datasets, broken, expect_same_scope=False)
