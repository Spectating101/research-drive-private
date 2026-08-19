from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from scripts.research_data_mcp.synthesis.integrity_sweep import check_dataset
from scripts.sync_materialized_registry import sync_registry


def _write_registry(root: Path, row: dict) -> Path:
    path = root / "config/research_query_registry.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"datasets": [row]}), encoding="utf-8")
    return path


def test_integrity_reports_multi_file_glob_as_held_not_absent(tmp_path: Path) -> None:
    (tmp_path / "data/submissions").mkdir(parents=True)
    (tmp_path / "data/submissions/A.json").write_text('{"ticker":"A"}\n', encoding="utf-8")
    (tmp_path / "data/submissions/B.json").write_text('{"ticker":"B"}\n', encoding="utf-8")
    row = {
        "dataset_id": "sec_fixture",
        "backend": "local_json_glob",
        "local_path": "data/submissions/*.json",
    }
    result = check_dataset(tmp_path, row)
    assert result["status"] == "held_not_single_file"
    assert result["data_files"] == 2
    assert result["bytes"] > 0


def test_materialization_sync_rejects_corrupt_parquet(tmp_path: Path) -> None:
    target = tmp_path / "data/panel/broken.parquet"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"PAR1" + b"not-a-parquet-file" + b"PAR1")
    _write_registry(
        tmp_path,
        {
            "dataset_id": "broken_panel",
            "backend": "local_parquet_panel",
            "analysis_readiness": "instant",
            "source_access_mode": "materialized_instant",
            "local_root": "data/panel",
            "local_file": "broken.parquet",
        },
    )

    report = sync_registry(dry_run=True, repo_root=tmp_path)

    assert report["demoted_to_metadata"] == ["broken_panel"]
    assert "broken_panel" not in report["promoted_to_instant"]


def test_materialization_sync_accepts_readable_parquet(tmp_path: Path) -> None:
    target = tmp_path / "data/panel/good.parquet"
    target.parent.mkdir(parents=True)
    pd.DataFrame({"id": [1, 2]}).to_parquet(target, index=False)
    _write_registry(
        tmp_path,
        {
            "dataset_id": "good_panel",
            "backend": "local_parquet_panel",
            "analysis_readiness": "metadata_search",
            "local_root": "data/panel",
            "local_file": "good.parquet",
        },
    )

    report = sync_registry(dry_run=True, repo_root=tmp_path)

    assert report["promoted_to_instant"] == ["good_panel"]
    assert report["demoted_to_metadata"] == []
