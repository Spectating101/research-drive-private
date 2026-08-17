"""The exported script must reproduce what the engine computed, or it is a lie."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from scripts.research_data_mcp.synthesis.spec_export import fingerprint_path, render_script
from scripts.research_data_mcp.synthesis_executor import execute, preflight_execution_spec

BASE = pd.DataFrame({"k": ["a", "a", "b", "c"], "v": [1.0, 3.0, 5.0, 7.0], "w": [10.0, 20.0, 30.0, 40.0]})
ATTR = pd.DataFrame({"k": ["a", "b", "c"], "y": [100.0, 200.0, 300.0]})


def _repo(tmp_path: Path, frames: dict[str, pd.DataFrame]) -> Path:
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    ds = []
    for name, frame in frames.items():
        frame.to_parquet(tmp_path / f"data/{name}.parquet")
        ds.append({"dataset_id": name, "name": name, "local_path": f"data/{name}.parquet",
                   "grain": "g", "join_keys": ["k"]})
    (tmp_path / "config/research_query_registry.json").write_text(
        json.dumps({"datasets": ds}), encoding="utf-8")
    return tmp_path


def _both(tmp_path, frames, spec):
    """Return (engine_df, script_df) for the same spec."""
    repo = _repo(tmp_path, frames)
    pf = preflight_execution_spec(repo, spec)
    assert pf["ok"], [i["code"] for i in pf["issues"]]
    execute(repo, "j", {"execution_spec": spec, "thread_id": "t"})
    engine = pd.read_parquet(repo / "data_lake/synthesis/thread_outputs/t/j/output.parquet")
    inputs = {n: fingerprint_path(repo / f"data/{n}.parquet") for n in frames}
    script = render_script(spec, inputs, probes=pf.get("join_probes"))
    path = repo / "method.py"
    path.write_text(script + f"\nresult.to_parquet(r'{repo}/out.parquet', index=False)\n", encoding="utf-8")
    run = subprocess.run([sys.executable, str(path)], capture_output=True, text=True, timeout=180)
    assert run.returncode == 0, run.stderr[-500:]
    return engine, pd.read_parquet(repo / "out.parquet")


def _same(a, b):
    assert a.shape == b.shape, f"{a.shape} vs {b.shape}"
    assert list(a.columns) == list(b.columns)
    left = a.sort_values(list(a.columns)).reset_index(drop=True)
    right = b.sort_values(list(b.columns)).reset_index(drop=True)
    pd.testing.assert_frame_equal(left, right, check_dtype=False, rtol=1e-9)


def test_grouped_aggregate_matches(tmp_path):
    spec = {"input_dataset_id": "a", "output_dataset_id": "synthesis_fid_a_v1",
            "group_by": ["k"], "metrics": [{"function": "mean", "column": "v", "as": "mv"}]}
    _same(*_both(tmp_path, {"a": BASE}, spec))


def test_ungrouped_aggregate_matches(tmp_path):
    """Regression: the renderer used to emit the raw frame for ungrouped specs."""
    spec = {"input_dataset_id": "a", "output_dataset_id": "synthesis_fid_b_v1",
            "group_by": [], "metrics": [{"function": "mean", "column": "v", "as": "mv"}]}
    engine, script = _both(tmp_path, {"a": BASE}, spec)
    assert engine.shape == (1, 1)
    _same(engine, script)


def test_ungrouped_count_matches(tmp_path):
    spec = {"input_dataset_id": "a", "output_dataset_id": "synthesis_fid_c_v1",
            "group_by": [], "metrics": [{"function": "count", "as": "n"}]}
    engine, script = _both(tmp_path, {"a": BASE}, spec)
    assert int(engine.iloc[0, 0]) == len(BASE)
    _same(engine, script)


def test_multi_metric_matches(tmp_path):
    spec = {"input_dataset_id": "a", "output_dataset_id": "synthesis_fid_d_v1",
            "group_by": ["k"], "metrics": [{"function": "mean", "column": "v", "as": "mv"},
                                            {"function": "max", "column": "w", "as": "mw"},
                                            {"function": "count", "as": "n"}]}
    _same(*_both(tmp_path, {"a": BASE}, spec))


def test_join_matches(tmp_path):
    spec = {"input_dataset_id": "a", "output_dataset_id": "synthesis_fid_e_v1",
            "group_by": ["k"], "metrics": [{"function": "mean", "column": "y", "as": "my"}],
            "transforms": [{"op": "join", "right_dataset_id": "b", "on": ["k"], "how": "inner"}]}
    _same(*_both(tmp_path, {"a": BASE, "b": ATTR}, spec))


def test_filter_matches(tmp_path):
    spec = {"input_dataset_id": "a", "output_dataset_id": "synthesis_fid_f_v1",
            "group_by": ["k"], "metrics": [{"function": "mean", "column": "v", "as": "mv"}],
            "transforms": [{"op": "filter", "column": "v", "cmp": "gt", "value": 2}]}
    _same(*_both(tmp_path, {"a": BASE}, spec))


DERIVE_BASE = pd.DataFrame({
    "k": ["a", "a", "b", "b"],
    "metric": ["vol", "si", "vol", "si"],
    "value": [10.0, 1.0, 20.0, 2.0],
    "x": [4.0, 6.0, 8.0, 10.0],
    "y": [2.0, 3.0, 4.0, 5.0],
})


def _derive_spec(transforms, metrics, name):
    return {"input_dataset_id": "a", "output_dataset_id": f"synthesis_der_{name}_v1",
            "group_by": ["k"], "metrics": metrics, "transforms": transforms}


def test_expr_derive_pivot_matches(tmp_path):
    """if_else over a metric column is how a long table becomes wide."""
    spec = _derive_spec(
        [{"op": "derive", "as": "vol", "expr": "if_else(metric == 'vol', value, None)"}],
        [{"function": "mean", "column": "vol", "as": "mvol"}], "pivot")
    _same(*_both(tmp_path, {"a": DERIVE_BASE}, spec))


def test_arithmetic_derive_by_column_matches(tmp_path):
    spec = _derive_spec(
        [{"op": "derive", "as": "d", "fn": "sub", "column": "x", "by_column": "y"}],
        [{"function": "mean", "column": "d", "as": "md"}], "sub")
    _same(*_both(tmp_path, {"a": DERIVE_BASE}, spec))


def test_arithmetic_derive_by_value_matches(tmp_path):
    spec = _derive_spec(
        [{"op": "derive", "as": "d", "fn": "mul", "column": "x", "value": 3}],
        [{"function": "mean", "column": "d", "as": "md"}], "mul")
    _same(*_both(tmp_path, {"a": DERIVE_BASE}, spec))


def test_div_derive_matches_including_infinity_handling(tmp_path):
    frame = pd.DataFrame({"k": ["a", "b"], "x": [1.0, 2.0], "y": [0.0, 2.0]})
    spec = _derive_spec(
        [{"op": "derive", "as": "d", "fn": "div", "column": "x", "by_column": "y"}],
        [{"function": "mean", "column": "d", "as": "md"}], "div")
    engine, script = _both(tmp_path, {"a": frame}, spec)
    _same(engine, script)


def test_abs_derive_matches(tmp_path):
    frame = pd.DataFrame({"k": ["a", "b"], "x": [-1.0, 2.0]})
    spec = _derive_spec(
        [{"op": "derive", "as": "d", "fn": "abs", "column": "x"}],
        [{"function": "mean", "column": "d", "as": "md"}], "abs")
    _same(*_both(tmp_path, {"a": frame}, spec))


def test_indicator_derive_matches(tmp_path):
    spec = _derive_spec(
        [{"op": "derive", "as": "d", "fn": "indicator", "column": "metric", "cmp": "eq", "value": "vol"}],
        [{"function": "sum", "column": "d", "as": "n_vol"}], "ind")
    _same(*_both(tmp_path, {"a": DERIVE_BASE}, spec))


def test_derive_script_is_code_not_a_comment(tmp_path):
    """Regression: the renderer used to emit a comment, leaving the column undefined."""
    spec = _derive_spec(
        [{"op": "derive", "as": "d", "fn": "abs", "column": "x"}],
        [{"function": "mean", "column": "d", "as": "md"}], "code")
    script = render_script(spec, {"a": {"path": "x.parquet", "fingerprint": None, "note": "n/a"}})
    assert 'frame["d"]' in script
    assert "# derive" not in script
