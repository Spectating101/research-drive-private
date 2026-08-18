#!/usr/bin/env python3
"""Held bytes must be reachable when the declared path is merely imprecise.

Measured on the real registry: 27 glob-backend datasets declare a bare directory with
no wildcard, so globbing the literal path matched only the directory and returned
nothing; 4 more declare a glob whose files sit one level deeper. Separately, two weekly
panels name a run that exists but does not contain the panel file, while an older run
does. None of these are missing data.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.research_query_engine.engine import ResearchQueryEngine

@pytest.fixture(autouse=True)
def _isolate_data_roots(monkeypatch):
    """tmp_path only. Otherwise the live RESEARCH_DATA_ROOTS supplies real files."""
    monkeypatch.delenv("RESEARCH_DATA_ROOTS", raising=False)
    monkeypatch.delenv("SHARPE_REGISTRY_PATH", raising=False)



def _engine(tmp_path: Path, rows: list[dict]) -> ResearchQueryEngine:
    cfg = tmp_path / "config"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "research_query_registry.json").write_text(
        json.dumps({"version": "0.1", "datasets": rows}), encoding="utf-8"
    )
    return ResearchQueryEngine(repo_root=tmp_path)


def _glob_row(local_path: str) -> dict:
    return {
        "dataset_id": "probe_glob",
        "backend": "local_json_glob",
        "local_path": local_path,
    }


# ---------- glob depth ----------

def test_bare_directory_path_finds_nested_files(tmp_path: Path) -> None:
    """27 real datasets declare a directory with no wildcard at all."""
    d = tmp_path / "data_lake/scrapes/abc"
    (d / "run1").mkdir(parents=True)
    (d / "run1" / "extract.json").write_text(json.dumps({"a": 1}), encoding="utf-8")
    engine = _engine(tmp_path, [_glob_row("data_lake/scrapes/abc")])
    result = engine.query("probe_glob", limit=10)
    assert [r["file"] for r in result.rows] == ["extract.json"]


def test_glob_one_level_too_shallow_descends(tmp_path: Path) -> None:
    """The TWSE shape: pattern matches only landing directories."""
    d = tmp_path / "data_lake/twse"
    (d / "20260101").mkdir(parents=True)
    (d / "20260101" / "summary.json").write_text(json.dumps({"a": 1}), encoding="utf-8")
    engine = _engine(tmp_path, [_glob_row("data_lake/twse/*")])
    result = engine.query("probe_glob", limit=10)
    assert [r["file"] for r in result.rows] == ["summary.json"]


def test_a_matching_file_at_the_declared_depth_wins(tmp_path: Path) -> None:
    """Descending must never override what the registry actually declared."""
    d = tmp_path / "data_lake/twse"
    d.mkdir(parents=True)
    (d / "top.json").write_text(json.dumps({"a": 1}), encoding="utf-8")
    (d / "deeper").mkdir()
    (d / "deeper" / "nested.json").write_text(json.dumps({"a": 2}), encoding="utf-8")
    engine = _engine(tmp_path, [_glob_row("data_lake/twse/*")])
    result = engine.query("probe_glob", limit=10)
    assert [r["file"] for r in result.rows] == ["top.json"]


def test_genuinely_empty_directory_still_returns_nothing(tmp_path: Path) -> None:
    (tmp_path / "data_lake/empty").mkdir(parents=True)
    engine = _engine(tmp_path, [_glob_row("data_lake/empty/*")])
    result = engine.query("probe_glob", limit=10)
    assert result.rows == []


# ---------- panel run fallback ----------

def _panel_row(**kw) -> dict:
    row = {
        "dataset_id": "probe_panel",
        "backend": "local_parquet_panel",
        "local_root": "data_lake/panels",
        "local_file": "panel.csv",
        "default_run_id": "run_new",
    }
    row.update(kw)
    return row


def _write_panel(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("a,b\n1,2\n", encoding="utf-8")


def test_default_run_missing_the_file_falls_back_to_a_run_that_has_it(tmp_path: Path) -> None:
    """ticker_week_*: declared run exists, lacks the file, an older run holds it."""
    root = tmp_path / "data_lake/panels"
    (root / "run_new").mkdir(parents=True)          # exists, but no panel file
    _write_panel(root / "run_old" / "panel.csv")
    engine = _engine(tmp_path, [_panel_row()])
    result = engine.query("probe_panel", limit=5)
    assert len(result.rows) == 1
    assert result.meta.get("run_id") == "run_old"


def test_an_explicitly_requested_run_never_silently_falls_back(tmp_path: Path) -> None:
    """Asking for a named run and getting a different one would be a lie."""
    root = tmp_path / "data_lake/panels"
    (root / "run_new").mkdir(parents=True)
    _write_panel(root / "run_old" / "panel.csv")
    engine = _engine(tmp_path, [_panel_row()])
    with pytest.raises(FileNotFoundError):
        engine.query("probe_panel", run_id="run_new", limit=5)


def test_default_run_that_has_the_file_is_used_unchanged(tmp_path: Path) -> None:
    root = tmp_path / "data_lake/panels"
    _write_panel(root / "run_new" / "panel.csv")
    _write_panel(root / "run_old" / "panel.csv")
    engine = _engine(tmp_path, [_panel_row()])
    result = engine.query("probe_panel", limit=5)
    assert result.meta.get("run_id") == "run_new"
