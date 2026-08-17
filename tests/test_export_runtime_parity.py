"""The exported script's expression runtime must match the engine's, function
for function and result for result.

The engine offered 23 expression functions and the exported runtime implemented
6, so any derive using abs, sqrt, log, year, length, round, clip, coalesce,
is_null, rank_pct, contains, month, quarter, day_of_week, lower, upper, strip,
replace or a nested date_trunc produced a script that died with a NameError.
Worse, the six it did implement had drifted: ntile bucketed a rank in the script
and the raw series on the desk.

Two hand-maintained lists drift. This test is what keeps them together: it fails
the moment the engine gains a function the script cannot run, or either side
changes what one means.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from scripts.research_data_mcp.synthesis_executor import execute, expression_functions
from scripts.research_data_mcp.synthesis.spec_export import fingerprint_path, render_script

FRAME = pd.DataFrame({
    "g": ["a", "a", "b", "b"],
    "v": [1.0, 4.0, 9.0, 16.0],
    "s": ["Foo ", "bar", "BAZ", " qux"],
    "d": pd.to_datetime(["2024-01-15", "2024-02-20", "2024-03-25", "2024-04-30"]),
})

# One expression per engine function, each reducing to a number so sum() compares.
EXPRESSIONS = {
    "abs": "abs(v - 5)", "sqrt": "sqrt(v)", "log": "log(v)", "round": "round(v)",
    "clip": "clip(v, 2, 10)", "coalesce": "coalesce(v, 0)", "is_null": "is_null(v) * 1",
    "ntile": "ntile(v, 2)", "rank_pct": "rank_pct(v)", "if_else": "if_else(v > 4, v, 0)",
    "length": "length(s)", "contains": "contains(s, 'a') * 1",
    "year": "year(d)", "month": "month(d)", "quarter": "quarter(d)",
    "day_of_week": "day_of_week(d)", "date_trunc": "length(date_trunc(d, 'month'))",
    "concat": "length(concat(s, s))", "lower": "length(lower(s))", "upper": "length(upper(s))",
    "strip": "length(strip(s))", "substr": "length(substr(s, 0, 2))",
    "replace": "length(replace(s, 'a', 'b'))",
}


def _exported_runtime_names() -> set[str]:
    """Names the rendered script's own runtime provides."""
    script = render_script(
        {"input_dataset_id": "a", "output_dataset_id": "synthesis_parity_probe",
         "group_by": ["g"], "metrics": [{"function": "sum", "column": "x", "as": "sx"}],
         "transforms": [{"op": "derive", "as": "x", "expr": "abs(v)"}]},
        {"a": {"path": "data/a.parquet", "fingerprint": None}})
    namespace: dict = {}
    body = script[script.index("def _expr_functions():"):script.index("def _derive_expr(")]
    exec("import numpy as np\nimport pandas as pd\n" + body, namespace)  # noqa: S102
    return set(namespace["_expr_functions"]())


def test_every_engine_function_exists_in_the_exported_runtime():
    missing = sorted(set(expression_functions()) - _exported_runtime_names())
    assert not missing, f"the exported script cannot run: {missing}"


def test_the_exported_runtime_adds_nothing_the_engine_lacks():
    extra = sorted(_exported_runtime_names() - set(expression_functions()))
    assert not extra, f"the script offers what the desk will not accept: {extra}"


def test_every_engine_function_has_a_case_here():
    """A new function must arrive with a comparison, or this suite lies by omission."""
    uncovered = sorted(set(expression_functions()) - set(EXPRESSIONS))
    assert not uncovered, f"no engine/script comparison for: {uncovered}"


def _repo(tmp_path: Path) -> Path:
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    FRAME.to_parquet(tmp_path / "data/a.parquet")
    (tmp_path / "config/research_query_registry.json").write_text(
        json.dumps({"datasets": [{"dataset_id": "a", "name": "a",
                                  "local_path": "data/a.parquet", "grain": "row"}]}),
        encoding="utf-8")
    return tmp_path


@pytest.mark.parametrize("name", sorted(EXPRESSIONS))
def test_the_script_reproduces_the_engine_for(tmp_path, name):
    repo = _repo(tmp_path)
    spec = {"input_dataset_id": "a", "output_dataset_id": "synthesis_parity_probe",
            "group_by": ["g"], "metrics": [{"function": "sum", "column": "x", "as": "sx"}],
            "transforms": [{"op": "derive", "as": "x", "expr": EXPRESSIONS[name]}]}
    execute(repo, "job", {"execution_spec": spec, "thread_id": "t"})
    engine = pd.read_parquet(repo / "data_lake/synthesis/thread_outputs/t/job/output.parquet")

    out = tmp_path / "exported.parquet"
    script = tmp_path / "exported.py"
    script.write_text(
        render_script(spec, {"a": fingerprint_path(repo / "data/a.parquet")})
        + f"\nresult.to_parquet({str(out)!r})\n", encoding="utf-8")
    done = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, timeout=300)
    assert done.returncode == 0, f"{name}: {done.stderr[-300:]}"
    pd.testing.assert_frame_equal(engine, pd.read_parquet(out), check_dtype=False)
