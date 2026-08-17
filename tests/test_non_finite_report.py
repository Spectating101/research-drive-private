"""inf in source data is reported, never silently rewritten."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.research_data_mcp.synthesis_executor import preflight_execution_spec


def _repo(tmp_path: Path, frame: pd.DataFrame) -> Path:
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    frame.to_parquet(tmp_path / "data/a.parquet")
    (tmp_path / "config/research_query_registry.json").write_text(json.dumps({"datasets": [
        {"dataset_id": "a", "name": "a", "local_path": "data/a.parquet", "grain": "g", "join_keys": ["k"]}
    ]}), encoding="utf-8")
    return tmp_path


def _spec():
    return {
        "input_dataset_id": "a",
        "output_dataset_id": "synthesis_non_finite_v1",
        "group_by": ["k"],
        "metrics": [{"function": "mean", "column": "v", "as": "out"}],
    }


def test_inf_in_source_is_reported(tmp_path):
    repo = _repo(tmp_path, pd.DataFrame({"k": ["x", "y"], "v": [np.inf, 1.0]}))
    report = preflight_execution_spec(repo, _spec())
    assert any("non-finite" in w for w in report["warnings"])
    assert any("a.v" in w for w in report["warnings"])


def test_negative_inf_counts_too(tmp_path):
    repo = _repo(tmp_path, pd.DataFrame({"k": ["x", "y"], "v": [-np.inf, np.inf]}))
    report = preflight_execution_spec(repo, _spec())
    warn = next(w for w in report["warnings"] if "non-finite" in w)
    assert "2 non-finite" in warn


def test_clean_data_produces_no_non_finite_warning(tmp_path):
    repo = _repo(tmp_path, pd.DataFrame({"k": ["x", "y"], "v": [1.0, 2.0]}))
    report = preflight_execution_spec(repo, _spec())
    assert not any("non-finite" in w for w in report["warnings"])


def test_nan_is_not_reported_as_non_finite(tmp_path):
    """NaN is a normal missing value; aggregates skip it. Only inf is the hazard."""
    repo = _repo(tmp_path, pd.DataFrame({"k": ["x", "y"], "v": [np.nan, 2.0]}))
    report = preflight_execution_spec(repo, _spec())
    assert not any("non-finite" in w for w in report["warnings"])


def test_reporting_does_not_block_execution(tmp_path):
    repo = _repo(tmp_path, pd.DataFrame({"k": ["x", "y"], "v": [np.inf, 1.0]}))
    report = preflight_execution_spec(repo, _spec())
    assert report["ok"] is True
