#!/usr/bin/env python3
"""The compensation must name what it compensated for."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.research_query_engine.registry_drift import scan


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    monkeypatch.delenv("RESEARCH_DATA_ROOTS", raising=False)
    monkeypatch.delenv("SHARPE_REGISTRY_PATH", raising=False)


def _repo(tmp_path: Path, rows: list[dict]) -> Path:
    cfg = tmp_path / "config"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "research_query_registry.json").write_text(
        json.dumps({"version": "0.1", "datasets": rows}), encoding="utf-8"
    )
    return tmp_path


def test_drift_is_named_with_the_pattern_that_served(tmp_path: Path) -> None:
    (tmp_path / "data_lake/deep/20260101").mkdir(parents=True)
    (tmp_path / "data_lake/deep/20260101/a.json").write_text("{}", encoding="utf-8")
    (tmp_path / "data_lake/flat").mkdir(parents=True)
    (tmp_path / "data_lake/flat/b.json").write_text("{}", encoding="utf-8")
    repo = _repo(
        tmp_path,
        [
            {"dataset_id": "deep", "backend": "local_json_glob", "local_path": "data_lake/deep/*"},
            {"dataset_id": "flat", "backend": "local_json_glob", "local_path": "data_lake/flat/*"},
        ],
    )
    report = scan(repo)
    assert report["glob_datasets"] == 2
    assert report["declared_correctly"] == 1
    assert [r["dataset_id"] for r in report["drifted"]] == ["deep"]
    drift = report["drifted"][0]
    assert drift["depth"] == "+1"
    assert drift["served_pattern"].endswith("data_lake/deep/*/*")


def test_a_dataset_with_no_files_is_not_reported_as_drift(tmp_path: Path) -> None:
    (tmp_path / "data_lake/empty").mkdir(parents=True)
    repo = _repo(
        tmp_path,
        [{"dataset_id": "e", "backend": "local_json_glob", "local_path": "data_lake/empty/*"}],
    )
    report = scan(repo)
    assert report["drifted"] == []
    assert report["no_files_at_any_depth"] == ["e"]
