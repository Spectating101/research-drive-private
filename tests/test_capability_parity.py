"""Everything the engine declares it can do, the exported script must also do.

Every defect found by hunting this contract was the same shape: two things that
should agree, drifting, with nothing binding them. The engine's expression
runtime against the script's. The manifest against the reader. The instructions
against the capability.

These tests are parametrised over the engine's own frozensets, so widening a
capability creates a case here that has to pass. Adding a metric function or a
filter operator without teaching the exporter fails this file rather than
shipping a script a researcher cannot run.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from scripts.research_data_mcp.mcp_instructions import mcp_server_instructions
from scripts.research_data_mcp.synthesis.spec_export import fingerprint_path, render_script
from scripts.research_data_mcp.synthesis_executor import (
    ALLOWED_ASOF_DIRECTIONS,
    ALLOWED_COLLAPSE_STRATEGIES,
    ALLOWED_DERIVE_FNS,
    ALLOWED_FILTER_OPS,
    ALLOWED_METRIC_FNS,
    execute,
)

LEFT = pd.DataFrame({
    "g": ["a", "a", "b", "b"],
    "v": [1.0, 2.0, 3.0, 4.0],
    "w": [2.0, 2.0, 2.0, 1.0],
    "d": pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]),
})
RIGHT = pd.DataFrame({
    "g": ["a", "b", "b"],
    "r": [10.0, 20.0, 30.0],
    "d": pd.to_datetime(["2024-01-01", "2024-01-01", "2024-01-03"]),
})

FILTER_VALUES = {"eq": 2.0, "ne": 2.0, "gt": 1.0, "gte": 2.0, "lt": 4.0, "lte": 3.0,
                 "in": [1.0, 2.0], "not_in": [4.0], "contains": "2"}


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    LEFT.to_parquet(tmp_path / "data/a.parquet")
    RIGHT.to_parquet(tmp_path / "data/b.parquet")
    (tmp_path / "config/research_query_registry.json").write_text(
        json.dumps({"datasets": [
            {"dataset_id": "a", "name": "a", "local_path": "data/a.parquet", "grain": "row"},
            {"dataset_id": "b", "name": "b", "local_path": "data/b.parquet", "grain": "row"}]}),
        encoding="utf-8")
    return tmp_path


def _spec(**over):
    spec = {"input_dataset_id": "a", "output_dataset_id": "synthesis_capability_parity",
            "group_by": ["g"],
            "metrics": [{"function": "count", "as": "n"}, {"function": "sum", "column": "v", "as": "sv"}]}
    spec.update(over)
    return spec


def _both(repo: Path, spec: dict, tmp_path: Path):
    """Run the spec on the desk and through its own exported script."""
    execute(repo, "job", {"execution_spec": spec, "thread_id": "parity"})
    engine = pd.read_parquet(repo / "data_lake/synthesis/thread_outputs/parity/job/output.parquet")
    out = tmp_path / "exported.parquet"
    script = tmp_path / "exported.py"
    script.write_text(
        render_script(spec, {"a": fingerprint_path(repo / "data/a.parquet"),
                             "b": fingerprint_path(repo / "data/b.parquet")})
        + f"\nresult.to_parquet({str(out)!r})\n", encoding="utf-8")
    done = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, timeout=300)
    assert done.returncode == 0, done.stderr[-400:]
    return engine, pd.read_parquet(out)


@pytest.mark.parametrize("function", sorted(ALLOWED_METRIC_FNS))
def test_every_metric_function_exports(repo, tmp_path, function):
    metric = {"function": function, "as": "m"}
    if function != "count":
        metric["column"] = "v"
    if function == "quantile":
        metric["q"] = 0.5
    engine, exported = _both(repo, _spec(metrics=[metric]), tmp_path)
    pd.testing.assert_frame_equal(engine, exported, check_dtype=False)


@pytest.mark.parametrize("op", sorted(ALLOWED_FILTER_OPS))
def test_every_filter_operator_exports(repo, tmp_path, op):
    spec = _spec(transforms=[{"op": "filter", "column": "v", "cmp": op, "value": FILTER_VALUES[op]}])
    engine, exported = _both(repo, spec, tmp_path)
    pd.testing.assert_frame_equal(engine, exported, check_dtype=False)


@pytest.mark.parametrize("fn", sorted(ALLOWED_DERIVE_FNS))
def test_every_derive_function_exports(repo, tmp_path, fn):
    step = {"op": "derive", "as": "x", "fn": fn, "column": "v"}
    if fn == "indicator":
        step |= {"cmp": "gt", "value": 1.0}
    elif fn != "abs":
        step |= {"by_column": "w"}
    spec = _spec(metrics=[{"function": "sum", "column": "x", "as": "sx"}], transforms=[step])
    engine, exported = _both(repo, spec, tmp_path)
    pd.testing.assert_frame_equal(engine, exported, check_dtype=False)


@pytest.mark.parametrize("direction", sorted(ALLOWED_ASOF_DIRECTIONS))
def test_every_asof_direction_exports(repo, tmp_path, direction):
    spec = _spec(metrics=[{"function": "sum", "column": "r", "as": "sr"}],
                 transforms=[{"op": "join_asof", "right_dataset_id": "b", "on": "d",
                              "direction": direction}])
    engine, exported = _both(repo, spec, tmp_path)
    pd.testing.assert_frame_equal(engine, exported, check_dtype=False)


@pytest.mark.parametrize("strategy", sorted(ALLOWED_COLLAPSE_STRATEGIES))
def test_every_collapse_strategy_agrees(repo, tmp_path, strategy):
    """`error` is meant to refuse a 1:N right side; first and last must round-trip."""
    spec = _spec(metrics=[{"function": "sum", "column": "r", "as": "sr"}],
                 transforms=[{"op": "join", "right_dataset_id": "b", "on": ["g"], "how": "inner",
                              "accept_row_loss": True, "collapse": {"strategy": strategy}}])
    if strategy == "error":
        with pytest.raises(ValueError, match="not 1:1"):
            execute(repo, "job", {"execution_spec": spec, "thread_id": "parity"})
        return
    engine, exported = _both(repo, spec, tmp_path)
    pd.testing.assert_frame_equal(engine, exported, check_dtype=False)


@pytest.mark.parametrize("op", ["select", "rename", "sort", "head", "drop_na", "drop_duplicates"])
def test_every_reshaping_transform_exports(repo, tmp_path, op):
    steps = {
        "select": {"op": "select", "columns": ["g", "v"]},
        "rename": {"op": "rename", "mapping": {"v": "vv"}},
        "sort": {"op": "sort", "by": ["v"]},
        "head": {"op": "head", "n": 3},
        "drop_na": {"op": "drop_na", "columns": ["v"]},
        "drop_duplicates": {"op": "drop_duplicates", "columns": ["g"]},
    }
    metrics = [{"function": "count", "as": "n"}] if op == "rename" else None
    spec = _spec(transforms=[steps[op]], **({"metrics": metrics} if metrics else {}))
    engine, exported = _both(repo, spec, tmp_path)
    pd.testing.assert_frame_equal(engine, exported, check_dtype=False)


@pytest.mark.parametrize("function", sorted(ALLOWED_METRIC_FNS))
def test_the_desk_instructions_name_every_metric(monkeypatch, function):
    """A capability nothing can discover is the same defect as one nothing reads."""
    monkeypatch.setenv("RESEARCH_MCP_DESK", "1")
    assert function in mcp_server_instructions()


def test_the_script_row_accounting_matches_the_engine_ledger(repo, tmp_path):
    """Luna's review caught this gap: the script prints its coverage and the
    engine records a ledger, and nothing compared the two. A spec exercising a
    join, a derive and two row-reducing steps must agree on every step.
    """
    import re

    spec = _spec(
        metrics=[{"function": "count", "as": "n"},
                 {"function": "mean", "column": "x", "as": "mx"}],
        transforms=[
            {"op": "join", "right_dataset_id": "b", "on": ["g"], "how": "inner",
             "accept_row_loss": True, "collapse": {"strategy": "first"}},
            {"op": "derive", "as": "x", "expr": "if_else(v > 1, v * r, 0)"},
            {"op": "filter", "column": "v", "cmp": "gt", "value": 1.0},
            {"op": "drop_na", "columns": ["x"]},
        ])
    engine_result = execute(repo, "job", {"execution_spec": spec, "thread_id": "parity"})

    out = tmp_path / "exported.parquet"
    script = tmp_path / "exported.py"
    script.write_text(
        render_script(spec, {"a": fingerprint_path(repo / "data/a.parquet"),
                             "b": fingerprint_path(repo / "data/b.parquet")})
        + f"\nresult.to_parquet({str(out)!r})\n", encoding="utf-8")
    done = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, timeout=300)
    assert done.returncode == 0, done.stderr[-400:]

    printed = done.stdout
    source, aggregated = re.search(r"source rows: (\d+)  aggregated over: (\d+)", printed).groups()
    assert int(source) == engine_result["source_rows"]
    assert int(aggregated) == engine_result["rows_aggregated"]

    # every step the script reported losing rows on must match the engine's ledger
    reported = {(op, int(a), int(b)) for op, a, b in
                re.findall(r"step \d+ (\w+): (\d+) -> (\d+) rows", printed)}
    expected = {(s["op"], s["rows_in"], s["rows_out"]) for s in engine_result["row_ledger"]
                if s["rows_in"] != s["rows_out"]}
    assert reported == expected, f"script {reported} vs engine {expected}"

    # and the numbers must be non-trivial, or this proves nothing
    assert engine_result["source_rows"] > engine_result["rows_aggregated"] > 0
