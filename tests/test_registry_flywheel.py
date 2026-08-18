from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.research_data_mcp.collection_flywheel import CollectionFlywheel
from scripts.research_data_mcp.registry_promotion import RegistryPromoter


@pytest.fixture(autouse=True)
def _isolate_data_roots(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep this tmp-path promotion test away from a caller's real bulk index."""
    for var in (
        "DATACITE_TOPIC_INDEX_ON_BULK",
        "DATACITE_TOPIC_INDEX_ROOT",
        "DATACITE_INDEX_V3_ROOT",
        "DATACITE_LOCAL_ROOT",
        "RESEARCH_BULK_ROOT",
        "RESEARCH_DATA_ROOTS",
    ):
        monkeypatch.delenv(var, raising=False)


def _enable_drive_first(repo: Path) -> None:
    """Give isolated promotion tests the same storage policy as production."""
    config = repo / "config"
    config.mkdir(parents=True, exist_ok=True)
    (config / "storage_tiers.json").write_text(
        json.dumps({"rules": {"drive_first": True}}),
        encoding="utf-8",
    )


def test_pipeline_promotion_resolves_latest_skynet_harvest(tmp_path: Path) -> None:
    repo = tmp_path
    _enable_drive_first(repo)
    harvest_root = repo / "stablecoin_skynet/data/harvest_20260101T000000Z"
    (harvest_root / "projects").mkdir(parents=True)
    (harvest_root / "projects/tether.json").write_text('{"slug":"tether"}', encoding="utf-8")
    (harvest_root / "manifest.json").write_text("{}", encoding="utf-8")

    map_path = repo / "config/procurement_registry_map.json"
    map_path.parent.mkdir(parents=True, exist_ok=True)
    map_path.write_text(
        json.dumps(
            {
                "pipelines": {
                    "skynet_stablecoin_harvest": {
                        "dataset_id": "skynet_stablecoin_harvest",
                        "name": "Skynet test",
                        "backend": "local_json_glob",
                        "access_shape": "local_file_tree",
                        "analysis_readiness": "metadata_search",
                        "path_resolver": "latest_skynet_harvest_projects",
                        "capabilities": ["limit"],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    registry_path = repo / "config/research_query_registry.json"
    registry_path.write_text(json.dumps({"version": "0.1", "datasets": []}), encoding="utf-8")

    promoter = RegistryPromoter(repo, registry_path, map_path)
    job = {
        "id": "job1",
        "status": "completed",
        "plan": {"job_type": "registered_pipeline", "pipeline_id": "skynet_stablecoin_harvest"},
        "result": {},
    }
    promoted = promoter.promote_job(job)
    assert len(promoted) == 1
    assert promoted[0]["dataset_id"] == "skynet_stablecoin_harvest"

    reg = json.loads(registry_path.read_text(encoding="utf-8"))
    row = next(d for d in reg["datasets"] if d["dataset_id"] == "skynet_stablecoin_harvest")
    assert "harvest_20260101T000000Z/projects/*.json" in row["local_path"]

    flywheel = CollectionFlywheel(repo, registry_path)
    fw = flywheel.promote_after_collect(job, promoted, search_goal="stablecoin skynet")
    assert fw.get("curated_added", 0) >= 1
