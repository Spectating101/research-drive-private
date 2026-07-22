from __future__ import annotations

import json
from pathlib import Path

from scripts.research_query_engine.engine import ResearchQueryEngine


def _panel(dataset_id: str, root: str, file_name: str) -> dict:
    return {
        "dataset_id": dataset_id,
        "backend": "local_parquet_panel",
        "analysis_readiness": "instant",
        "local_root": root,
        "local_file": file_name,
        "materialization": {"query_ready": True, "resolved_path": f"{root}/{file_name}"},
    }


def test_missing_local_panel_is_downgraded_without_mutating_registry_file(tmp_path: Path) -> None:
    registry = tmp_path / "config/research_query_registry.json"
    registry.parent.mkdir()
    registry.write_text(
        json.dumps(
            {
                "datasets": [
                    _panel("missing_panel", "data_lake/missing", "missing.parquet"),
                    _panel("ready_panel", "data_lake/ready", "ready.parquet"),
                ]
            }
        ),
        encoding="utf-8",
    )
    ready = tmp_path / "data_lake/ready/ready.parquet"
    ready.parent.mkdir(parents=True)
    ready.write_bytes(b"placeholder")

    engine = ResearchQueryEngine(registry, repo_root=tmp_path)

    missing = engine.describe("missing_panel")
    assert missing["analysis_readiness"] == "metadata_search"
    assert missing["materialization"]["query_ready"] is False
    assert missing["materialization"]["skipped"] == "local_panel_missing_at_runtime"
    assert missing["materialization"]["expected_path"] == "data_lake/missing/missing.parquet"
    assert missing["runtime_readiness_reason"] == "local_panel_missing"
    assert json.loads(registry.read_text(encoding="utf-8"))["datasets"][0]["analysis_readiness"] == "instant"

    assert engine.describe("ready_panel")["analysis_readiness"] == "instant"
