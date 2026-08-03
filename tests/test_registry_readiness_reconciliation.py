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


def test_malformed_csv_is_registered_for_schema_review_not_query_ready(tmp_path: Path) -> None:
    registry = tmp_path / "config/research_query_registry.json"
    registry.parent.mkdir()
    canonical = {
        "dataset_id": "co2_csv",
        "backend": "local_csv_file",
        "analysis_readiness": "query_ready",
        "local_path": "data_lake/procured/co2.csv",
        "canonical_remote": "gdrive:archive/co2_csv",
        "materialization": {"query_ready": True},
    }
    registry.write_text(json.dumps({"datasets": [canonical]}), encoding="utf-8")
    local = tmp_path / canonical["local_path"]
    local.parent.mkdir(parents=True)
    local.write_text(
        "Date,Decimal Date,Average,Interpolated,Trend,Number of Days\n"
        "1958-03,1958.2027,315.71,314.44,-01,-9.99,-0.99\n",
        encoding="utf-8",
    )

    engine = ResearchQueryEngine(registry, repo_root=tmp_path)
    effective = engine.describe("co2_csv")
    assert effective["analysis_readiness"] == "registered"
    assert effective["materialization"]["query_ready"] is False
    assert effective["materialization"]["skipped"] == "csv_schema_mismatch_at_runtime"
    assert effective["runtime_readiness_reason"] == "csv_schema_mismatch"
    assert effective["schema_review_required"] is True
    assert effective["schema_observation"]["header_columns"] == 6
    assert effective["schema_observation"]["observed_widths"] == [7]

    result = engine.query("co2_csv", limit=5).to_dict()
    assert result["rows"] == []
    assert result["meta"]["error"] == "schema_mismatch"
    assert result["meta"]["required_action"] == "review_schema"

    service = SearchService(engine, registry, tmp_path)
    preview = service.query_dataset("co2_csv", {"limit": 3})
    assert preview["rows"] == []
    assert preview["meta"]["error"] == "schema_mismatch"
    assert preview["meta"]["required_action"] == "review_schema"
    # Runtime reconciliation never rewrites the canonical registry claim.
    assert json.loads(registry.read_text(encoding="utf-8"))["datasets"][0]["analysis_readiness"] == "query_ready"


def test_well_formed_csv_remains_query_ready(tmp_path: Path) -> None:
    registry = tmp_path / "config/research_query_registry.json"
    registry.parent.mkdir()
    registry.write_text(
        json.dumps({"datasets": [{
            "dataset_id": "valid_csv",
            "backend": "local_csv_file",
            "analysis_readiness": "query_ready",
            "local_path": "data_lake/procured/valid.csv",
            "materialization": {"query_ready": True},
        }]}),
        encoding="utf-8",
    )
    local = tmp_path / "data_lake/procured/valid.csv"
    local.parent.mkdir(parents=True)
    local.write_text("date,value\n2026-01,1\n", encoding="utf-8")
    engine = ResearchQueryEngine(registry, repo_root=tmp_path)
    assert engine.describe("valid_csv")["analysis_readiness"] == "query_ready"
    assert engine.query("valid_csv", limit=5).rows == [{"date": "2026-01", "value": 1}]


@pytest.mark.parametrize(
    "content,expected_rows",
    [
        ("\ufeffdate,value\n2026-01,1\n", 1),
        ('date,note\n2026-01,"value, with comma"\n', 1),
        ('date,note\n2026-01,"line one\nline two"\n', 1),
        ("date,value\n\n2026-01,1\n\n2026-02,2\n", 2),
    ],
)
def test_csv_shape_accepts_valid_quoting_bom_and_blank_lines(
    tmp_path: Path, content: str, expected_rows: int
) -> None:
    path = tmp_path / "valid.csv"
    path.write_text(content, encoding="utf-8")
    observation = ResearchQueryEngine._csv_shape_observation(path)
    assert observation["valid"] is True
    assert observation["sampled_rows"] == expected_rows
    assert observation["observed_widths"] == [2]


@pytest.mark.parametrize(
    "content,observed_widths",
    [
        ("a,b,c\n1,2\n", [2]),
        ("a,b\n1,2,3\n", [3]),
        ("a,b\n1,2\n3,4,5\n", [2, 3]),
        ("a,b\n", []),
    ],
)
def test_csv_shape_rejects_short_wide_mixed_and_header_only_files(
    tmp_path: Path, content: str, observed_widths: list[int]
) -> None:
    path = tmp_path / "invalid.csv"
    path.write_text(content, encoding="utf-8")
    observation = ResearchQueryEngine._csv_shape_observation(path)
    assert observation["valid"] is False
    assert observation["reason"] == "column_count_mismatch"
    assert observation["observed_widths"] == observed_widths
