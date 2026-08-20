#!/usr/bin/env python3
"""Every registry row lands in exactly one state, and the states reconcile.

Headline counts disagreed for weeks because they answered different questions. This pins the
report that reconciles them: 114 rows serve through the engine, 80 resolve to a single file
for synthesis, and the intersection — what an end-to-end journey actually needs — is what
`queryable` counts.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.research_query_engine.library_classification import STATES, classify


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    monkeypatch.delenv("RESEARCH_DATA_ROOTS", raising=False)


def _repo(tmp_path: Path, rows: list[dict]) -> Path:
    cfg = tmp_path / "config"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "research_query_registry.json").write_text(
        json.dumps({"version": "0.1", "datasets": rows}), encoding="utf-8"
    )
    return tmp_path


def test_every_row_gets_exactly_one_state(tmp_path):
    repo = _repo(tmp_path, [
        {"dataset_id": "declares_nothing", "backend": "local_csv_file"},
        {"dataset_id": "points_nowhere", "backend": "local_csv_file",
         "local_path": "data_lake/missing/file.csv"},
    ])
    report = classify(repo)
    assert report["registry_rows"] == 2
    assert sum(report["counts"].values()) == 2, report["counts"]
    assert set(report["counts"]) == set(STATES)


def test_a_row_with_no_declared_path_is_metadata_only(tmp_path):
    repo = _repo(tmp_path, [{"dataset_id": "x", "backend": "local_csv_file"}])
    assert classify(repo)["counts"]["metadata_only"] == 1


def test_a_declared_but_absent_path_is_absent_not_metadata(tmp_path):
    repo = _repo(tmp_path, [{"dataset_id": "x", "backend": "local_csv_file",
                             "local_path": "data_lake/nope/thing.csv"}])
    counts = classify(repo)["counts"]
    assert counts["absent"] == 1 and counts["metadata_only"] == 0


def test_a_readable_single_file_is_queryable(tmp_path):
    d = tmp_path / "data_lake/x"
    d.mkdir(parents=True)
    (d / "one.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    repo = _repo(tmp_path, [{"dataset_id": "x", "backend": "local_csv_file",
                             "local_path": "data_lake/x/one.csv"}])
    report = classify(repo)
    assert report["counts"]["queryable"] == 1
    assert report["end_to_end_capable"] == 1
