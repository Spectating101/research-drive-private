#!/usr/bin/env python3
"""hydrate_procured_from_acquisition copies staging bytes idempotently."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO), str(REPO / "kernel"), str(REPO / "drive")]

from scripts.research_query_engine.hydrate_procured_from_acquisition import hydrate


def test_hydrate_copies_raw_and_writes_manifest(tmp_path: Path):
    root = tmp_path / "repo"
    job = "job_demo"
    acq = root / "data_lake/yzu_cluster/acquisitions" / job
    raw = acq / "raw"
    raw.mkdir(parents=True)
    (raw / "sample.txt").write_text("hello-research-drive\n", encoding="utf-8")
    meta = {
        "job_id": job,
        "dataset_id": "procured_demo",
        "manifest_id": "collection_manifest_job_demo",
        "canonical_dir": "data_lake/procured/demo_asset",
        "files": [{"name": "sample.txt", "bytes": 21}],
    }
    (acq / "meta.json").write_text(json.dumps(meta), encoding="utf-8")

    result = hydrate(repo_root=root, job_id=job, dry_run=False)
    assert result["ok"] is True
    dest = root / "data_lake/procured/demo_asset"
    assert (dest / "sample.txt").read_text(encoding="utf-8") == "hello-research-drive\n"
    manifest = json.loads((dest / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["dataset_id"] == "procured_demo"
    assert manifest["source"] == "hydrated_from_acquisition_staging"

    again = hydrate(repo_root=root, job_id=job, dry_run=False)
    assert again["ok"] is True
    assert any(row["action"] == "skip_identical" for row in again["files"])


def test_hydrate_refuses_checksum_mismatch(tmp_path: Path):
    root = tmp_path / "repo"
    job = "job_bad"
    acq = root / "data_lake/yzu_cluster/acquisitions" / job
    raw = acq / "raw"
    raw.mkdir(parents=True)
    (raw / "sample.txt").write_text("new\n", encoding="utf-8")
    (acq / "meta.json").write_text(
        json.dumps(
            {
                "job_id": job,
                "dataset_id": "procured_demo",
                "canonical_dir": "data_lake/procured/demo_asset",
            }
        ),
        encoding="utf-8",
    )
    dest = root / "data_lake/procured/demo_asset"
    dest.mkdir(parents=True)
    (dest / "sample.txt").write_text("old\n", encoding="utf-8")

    result = hydrate(repo_root=root, job_id=job, dry_run=True)
    assert result["ok"] is False
    assert any(row["action"] == "refuse_mismatch" for row in result["files"])
