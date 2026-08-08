from __future__ import annotations


def test_declared_instant_without_bytes_is_not_query_instant(tmp_path):
    from scripts.research_data_mcp.registry_access import access_tier

    row = {
        "dataset_id": "panel",
        "backend": "local_parquet_panel",
        "analysis_readiness": "instant",
        "local_path": "data/panel.parquet",
    }
    assert access_tier(row, repo_root=tmp_path) == "metadata_search"


def test_instant_requires_observed_bytes(tmp_path):
    from scripts.research_data_mcp.registry_access import access_tier

    path = tmp_path / "data/panel.parquet"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"parquet-proof")
    row = {
        "dataset_id": "panel",
        "backend": "local_parquet_panel",
        "analysis_readiness": "instant",
        "local_path": "data/panel.parquet",
    }
    assert access_tier(row, repo_root=tmp_path) == "query_instant"


def test_runtime_mount_can_supply_observed_bytes(tmp_path, monkeypatch):
    from scripts.research_data_mcp.registry_access import access_tier

    runtime = tmp_path / "runtime"
    (runtime / "data").mkdir(parents=True)
    (runtime / "data/panel.parquet").write_bytes(b"parquet-proof")
    monkeypatch.setenv("YZU_RUNTIME_DRIVE_ROOT", str(runtime))
    row = {
        "dataset_id": "panel",
        "backend": "local_parquet_panel",
        "analysis_readiness": "instant",
        "local_path": "data/panel.parquet",
    }
    assert access_tier(row, repo_root=tmp_path) == "query_instant"


def test_nonlocal_instant_without_observation_stays_catalog_only(tmp_path):
    from scripts.research_data_mcp.registry_access import access_tier

    row = {
        "dataset_id": "remote",
        "backend": "live_connector",
        "analysis_readiness": "instant",
        "source_access_mode": "live_connector",
    }
    assert access_tier(row, repo_root=tmp_path) == "catalog_only"
