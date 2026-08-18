#!/usr/bin/env python3
"""Compensating for a wrong catalogue entry silently is not the same as fixing it.

Synthesis reports source_rows, a per-step row ledger and an as-of match rate, so a
result can be judged. A store query that quietly descends two levels below the declared
path leaves the caller unable to tell a precise holding from a lucky one, and leaves 31
wrong registry entries invisible and therefore permanent.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.research_query_engine.engine import ResearchQueryEngine


@pytest.fixture(autouse=True)
def _isolate_data_roots(monkeypatch):
    monkeypatch.delenv("RESEARCH_DATA_ROOTS", raising=False)
    monkeypatch.delenv("SHARPE_REGISTRY_PATH", raising=False)


def _engine(tmp_path: Path, local_path: str) -> ResearchQueryEngine:
    cfg = tmp_path / "config"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "research_query_registry.json").write_text(
        json.dumps(
            {
                "version": "0.1",
                "datasets": [
                    {
                        "dataset_id": "probe",
                        "backend": "local_json_glob",
                        "local_path": local_path,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return ResearchQueryEngine(repo_root=tmp_path)


def test_a_precise_pattern_reports_no_drift(tmp_path: Path) -> None:
    d = tmp_path / "data_lake/x"
    d.mkdir(parents=True)
    (d / "a.json").write_text("{}", encoding="utf-8")
    result = _engine(tmp_path, "data_lake/x/*").query("probe", limit=5)
    res = result.meta["resolution"]
    assert res["depth"] == "declared"
    assert res["registry_drift"] is False
    assert res["matched"] == 1


def test_descending_is_reported_as_drift_with_the_depth_used(tmp_path: Path) -> None:
    d = tmp_path / "data_lake/x/20260101"
    d.mkdir(parents=True)
    (d / "a.json").write_text("{}", encoding="utf-8")
    result = _engine(tmp_path, "data_lake/x/*").query("probe", limit=5)
    res = result.meta["resolution"]
    assert res["registry_drift"] is True
    assert res["depth"] == "+1"
    assert res["declared"] == "data_lake/x/*"
    assert res["served_pattern"].endswith("data_lake/x/*/*")
    assert res["matched"] == 1


def test_a_wildcard_free_directory_reports_a_recursive_read(tmp_path: Path) -> None:
    d = tmp_path / "data_lake/scrape/run1"
    d.mkdir(parents=True)
    (d / "extract.json").write_text("{}", encoding="utf-8")
    result = _engine(tmp_path, "data_lake/scrape").query("probe", limit=5)
    res = result.meta["resolution"]
    assert res["depth"] == "recursive"
    assert res["registry_drift"] is True


def test_finding_nothing_still_reports_what_was_tried(tmp_path: Path) -> None:
    (tmp_path / "data_lake/empty").mkdir(parents=True)
    result = _engine(tmp_path, "data_lake/empty/*").query("probe", limit=5)
    res = result.meta["resolution"]
    assert res["matched"] == 0
    assert res["depth"] == "none"
    assert res["registry_drift"] is False
