"""A declared collapse rule must change the result, or the gate is theatre."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from scripts.research_data_mcp.synthesis_executor import execute


def _repo(tmp_path: Path) -> Path:
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"k": ["a", "b"], "x": [1.0, 2.0]}).to_parquet(tmp_path / "data/spine.parquet")
    pd.DataFrame({"k": ["a", "a", "b"], "y": [10.0, 99.0, 20.0]}).to_parquet(tmp_path / "data/many.parquet")
    (tmp_path / "config/research_query_registry.json").write_text(json.dumps({"datasets": [
        {"dataset_id": "spine", "name": "spine", "local_path": "data/spine.parquet", "grain": "g", "join_keys": ["k"]},
        {"dataset_id": "many", "name": "many", "local_path": "data/many.parquet", "grain": "g", "join_keys": ["k"]},
    ]}), encoding="utf-8")
    return tmp_path


def _spec(strategy):
    join = {"op": "join", "right_dataset_id": "many", "on": ["k"], "how": "inner"}
    if strategy:
        join["collapse"] = {"strategy": strategy}
    return {
        "input_dataset_id": "spine",
        "output_dataset_id": "synthesis_collapse_applied_v1",
        "group_by": [],
        "metrics": [{"function": "mean", "column": "y", "as": "mean_y"},
                    {"function": "count", "as": "n"}],
        "transforms": [join],
    }


def _run(tmp_path, strategy, jid):
    repo = _repo(tmp_path)
    execute(repo, jid, {"execution_spec": _spec(strategy), "thread_id": "t"})
    return pd.read_parquet(repo / f"data_lake/synthesis/thread_outputs/t/{jid}/output.parquet")


def test_first_keeps_the_first_row_per_key(tmp_path):
    out = _run(tmp_path, "first", "j1")
    assert float(out["mean_y"].iloc[0]) == pytest.approx(15.0)
    assert int(out["n"].iloc[0]) == 2


def test_last_keeps_the_last_row_per_key(tmp_path):
    out = _run(tmp_path, "last", "j2")
    assert float(out["mean_y"].iloc[0]) == pytest.approx(59.5)
    assert int(out["n"].iloc[0]) == 2


def test_first_and_last_must_differ(tmp_path):
    """If these ever match, collapse is being ignored again."""
    a = float(_run(tmp_path, "first", "j3")["mean_y"].iloc[0])
    b = float(_run(tmp_path, "last", "j4")["mean_y"].iloc[0])
    assert a != b


def test_error_strategy_refuses_a_one_to_many_side(tmp_path):
    with pytest.raises(ValueError, match="not 1:1"):
        _run(tmp_path, "error", "j5")


def test_without_a_rule_the_fan_out_is_visible(tmp_path):
    """No declared rule -> all 3 rows survive; preflight is what blocks this."""
    out = _run(tmp_path, None, "j6")
    assert int(out["n"].iloc[0]) == 3
