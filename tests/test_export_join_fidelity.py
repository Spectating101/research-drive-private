"""A join the desk ran must produce a script the researcher can run.

Two divergences made the exported script crash on joins the engine completed:
pandas' default merge suffixes are _x/_y while the engine keeps the input's
name and suffixes the other _right, so a metric on the shared name raised
KeyError; and the engine aligns key dtypes to string when they disagree, which
the script did not, so a date-against-text key raised ValueError.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from scripts.research_data_mcp.synthesis_executor import execute
from scripts.research_data_mcp.synthesis.spec_export import fingerprint_path, render_script


def _repo(tmp_path: Path, left: pd.DataFrame, right: pd.DataFrame) -> Path:
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    left.to_parquet(tmp_path / "data/a.parquet")
    right.to_parquet(tmp_path / "data/b.parquet")
    (tmp_path / "config/research_query_registry.json").write_text(
        json.dumps({"datasets": [
            {"dataset_id": "a", "name": "a", "local_path": "data/a.parquet", "grain": "row"},
            {"dataset_id": "b", "name": "b", "local_path": "data/b.parquet", "grain": "row"}]}),
        encoding="utf-8")
    return tmp_path


def _both(tmp_path: Path, left: pd.DataFrame, right: pd.DataFrame, spec: dict):
    repo = _repo(tmp_path, left, right)
    execute(repo, "job", {"execution_spec": spec, "thread_id": "t"})
    engine = pd.read_parquet(repo / "data_lake/synthesis/thread_outputs/t/job/output.parquet")

    out = tmp_path / "exported.parquet"
    script = tmp_path / "exported.py"
    script.write_text(
        render_script(spec, {"a": fingerprint_path(repo / "data/a.parquet"),
                             "b": fingerprint_path(repo / "data/b.parquet")})
        + f"\nresult.to_parquet({str(out)!r})\n", encoding="utf-8")
    done = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, timeout=300)
    assert done.returncode == 0, done.stderr[-400:]
    return engine, pd.read_parquet(out)


def _spec(**over):
    spec = {"input_dataset_id": "a", "output_dataset_id": "synthesis_export_join_probe",
            "group_by": ["k"], "metrics": [{"function": "sum", "column": "v", "as": "s"}],
            "transforms": [{"op": "join", "right_dataset_id": "b", "on": ["k"], "how": "inner"}]}
    spec.update(over)
    return spec


def test_a_column_name_on_both_sides_does_not_break_the_script(tmp_path):
    engine, exported = _both(
        tmp_path,
        pd.DataFrame({"k": ["x", "y"], "v": [1.0, 2.0]}),
        pd.DataFrame({"k": ["x", "y"], "v": [10.0, 20.0]}),
        _spec())
    pd.testing.assert_frame_equal(engine, exported, check_dtype=False)
    assert engine["s"].tolist() == [1.0, 2.0]


def test_disagreeing_key_dtypes_are_aligned_in_the_script_too(tmp_path):
    engine, exported = _both(
        tmp_path,
        pd.DataFrame({"k": pd.to_datetime(["2024-01-01", "2024-01-02"]), "v": [1.0, 2.0]}),
        pd.DataFrame({"k": ["2024-01-01", "2024-01-02"], "w": [10.0, 20.0]}),
        _spec(metrics=[{"function": "sum", "column": "w", "as": "s"}]))
    pd.testing.assert_frame_equal(engine, exported, check_dtype=False)


@pytest.mark.parametrize("strategy,total", [("first", 10.0), ("last", 99.0)])
def test_the_collapse_rule_is_applied_by_the_script(tmp_path, strategy, total):
    engine, exported = _both(
        tmp_path,
        pd.DataFrame({"k": ["x"], "v": [1.0]}),
        pd.DataFrame({"k": ["x", "x"], "w": [10.0, 99.0]}),
        _spec(metrics=[{"function": "sum", "column": "w", "as": "s"}],
              transforms=[{"op": "join", "right_dataset_id": "b", "on": ["k"], "how": "inner",
                           "collapse": {"strategy": strategy}}]))
    pd.testing.assert_frame_equal(engine, exported, check_dtype=False)
    assert engine["s"].iloc[0] == total


def test_a_left_join_keeps_the_same_rows_in_both(tmp_path):
    engine, exported = _both(
        tmp_path,
        pd.DataFrame({"k": ["x", "y", "z"], "v": [1.0, 2.0, 3.0]}),
        pd.DataFrame({"k": ["x", "y"], "w": [10.0, 20.0]}),
        _spec(metrics=[{"function": "count", "as": "n"},
                       {"function": "sum", "column": "w", "as": "s"}],
              transforms=[{"op": "join", "right_dataset_id": "b", "on": ["k"], "how": "left",
                           "accept_row_loss": True}]))
    pd.testing.assert_frame_equal(engine, exported, check_dtype=False)
    assert len(engine) == 3
