from __future__ import annotations

import json
import zipfile
from pathlib import Path

from scripts.yzu_cluster.acquisitions import materialize_job, registry_spec_from_materialized


def test_materialized_collection_emits_manifest_for_declared_dataset(tmp_path: Path) -> None:
    archive = tmp_path / "source.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("raw/usdt.csv", "timestamp,value\n2020-01-01,1\n")

    result = materialize_job(
        tmp_path,
        "collect-usdt",
        {"dataset_id": "raw_usdt_history", "validation": {"min_files": 1, "min_total_bytes": 1}},
        {"artifacts": [{"artifact": "source.zip"}]},
    )

    materialized = result["materialized"]
    manifest_path = tmp_path / materialized["manifest_path"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert result["output_manifest_id"] == materialized["manifest_id"]
    assert manifest["manifest_id"] == materialized["manifest_id"]
    assert manifest["output"]["dataset_id"] == "raw_usdt_history"
    assert manifest["validation"]["ok"] is True


def test_declared_dataset_identity_wins_over_connector_identity(tmp_path: Path) -> None:
    archive = tmp_path / "source.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("raw/tickers.json", '{"ticker": "ACME"}\n')

    result = materialize_job(
        tmp_path,
        "collect-tickers",
        {
            "dataset_id": "sec_company_tickers_snapshot",
            "connector_id": "sec_edgar",
            "validation": {"min_files": 1, "min_total_bytes": 1},
        },
        {"artifacts": [{"artifact": "source.zip"}]},
    )

    assert result["materialized"]["dataset_id"] == "sec_company_tickers_snapshot"
    assert result["output_manifest_id"] == "collection_manifest_collect-tickers"


def test_single_materialized_file_registers_a_file_path_not_directory(tmp_path: Path) -> None:
    spec = registry_spec_from_materialized(
        tmp_path,
        {"id": "collect-json", "plan": {"title": "JSON canary", "job_type": "http_manifest"}},
        {
            "dataset_id": "json_canary",
            "canonical_dir": "data_lake/procured/json_canary",
            "files": [{"name": "payload.json", "bytes": 128}],
        },
    )

    assert spec is not None
    assert spec["backend"] == "local_json_file"
    assert spec["local_path"].endswith("data_lake/procured/json_canary/payload.json")
    assert spec["analysis_readiness"] == "instant"


def test_multiple_json_files_register_as_queryable_json_glob(tmp_path: Path) -> None:
    spec = registry_spec_from_materialized(
        tmp_path,
        {"id": "collect-json-pair", "plan": {"title": "JSON pair", "job_type": "http_manifest"}},
        {
            "dataset_id": "json_pair",
            "canonical_dir": "data_lake/procured/json_pair",
            "files": [
                {"name": "first.json", "bytes": 128},
                {"name": "second.json", "bytes": 256},
            ],
        },
    )

    assert spec is not None
    assert spec["backend"] == "local_json_glob"
    assert spec["local_path"].endswith("data_lake/procured/json_pair/*")


def test_single_parquet_registers_local_root_and_local_file(tmp_path: Path) -> None:
    """Single parquet must expose local_root/local_file so _resolve_panel_path can query it."""
    local_path = "data_lake/procured/panel_canary/panel.parquet"
    spec = registry_spec_from_materialized(
        tmp_path,
        {"id": "collect-parquet", "plan": {"title": "Parquet canary", "job_type": "http_manifest"}},
        {
            "dataset_id": "panel_canary",
            "canonical_dir": "data_lake/procured/panel_canary",
            "files": [{"name": "panel.parquet", "bytes": 4096}],
        },
    )

    assert spec is not None
    assert spec["backend"] == "local_parquet_panel"
    assert spec["local_path"] == local_path
    assert spec["local_root"] == "data_lake/procured/panel_canary"
    assert spec["local_file"] == "panel.parquet"
    assert spec["analysis_readiness"] == "instant"
