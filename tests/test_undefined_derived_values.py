"""A value that blew up is masked to NaN — say how many, or 0.0 lies.

Dividing by zero yields inf, which _finite turns into NaN so a mean() cannot
report a finite-looking number built on it. But sum() of an all-NaN group
returns 0.0, and a researcher reads 0.0 as a measured zero. The count is what
separates "the total is zero" from "there was nothing to total".
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from scripts.research_data_mcp.synthesis_executor import execute


def _repo(tmp_path: Path, frame: pd.DataFrame) -> Path:
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    frame.to_parquet(tmp_path / "data/a.parquet")
    (tmp_path / "config/research_query_registry.json").write_text(
        json.dumps({"datasets": [{"dataset_id": "a", "name": "a",
                                  "local_path": "data/a.parquet", "grain": "row"}]}),
        encoding="utf-8")
    return tmp_path


def _spec(**over):
    spec = {
        "input_dataset_id": "a",
        "output_dataset_id": "synthesis_undefined_probe",
        "group_by": ["g"],
        "metrics": [{"function": "sum", "column": "ratio", "as": "r"}],
        "transforms": [{"op": "derive", "as": "ratio", "fn": "div",
                        "column": "num", "by_column": "den"}],
    }
    spec.update(over)
    return spec


FRAME = pd.DataFrame({"g": ["a", "a", "b"], "num": [10.0, 20.0, 30.0], "den": [2.0, 4.0, 0.0]})


def test_a_division_by_zero_is_counted(tmp_path):
    repo = _repo(tmp_path, FRAME)
    result = execute(repo, "job", {"execution_spec": _spec(), "thread_id": "t"})
    assert result["undefined_derived_values"] == {"ratio": 1}


def test_the_count_is_written_to_the_manifest(tmp_path):
    repo = _repo(tmp_path, FRAME)
    execute(repo, "job", {"execution_spec": _spec(), "thread_id": "t"})
    manifest = json.loads((repo / "data_lake/synthesis/thread_outputs/t/job/manifest.json").read_text())
    assert manifest["undefined_derived_values"] == {"ratio": 1}


def test_clean_arithmetic_reports_nothing(tmp_path):
    repo = _repo(tmp_path, pd.DataFrame({"g": ["a", "b"], "num": [10.0, 30.0], "den": [2.0, 3.0]}))
    result = execute(repo, "job", {"execution_spec": _spec(), "thread_id": "t"})
    assert result["undefined_derived_values"] == {}


def test_an_expression_that_blows_up_is_counted_too(tmp_path):
    repo = _repo(tmp_path, FRAME)
    spec = _spec(transforms=[{"op": "derive", "as": "ratio", "expr": "num / den"}])
    result = execute(repo, "job", {"execution_spec": spec, "thread_id": "t"})
    assert result["undefined_derived_values"] == {"ratio": 1}


def test_the_masked_value_does_not_become_a_finite_number(tmp_path):
    """The group whose only value was undefined must not report a real mean."""
    repo = _repo(tmp_path, FRAME)
    spec = _spec(metrics=[{"function": "mean", "column": "ratio", "as": "m"},
                          {"function": "sum", "column": "ratio", "as": "r"}])
    execute(repo, "job", {"execution_spec": spec, "thread_id": "t"})
    out = pd.read_parquet(repo / "data_lake/synthesis/thread_outputs/t/job/output.parquet")
    row_b = out[out["g"] == "b"].iloc[0]
    assert pd.isna(row_b["m"])
    assert row_b["r"] == 0.0


def test_each_derived_column_is_counted_separately(tmp_path):
    repo = _repo(tmp_path, FRAME)
    spec = _spec(
        metrics=[{"function": "sum", "column": "ratio", "as": "r"},
                 {"function": "sum", "column": "flipped", "as": "f"}],
        transforms=[{"op": "derive", "as": "ratio", "fn": "div", "column": "num", "by_column": "den"},
                    {"op": "derive", "as": "flipped", "fn": "div", "column": "den", "by_column": "num"}],
    )
    result = execute(repo, "job", {"execution_spec": spec, "thread_id": "t"})
    assert result["undefined_derived_values"] == {"ratio": 1}
