from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.research_data_mcp.search import SearchService
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
    assert missing["materialization"]["skipped"] == "local_bytes_missing_at_runtime"
    assert missing["materialization"]["expected_path"] == "data_lake/missing/missing.parquet"
    assert missing["runtime_readiness_reason"] == "local_bytes_missing"
    assert json.loads(registry.read_text(encoding="utf-8"))["datasets"][0]["analysis_readiness"] == "instant"

    assert engine.describe("ready_panel")["analysis_readiness"] == "instant"


def test_remote_query_ready_file_is_effectively_registered_until_hydrated(tmp_path: Path) -> None:
    registry = tmp_path / "config/research_query_registry.json"
    registry.parent.mkdir()
    registry.write_text(
        json.dumps(
            {
                "datasets": [
                    {
                        "dataset_id": "remote_csv",
                        "backend": "local_csv_file",
                        "analysis_readiness": "query_ready",
                        "source_access_mode": "materialized_query_ready",
                        "local_path": "data_lake/procured/remote.csv",
                        "canonical_remote": "gdrive:archive/remote_csv",
                        "source_of_truth": "gdrive",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    engine = ResearchQueryEngine(registry, repo_root=tmp_path)
    effective = engine.describe("remote_csv")

    assert effective["analysis_readiness"] == "registered"
    assert effective["materialization"]["query_ready"] is False
    assert effective["runtime_readiness_reason"] == "local_bytes_missing"
    assert effective["hydrate_required"] is True
    assert json.loads(registry.read_text(encoding="utf-8"))["datasets"][0]["analysis_readiness"] == "query_ready"

    hydrated = tmp_path / "data_lake/procured/remote.csv"
    hydrated.parent.mkdir(parents=True)
    hydrated.write_text("date,value\n2026-01,1\n", encoding="utf-8")
    refreshed = ResearchQueryEngine(registry, repo_root=tmp_path).describe("remote_csv")
    assert refreshed["analysis_readiness"] == "query_ready"
    assert "hydrate_required" not in refreshed


def test_remote_query_requires_explicit_hydration_then_returns_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = tmp_path / "config/research_query_registry.json"
    registry.parent.mkdir()
    registry.write_text(
        json.dumps(
            {
                "datasets": [
                    {
                        "dataset_id": "remote_csv",
                        "backend": "local_csv_file",
                        "analysis_readiness": "query_ready",
                        "local_path": "data_lake/procured/remote.csv",
                        "canonical_remote": "gdrive:archive/remote_csv",
                        "source_of_truth": "gdrive",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    service = SearchService(ResearchQueryEngine(registry, repo_root=tmp_path), registry, tmp_path)

    def fake_hydrate(repo_root: Path, spec: dict, *, dry_run: bool = False) -> dict:
        if dry_run:
            return {"dry_run": True, "plan": {"dataset_id": spec["dataset_id"]}}
        local = repo_root / spec["local_path"]
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_text("date,value\n2026-01,1\n", encoding="utf-8")
        return {"ok": True, "local_path": spec["local_path"]}

    monkeypatch.setattr(
        "scripts.research_data_mcp.registry_hydrate.ensure_registry_local_bytes",
        fake_hydrate,
    )

    guarded = service.query_dataset("remote_csv", {"limit": 101})
    assert guarded["rows"] == []
    assert guarded["meta"]["error"] == "not_query_ready"
    assert guarded["meta"]["required_action"] == "hydrate"

    hydrated = service.query_dataset("remote_csv", {"limit": 5, "hydrate": "1"})
    assert hydrated["rows"] == [{"date": "2026-01", "value": 1}]
    assert service.describe_dataset("remote_csv")["analysis_readiness"] == "query_ready"
