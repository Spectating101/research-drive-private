"""Point-in-time join: the most recent right row as of each left timestamp."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from scripts.research_data_mcp.synthesis.spec_export import fingerprint_path, render_script
from scripts.research_data_mcp.synthesis_executor import (
    execute,
    preflight_execution_spec,
    validate_execution_spec,
)

DAILY = pd.DataFrame({
    "date": pd.date_range("2024-01-01", periods=90, freq="D").strftime("%Y-%m-%d"),
    "ric": ["AAPL.O"] * 90,
    "px": range(90),
})
MONTHLY = pd.DataFrame({
    "date": ["2023-12-01", "2024-01-01", "2024-02-01", "2024-03-01"],
    "ric": ["AAPL.O"] * 4,
    "book_value": [10.0, 11.0, 12.0, 13.0],
})


def _repo(tmp_path: Path, frames: dict[str, pd.DataFrame]) -> Path:
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    ds = []
    for name, frame in frames.items():
        frame.to_parquet(tmp_path / f"data/{name}.parquet")
        ds.append({"dataset_id": name, "name": name, "local_path": f"data/{name}.parquet",
                   "grain": "g", "join_keys": ["ric"]})
    (tmp_path / "config/research_query_registry.json").write_text(
        json.dumps({"datasets": ds}), encoding="utf-8")
    return tmp_path


def _spec(**over):
    step = {"op": "join_asof", "right_dataset_id": "fund", "on": "date", "by": ["ric"],
            "direction": "backward", "tolerance": "40D"}
    step.update(over.pop("step", {}))
    spec = {"input_dataset_id": "px", "output_dataset_id": "synthesis_asof_test_v1",
            "group_by": [], "metrics": [{"function": "count", "as": "n"},
                                        {"function": "mean", "column": "book_value", "as": "bv"}],
            "transforms": [step]}
    spec.update(over)
    return spec


def _run(tmp_path, spec, jid="j"):
    repo = _repo(tmp_path, {"px": DAILY, "fund": MONTHLY})
    execute(repo, jid, {"execution_spec": spec, "thread_id": "t"})
    return pd.read_parquet(repo / f"data_lake/synthesis/thread_outputs/t/{jid}/output.parquet")


def test_asof_keeps_every_left_row_where_exact_match_would_not(tmp_path):
    out = _run(tmp_path, _spec())
    assert int(out["n"].iloc[0]) == 90


def test_asof_carries_the_most_recent_prior_value(tmp_path):
    """31 days at 11.0, 29 at 12.0, 30 at 13.0 -> 11.99."""
    out = _run(tmp_path, _spec())
    assert float(out["bv"].iloc[0]) == pytest.approx((31 * 11 + 29 * 12 + 30 * 13) / 90, abs=1e-6)


def test_exact_join_on_the_same_data_keeps_almost_nothing(tmp_path):
    """The contrast that motivates as-of at all."""
    spec = {"input_dataset_id": "px", "output_dataset_id": "synthesis_asof_exact_v1",
            "group_by": [], "metrics": [{"function": "count", "as": "n"}],
            "transforms": [{"op": "join", "right_dataset_id": "fund", "on": ["date"],
                            "how": "inner", "accept_row_loss": True}]}
    assert int(_run(tmp_path, spec, "x")["n"].iloc[0]) == 3


def test_tolerance_bounds_staleness(tmp_path):
    """A 5-day tolerance drops rows whose newest prior value is older than that."""
    out = _run(tmp_path, _spec(step={"tolerance": "5D"}), "tol")
    assert int(out["n"].iloc[0]) == 90  # rows survive; the value is null past tolerance
    assert float(out["bv"].iloc[0]) == pytest.approx(12.0, abs=1e-6)


def test_direction_must_be_known():
    with pytest.raises(ValueError, match="direction"):
        validate_execution_spec(_spec(step={"direction": "sideways"}))


def test_forward_direction_warns_about_lookahead(tmp_path):
    repo = _repo(tmp_path, {"px": DAILY, "fund": MONTHLY})
    report = preflight_execution_spec(repo, _spec(step={"direction": "forward"}))
    assert any("lookahead" in w for w in report["warnings"])


def test_missing_tolerance_warns_about_unbounded_staleness(tmp_path):
    repo = _repo(tmp_path, {"px": DAILY, "fund": MONTHLY})
    report = preflight_execution_spec(repo, _spec(step={"tolerance": None}))
    assert any("staleness" in w for w in report["warnings"])


def test_no_shared_entities_is_an_issue(tmp_path):
    other = MONTHLY.assign(ric="MSFT.O")
    repo = _repo(tmp_path, {"px": DAILY, "fund": other})
    report = preflight_execution_spec(repo, _spec())
    assert any(i["code"] == "empty_join" for i in report["issues"])


def test_asof_requires_a_single_ordered_column():
    with pytest.raises(ValueError, match="single ordered"):
        validate_execution_spec(_spec(step={"on": ""}))


def test_export_reproduces_the_asof_result(tmp_path):
    repo = _repo(tmp_path, {"px": DAILY, "fund": MONTHLY})
    spec = _spec()
    pf = preflight_execution_spec(repo, spec)
    execute(repo, "fid", {"execution_spec": spec, "thread_id": "t"})
    engine = pd.read_parquet(repo / "data_lake/synthesis/thread_outputs/t/fid/output.parquet")
    inputs = {n: fingerprint_path(repo / f"data/{n}.parquet") for n in ("px", "fund")}
    script = render_script(spec, inputs, probes=pf.get("join_probes"))
    path = repo / "m.py"
    path.write_text(script + f"\nresult.to_parquet(r'{repo}/o.parquet', index=False)\n", encoding="utf-8")
    run = subprocess.run([sys.executable, str(path)], capture_output=True, text=True, timeout=180)
    assert run.returncode == 0, run.stderr[-500:]
    pd.testing.assert_frame_equal(engine, pd.read_parquet(repo / "o.parquet"),
                                  check_dtype=False, rtol=1e-9)


MONTHLY_ALT = MONTHLY.rename(columns={"date": "as_of_date"})


def test_sides_may_name_the_time_column_differently(tmp_path):
    """A daily panel says `date`; a point-in-time snapshot says `as_of_date`."""
    repo = _repo(tmp_path, {"px": DAILY, "fund": MONTHLY_ALT})
    spec = _spec(step={"on": None, "left_on": "date", "right_on": "as_of_date"})
    spec["transforms"][0].pop("on", None)
    execute(repo, "alt", {"execution_spec": spec, "thread_id": "t"})
    out = pd.read_parquet(repo / "data_lake/synthesis/thread_outputs/t/alt/output.parquet")
    assert int(out["n"].iloc[0]) == 90


def test_on_and_left_on_together_are_refused():
    with pytest.raises(ValueError, match="either `on` or both"):
        validate_execution_spec(_spec(step={"left_on": "date", "right_on": "as_of_date"}))


def test_neither_on_nor_a_pair_is_refused():
    spec = _spec()
    spec["transforms"][0].pop("on")
    with pytest.raises(ValueError, match="left_on"):
        validate_execution_spec(spec)


def test_preflight_checks_each_side_against_its_own_column(tmp_path):
    repo = _repo(tmp_path, {"px": DAILY, "fund": MONTHLY_ALT})
    spec = _spec(step={"on": None, "left_on": "date", "right_on": "as_of_date"})
    spec["transforms"][0].pop("on", None)
    report = preflight_execution_spec(repo, spec)
    assert report["ok"], [i for i in report["issues"]]


def test_preflight_names_the_side_whose_column_is_missing(tmp_path):
    repo = _repo(tmp_path, {"px": DAILY, "fund": MONTHLY})  # right has `date`, not `as_of_date`
    spec = _spec(step={"on": None, "left_on": "date", "right_on": "as_of_date"})
    spec["transforms"][0].pop("on", None)
    report = preflight_execution_spec(repo, spec)
    issue = next(i for i in report["issues"] if i["code"] == "missing_column")
    assert issue["side"] == "right" and issue["column"] == "as_of_date"


def test_export_reproduces_a_split_column_asof(tmp_path):
    repo = _repo(tmp_path, {"px": DAILY, "fund": MONTHLY_ALT})
    spec = _spec(step={"on": None, "left_on": "date", "right_on": "as_of_date"})
    spec["transforms"][0].pop("on", None)
    pf = preflight_execution_spec(repo, spec)
    execute(repo, "altfid", {"execution_spec": spec, "thread_id": "t"})
    engine = pd.read_parquet(repo / "data_lake/synthesis/thread_outputs/t/altfid/output.parquet")
    inputs = {n: fingerprint_path(repo / f"data/{n}.parquet") for n in ("px", "fund")}
    script = render_script(spec, inputs, probes=pf.get("join_probes"))
    path = repo / "alt.py"
    path.write_text(script + f"\nresult.to_parquet(r'{repo}/alt.parquet', index=False)\n", encoding="utf-8")
    run = subprocess.run([sys.executable, str(path)], capture_output=True, text=True, timeout=180)
    assert run.returncode == 0, run.stderr[-500:]
    pd.testing.assert_frame_equal(engine, pd.read_parquet(repo / "alt.parquet"),
                                  check_dtype=False, rtol=1e-9)
