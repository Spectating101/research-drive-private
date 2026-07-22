from __future__ import annotations

import json
import zipfile
from pathlib import Path

from scripts.yzu_cluster.acquisitions import materialize_job


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
