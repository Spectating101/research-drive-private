"""An as-of join that matched nothing must not look like a measured zero.

merge_asof leaves unmatched left rows as NaN, and sum() of NaN is 0.0. It also
silently drops left rows whose as-of column will not parse as a date. Both are
row loss the researcher never saw. Backward must also never read a value dated
after the row it is attached to.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from scripts.research_data_mcp.synthesis_executor import execute

LEFT = pd.DataFrame({"d": ["2024-01-03", "2024-01-06"], "id": [1, 2]})
RIGHT = pd.DataFrame({"d": pd.to_datetime(["2024-01-01", "2024-01-05", "2024-01-09"]),
                      "fact": [10.0, 50.0, 90.0]})


def _repo(tmp_path: Path, left: pd.DataFrame = LEFT, right: pd.DataFrame = RIGHT) -> Path:
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


def _spec(**step_over):
    step = {"op": "join_asof", "right_dataset_id": "b", "on": "d", "direction": "backward"}
    step.update(step_over)
    return {"input_dataset_id": "a", "output_dataset_id": "synthesis_asof_probe",
            "group_by": ["id"], "metrics": [{"function": "sum", "column": "fact", "as": "f"}],
            "transforms": [step]}


def _run(repo: Path, spec: dict, job: str = "job"):
    result = execute(repo, job, {"execution_spec": spec, "thread_id": "t"})
    out = pd.read_parquet(repo / f"data_lake/synthesis/thread_outputs/t/{job}/output.parquet")
    return result, dict(zip(out["id"], out["f"]))


def test_backward_never_reads_a_value_dated_after_the_row(tmp_path):
    """Jan 3 must see Jan 1's 10, not Jan 5's 50."""
    _, got = _run(_repo(tmp_path), _spec())
    assert got[1] == 10.0
    assert got[2] == 50.0


@pytest.mark.parametrize("direction,first", [("forward", 50.0), ("nearest", 10.0)])
def test_the_other_directions_behave_as_documented(tmp_path, direction, first):
    _, got = _run(_repo(tmp_path), _spec(direction=direction), f"job_{direction}")
    assert got[1] == first


def test_tolerance_bounds_how_stale_a_match_may_be(tmp_path):
    """Jan 3 is two days past Jan 1, so a 1-day tolerance must reject it."""
    _, got = _run(_repo(tmp_path), _spec(tolerance="1D"))
    assert got[1] == 0.0
    assert got[2] == 50.0


def test_an_unmatched_row_is_counted_not_silently_zero(tmp_path):
    result, got = _run(_repo(tmp_path), _spec(tolerance="1D"))
    coverage = result["asof_coverage"][0]
    assert coverage["matched_rows"] == 1
    assert coverage["unmatched_rows"] == 1
    assert coverage["match_rate_pct"] == 50.0
    assert got[1] == 0.0


def test_a_left_row_with_an_unparseable_date_is_reported(tmp_path):
    left = pd.DataFrame({"d": ["2024-01-03", "2024-01-06", "not-a-date"], "id": [1, 2, 3]})
    result, got = _run(_repo(tmp_path, left=left), _spec())
    coverage = result["asof_coverage"][0]
    assert coverage["left_rows"] == 3
    assert coverage["undated_left_rows_dropped"] == 1
    assert 3 not in got


def test_full_coverage_reports_a_hundred_percent(tmp_path):
    result, _ = _run(_repo(tmp_path), _spec())
    coverage = result["asof_coverage"][0]
    assert coverage["unmatched_rows"] == 0
    assert coverage["match_rate_pct"] == 100.0
    assert coverage["undated_left_rows_dropped"] == 0


def test_coverage_is_written_to_the_manifest(tmp_path):
    repo = _repo(tmp_path)
    execute(repo, "job", {"execution_spec": _spec(tolerance="1D"), "thread_id": "t"})
    manifest = json.loads((repo / "data_lake/synthesis/thread_outputs/t/job/manifest.json").read_text())
    assert manifest["asof_coverage"][0]["match_rate_pct"] == 50.0


def test_a_spec_with_no_asof_reports_an_empty_coverage_list(tmp_path):
    repo = _repo(tmp_path)
    spec = {"input_dataset_id": "a", "output_dataset_id": "synthesis_plain_probe",
            "group_by": ["id"], "metrics": [{"function": "count", "as": "n"}]}
    result = execute(repo, "job", {"execution_spec": spec, "thread_id": "t"})
    assert result["asof_coverage"] == []


def test_the_marker_column_never_reaches_the_output(tmp_path):
    repo = _repo(tmp_path)
    execute(repo, "job", {"execution_spec": _spec(), "thread_id": "t"})
    out = pd.read_parquet(repo / "data_lake/synthesis/thread_outputs/t/job/output.parquet")
    assert not any(str(c).startswith("__asof") for c in out.columns)
