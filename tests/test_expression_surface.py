"""Every expression operator must execute end to end, and adding one must land here.

The parity suite parametrises over metrics, filter operators, derive functions,
as-of directions, collapse strategies and reshaping ops. It does not touch the 23
expression operators, so `log(v)` over a column spanning zero went unexercised and
its undefined values went uncounted until someone ran it by hand.

Parametrising over `expr_runtime.functions()` means widening that runtime creates a
case here that has to pass, rather than a capability nothing ever calls.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from scripts.research_data_mcp.synthesis.expr_runtime import functions
from scripts.research_data_mcp.synthesis_executor import execute

# one usage per operator, chosen so the expression is defined on FRAME
USAGE = {
    "date_trunc": "date_trunc(d, 'month')", "year": "year(d)", "month": "month(d)",
    "quarter": "quarter(d)", "day_of_week": "day_of_week(d)",
    "lower": "lower(s)", "upper": "upper(s)", "strip": "strip(s)",
    "substr": "substr(s, 0, 3)", "replace": "replace(s, 'Sym', 'X')",
    "contains": "contains(s, 'Sym')", "concat": "concat(s, g)", "length": "length(s)",
    "abs": "abs(v)", "round": "round(v, 1)", "clip": "clip(v, 0, 20)",
    "log": "log(v)", "sqrt": "sqrt(v)", "if_else": "if_else(v > 10, v, 0)",
    "coalesce": "coalesce(v, w)", "is_null": "is_null(v)",
    "rank_pct": "rank_pct(v)", "ntile": "ntile(v, 4)",
}

FRAME = pd.DataFrame({
    "g": list("abcd") * 5,
    "d": pd.to_datetime(["2024-01-02", "2024-02-11", "2024-03-21", "2024-04-30"] * 5),
    "v": [float(i) + 1.0 for i in range(20)],
    "w": [2.0] * 20,
    "s": [f"Sym_{i % 3} " for i in range(20)],
})


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    FRAME.to_parquet(tmp_path / "data/a.parquet")
    right = pd.DataFrame({"g": sorted(list("abcd")), "r": [10.0, 20.0, 30.0, 40.0]})
    right.to_parquet(tmp_path / "data/b.parquet")
    (tmp_path / "config/research_query_registry.json").write_text(
        json.dumps({"datasets": [
            {"dataset_id": "a", "name": "a", "local_path": "data/a.parquet", "grain": "row"},
            {"dataset_id": "b", "name": "b", "local_path": "data/b.parquet", "grain": "row"}]}),
        encoding="utf-8")
    return tmp_path


def _spec(transforms, metrics=None):
    return {"input_dataset_id": "a", "output_dataset_id": "synthesis_expression_probe",
            "group_by": ["g"], "transforms": transforms,
            "metrics": metrics or [{"function": "nunique", "column": "x", "as": "nx"}]}


def test_the_usage_table_covers_the_whole_runtime():
    """A new operator with no usage here would otherwise be silently untested."""
    assert set(USAGE) == set(functions())


@pytest.mark.parametrize("name", sorted(USAGE))
def test_every_expression_operator_executes(repo, name):
    result = execute(repo, "job", {"execution_spec": _spec(
        [{"op": "derive", "as": "x", "expr": USAGE[name]}]), "thread_id": "expr"})
    assert result["rows"] == 4


def test_two_joins_in_one_spec_both_record_their_accounting(repo):
    """Multi-way was never exercised: an equi-join and an as-of join together."""
    spec = _spec(
        transforms=[
            {"op": "join", "right_dataset_id": "b", "on": ["g"], "how": "inner",
             "accept_row_loss": True, "collapse": {"strategy": "first"}},
            {"op": "join_asof", "right_dataset_id": "b", "left_on": "v", "right_on": "r",
             "direction": "backward"},
        ],
        metrics=[{"function": "count", "as": "n"}])
    result = execute(repo, "job", {"execution_spec": spec, "thread_id": "expr"})
    ops = [step["op"] for step in result["row_ledger"]]
    assert ops == ["join", "join_asof"]
    assert len(result["asof_coverage"]) == 1
    assert result["source_rows"] == len(FRAME)
