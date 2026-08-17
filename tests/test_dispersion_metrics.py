"""Dispersion is available, not imposed.

With only count/sum/mean/min/max the engine could state an effect size and never
its spread. A grouped mean of fwd_return_4w on the fused Asia panel read as a
tradeable finding; the same query with std and a baseline puts every country's
t-statistic under 0.51. The engine supplies the spread and judges nothing — a
spec asking for mean alone still runs.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from scripts.research_data_mcp.synthesis_executor import execute, validate_execution_spec
from scripts.research_data_mcp.synthesis.spec_export import fingerprint_path, render_script

FRAME = pd.DataFrame({
    "g": ["a"] * 5 + ["b"] * 5,
    "v": [1.0, 2.0, 3.0, 4.0, 100.0, 2.0, 2.0, 2.0, 2.0, 2.0],
})


def _repo(tmp_path: Path) -> Path:
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    FRAME.to_parquet(tmp_path / "data/a.parquet")
    (tmp_path / "config/research_query_registry.json").write_text(
        json.dumps({"datasets": [{"dataset_id": "a", "name": "a",
                                  "local_path": "data/a.parquet", "grain": "row"}]}),
        encoding="utf-8")
    return tmp_path


def _spec(metrics, group_by=("g",)):
    return {"input_dataset_id": "a", "output_dataset_id": "synthesis_dispersion_probe",
            "group_by": list(group_by), "metrics": metrics}


def _run(repo: Path, spec: dict, job: str = "job") -> pd.DataFrame:
    execute(repo, job, {"execution_spec": spec, "thread_id": "t"})
    return pd.read_parquet(repo / f"data_lake/synthesis/thread_outputs/t/{job}/output.parquet")


ALL_METRICS = [
    {"function": "count", "as": "n"},
    {"function": "mean", "column": "v", "as": "m"},
    {"function": "std", "column": "v", "as": "sd"},
    {"function": "median", "column": "v", "as": "med"},
    {"function": "nunique", "column": "v", "as": "nu"},
    {"function": "quantile", "column": "v", "q": 0.9, "as": "p90"},
]


def test_spread_separates_a_wide_group_from_a_tight_one(tmp_path):
    """Both groups can share a mean while one is noise and the other is not."""
    out = _run(_repo(tmp_path), _spec(ALL_METRICS)).set_index("g")
    assert out.loc["a", "sd"] > 40
    assert out.loc["b", "sd"] == 0.0
    assert out.loc["a", "med"] == 3.0
    assert out.loc["b", "nu"] == 1


def test_each_new_metric_matches_pandas(tmp_path):
    out = _run(_repo(tmp_path), _spec(ALL_METRICS)).sort_values("g").reset_index(drop=True)
    grouped = FRAME.groupby("g", dropna=False)
    want = pd.DataFrame({"m": grouped["v"].mean(), "sd": grouped["v"].std(),
                         "med": grouped["v"].median(), "nu": grouped["v"].nunique(),
                         "p90": grouped["v"].quantile(0.9)}).reset_index()
    for column in ("m", "sd", "med", "nu", "p90"):
        pd.testing.assert_series_equal(out[column], want[column], check_dtype=False)


def test_a_spec_asking_only_for_a_mean_still_runs(tmp_path):
    """Availability, not enforcement — the engine does not require dispersion."""
    out = _run(_repo(tmp_path), _spec([{"function": "mean", "column": "v", "as": "m"}]))
    assert list(out.columns) == ["g", "m"]


def test_quantile_requires_its_fraction():
    with pytest.raises(ValueError, match="quantile requires q"):
        validate_execution_spec(_spec([{"function": "quantile", "column": "v", "as": "p"}]))


@pytest.mark.parametrize("q", [-0.1, 1.5, "high"])
def test_a_nonsense_quantile_is_refused(q):
    with pytest.raises(ValueError, match="quantile q must be"):
        validate_execution_spec(_spec([{"function": "quantile", "column": "v", "q": q, "as": "p"}]))


def test_a_boundary_quantile_is_allowed():
    for q in (0.0, 1.0):
        out = validate_execution_spec(_spec([{"function": "quantile", "column": "v", "q": q, "as": "p"}]))
        assert out["metrics"][0]["q"] == q


def test_dispersion_metrics_need_a_column():
    with pytest.raises(ValueError, match="require a source column"):
        validate_execution_spec(_spec([{"function": "std", "as": "sd"}]))


def test_the_exported_script_reproduces_every_new_metric(tmp_path):
    repo = _repo(tmp_path)
    spec = _spec(ALL_METRICS)
    engine = _run(repo, spec)
    out = tmp_path / "exported.parquet"
    script = tmp_path / "exported.py"
    script.write_text(
        render_script(spec, {"a": fingerprint_path(repo / "data/a.parquet")})
        + f"\nresult.to_parquet({str(out)!r})\n", encoding="utf-8")
    done = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, timeout=300)
    assert done.returncode == 0, done.stderr[-400:]
    pd.testing.assert_frame_equal(
        engine.sort_values("g").reset_index(drop=True),
        pd.read_parquet(out).sort_values("g").reset_index(drop=True),
        check_dtype=False)


def test_ungrouped_dispersion_covers_the_whole_frame(tmp_path):
    out = _run(_repo(tmp_path), _spec(ALL_METRICS, group_by=()))
    assert len(out) == 1
    assert out["sd"].iloc[0] == pytest.approx(FRAME["v"].std())
    assert out["med"].iloc[0] == pytest.approx(FRAME["v"].median())


def test_an_ungrouped_export_reproduces_dispersion(tmp_path):
    repo = _repo(tmp_path)
    spec = _spec(ALL_METRICS, group_by=())
    engine = _run(repo, spec, "ungrouped")
    out = tmp_path / "u.parquet"
    script = tmp_path / "u.py"
    script.write_text(
        render_script(spec, {"a": fingerprint_path(repo / "data/a.parquet")})
        + f"\nresult.to_parquet({str(out)!r})\n", encoding="utf-8")
    subprocess.run([sys.executable, str(script)], capture_output=True, text=True,
                   timeout=300, check=True)
    pd.testing.assert_frame_equal(engine, pd.read_parquet(out), check_dtype=False)
