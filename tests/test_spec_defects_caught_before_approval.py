"""Preflight exists so a researcher never approves a spec that cannot run.

Three specs passed preflight clean and then died inside pandas in the approved
job: two metrics sharing an output name ("columns overlap but no suffix
specified"), a metric named after a group key ("cannot insert g, already
exists"), and a mean of a text column (a bare TypeError). All three are spec
errors and all three are now refused up front.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from scripts.research_data_mcp.synthesis_executor import (
    preflight_execution_spec,
    validate_execution_spec,
)

FRAME = pd.DataFrame({"g": ["a", "b", "b"], "v": [1.0, 2.0, 4.0]})


def _repo(tmp_path: Path) -> Path:
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    FRAME.to_parquet(tmp_path / "data/a.parquet")
    (tmp_path / "config/research_query_registry.json").write_text(
        json.dumps({"datasets": [{"dataset_id": "a", "name": "a",
                                  "local_path": "data/a.parquet", "grain": "row"}]}),
        encoding="utf-8")
    return tmp_path


def _spec(metrics, **over):
    spec = {"input_dataset_id": "a", "output_dataset_id": "synthesis_defect_probe",
            "group_by": ["g"], "metrics": metrics}
    spec.update(over)
    return spec


def test_two_metrics_cannot_share_an_output_name():
    with pytest.raises(ValueError, match="share the output name"):
        validate_execution_spec(_spec([{"function": "sum", "column": "v", "as": "x"},
                                       {"function": "mean", "column": "v", "as": "x"}]))


def test_a_metric_cannot_be_named_after_a_group_key():
    with pytest.raises(ValueError, match="already a group_by column"):
        validate_execution_spec(_spec([{"function": "sum", "column": "v", "as": "g"}]))


def test_a_metric_may_be_named_after_a_source_column_it_replaces():
    """Shadowing an input column is legitimate; only the group key collides."""
    out = validate_execution_spec(_spec([{"function": "sum", "column": "v", "as": "v"}]))
    assert out["metrics"][0]["as"] == "v"


def test_a_mean_of_a_text_column_is_refused_before_approval(tmp_path):
    report = preflight_execution_spec(_repo(tmp_path),
                                      _spec([{"function": "mean", "column": "g", "as": "m"}]))
    assert report["ok"] is False
    issue = next(i for i in report["issues"] if i["code"] == "metric_needs_numbers")
    assert issue["column"] == "g"
    assert issue["function"] == "mean"


@pytest.mark.parametrize("function", ["sum", "mean", "std", "median"])
def test_every_numeric_only_function_is_checked(tmp_path, function):
    report = preflight_execution_spec(_repo(tmp_path),
                                      _spec([{"function": function, "column": "g", "as": "x"}]))
    assert any(i["code"] == "metric_needs_numbers" for i in report["issues"]), function


def test_quantile_of_text_is_refused(tmp_path):
    report = preflight_execution_spec(
        _repo(tmp_path), _spec([{"function": "quantile", "column": "g", "q": 0.5, "as": "p"}]))
    assert any(i["code"] == "metric_needs_numbers" for i in report["issues"])


@pytest.mark.parametrize("function", ["min", "max", "nunique"])
def test_functions_that_work_on_text_are_left_alone(tmp_path, function):
    """Ordering strings and counting distinct values are both legitimate."""
    report = preflight_execution_spec(_repo(tmp_path),
                                      _spec([{"function": function, "column": "g", "as": "x"}]))
    assert report["ok"] is True, report["issues"]


def test_a_derived_column_is_not_prejudged(tmp_path):
    """A derive output has no dtype yet, so the check must not guess at one."""
    report = preflight_execution_spec(
        _repo(tmp_path),
        _spec([{"function": "mean", "column": "ratio", "as": "m"}],
              transforms=[{"op": "derive", "as": "ratio", "fn": "div", "column": "v", "value": 2.0}]))
    assert report["ok"] is True, report["issues"]


def test_a_sound_spec_still_passes(tmp_path):
    report = preflight_execution_spec(
        _repo(tmp_path), _spec([{"function": "count", "as": "n"},
                                {"function": "std", "column": "v", "as": "sd"}]))
    assert report["ok"] is True
    assert report["issues"] == []
