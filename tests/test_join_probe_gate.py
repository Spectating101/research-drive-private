"""A declared join must be measured before it can be proposed."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from scripts.research_data_mcp.synthesis_executor import (
    preflight_execution_spec,
    validate_execution_spec,
)


def _repo(tmp_path: Path, rows: dict[str, pd.DataFrame]) -> Path:
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    datasets = []
    for dataset_id, frame in rows.items():
        rel = f"data/{dataset_id}.parquet"
        frame.to_parquet(tmp_path / rel)
        datasets.append({
            "dataset_id": dataset_id,
            "name": dataset_id,
            "local_path": rel,
            "grain": "instrument_snapshot",
            "join_keys": ["ric"],
        })
    (tmp_path / "config/research_query_registry.json").write_text(
        json.dumps({"datasets": datasets}), encoding="utf-8"
    )
    return tmp_path


def _spec(**over):
    spec = {
        "input_dataset_id": "spine",
        "output_dataset_id": "synthesis_join_probe_out",
        "group_by": ["ric"],
        "metrics": [{"function": "count", "as": "n"}],
        "transforms": [{"op": "join", "right_dataset_id": "attr", "on": ["ric"], "how": "inner"}],
    }
    spec.update(over)
    return spec


def test_collapse_strategy_is_validated():
    spec = _spec(transforms=[{
        "op": "join", "right_dataset_id": "attr", "on": ["ric"],
        "collapse": {"strategy": "nonsense"},
    }])
    with pytest.raises(ValueError, match="collapse strategy"):
        validate_execution_spec(spec)


def test_collapse_is_optional_and_normalised():
    out = validate_execution_spec(_spec(transforms=[{
        "op": "join", "right_dataset_id": "attr", "on": ["ric"],
        "collapse": {"strategy": "FIRST"},
    }]))
    assert out["transforms"][0]["collapse"] == {"strategy": "first"}


def test_overlapping_join_is_measured_and_passes(tmp_path):
    repo = _repo(tmp_path, {
        "spine": pd.DataFrame({"ric": ["A", "B", "C"]}),
        "attr": pd.DataFrame({"ric": ["A", "B", "C"], "v": [1, 2, 3]}),
    })
    report = preflight_execution_spec(repo, _spec())
    assert report["ok"] is True
    probe = report["join_probes"][0]
    assert probe["shared_distinct"] == 3
    assert probe["coverage_right_pct"] == 100.0


def test_join_with_no_shared_keys_is_an_issue_not_a_silent_empty(tmp_path):
    repo = _repo(tmp_path, {
        "spine": pd.DataFrame({"ric": ["A", "B"]}),
        "attr": pd.DataFrame({"ric": ["X", "Y"], "v": [1, 2]}),
    })
    report = preflight_execution_spec(repo, _spec())
    assert report["ok"] is False
    assert any(i["code"] == "empty_join" for i in report["issues"])


def test_one_to_many_join_requires_an_explicit_collapse_rule(tmp_path):
    repo = _repo(tmp_path, {
        "spine": pd.DataFrame({"ric": ["A", "B"]}),
        "attr": pd.DataFrame({"ric": ["A", "A", "B"], "v": [1, 2, 3]}),
    })
    report = preflight_execution_spec(repo, _spec())
    assert report["ok"] is False
    issue = next(i for i in report["issues"] if i["code"] == "collapse_rule_required")
    assert "1:N" in issue["detail"]


def test_declaring_a_collapse_rule_clears_the_fan_out_issue(tmp_path):
    repo = _repo(tmp_path, {
        "spine": pd.DataFrame({"ric": ["A", "B"]}),
        "attr": pd.DataFrame({"ric": ["A", "A", "B"], "v": [1, 2, 3]}),
    })
    spec = _spec(transforms=[{
        "op": "join", "right_dataset_id": "attr", "on": ["ric"],
        "how": "inner", "collapse": {"strategy": "first"},
    }])
    report = preflight_execution_spec(repo, spec)
    assert not any(i["code"] == "collapse_rule_required" for i in report["issues"])


def test_partial_overlap_is_reported_without_blocking(tmp_path):
    repo = _repo(tmp_path, {
        "spine": pd.DataFrame({"ric": ["A", "B", "C", "D"]}),
        "attr": pd.DataFrame({"ric": ["C", "D"], "v": [1, 2]}),
    })
    report = preflight_execution_spec(repo, _spec())
    probe = report["join_probes"][0]
    assert probe["shared_distinct"] == 2
    assert probe["coverage_left_pct"] == 50.0
    assert not any(i["code"] == "empty_join" for i in report["issues"])


def test_frequency_mismatch_is_blocked_when_both_sides_lose_most_rows(tmp_path):
    """Daily against month-start dates: a handful of accidental matches."""
    daily = pd.DataFrame({"ric": [f"d{i:03d}" for i in range(300)]})
    monthly = pd.DataFrame({"ric": [f"d{i:03d}" for i in range(0, 300, 30)] + [f"m{i}" for i in range(90)],
                            "v": range(100)})
    repo = _repo(tmp_path, {"spine": daily, "attr": monthly})
    report = preflight_execution_spec(repo, _spec())
    issue = next(i for i in report["issues"] if i["code"] == "join_discards_most_rows")
    assert issue["retained_left_pct"] < 20
    assert issue["retained_right_pct"] < 20


def test_history_truncation_is_allowed(tmp_path):
    """A long spine joined to a short series keeps all of the short one — normal."""
    long_side = pd.DataFrame({"ric": [f"d{i:04d}" for i in range(2000)]})
    short_side = pd.DataFrame({"ric": [f"d{i:04d}" for i in range(200)], "v": range(200)})
    repo = _repo(tmp_path, {"spine": long_side, "attr": short_side})
    report = preflight_execution_spec(repo, _spec())
    assert not any(i["code"] == "join_discards_most_rows" for i in report["issues"])


def test_accept_row_loss_lets_a_researcher_proceed_deliberately(tmp_path):
    daily = pd.DataFrame({"ric": [f"d{i:03d}" for i in range(300)]})
    monthly = pd.DataFrame({"ric": [f"d{i:03d}" for i in range(0, 300, 30)] + [f"m{i}" for i in range(90)],
                            "v": range(100)})
    repo = _repo(tmp_path, {"spine": daily, "attr": monthly})
    spec = _spec(transforms=[{"op": "join", "right_dataset_id": "attr", "on": ["ric"],
                              "how": "inner", "accept_row_loss": True}])
    report = preflight_execution_spec(repo, spec)
    assert not any(i["code"] == "join_discards_most_rows" for i in report["issues"])


def test_column_collision_is_named_with_the_suffix_that_wins(tmp_path):
    repo = _repo(tmp_path, {
        "spine": pd.DataFrame({"ric": ["A", "B"], "v": [1.0, 2.0]}),
        "attr": pd.DataFrame({"ric": ["A", "B"], "v": [99.0, 98.0]}),
    })
    report = preflight_execution_spec(repo, _spec())
    warn = next(w for w in report["warnings"] if "both sides" in w)
    assert "v_right" in warn


def test_left_join_denominator_mismatch_is_warned(tmp_path):
    repo = _repo(tmp_path, {
        "spine": pd.DataFrame({"ric": ["A", "B", "C", "D"]}),
        "attr": pd.DataFrame({"ric": ["A", "B"], "y": [10.0, 20.0]}),
    })
    spec = _spec(
        metrics=[{"function": "mean", "column": "y", "as": "mean_y"},
                 {"function": "count", "as": "n"}],
        transforms=[{"op": "join", "right_dataset_id": "attr", "on": ["ric"],
                     "how": "left", "accept_row_loss": True}],
    )
    report = preflight_execution_spec(repo, spec)
    assert any("different" in w and "row counts" in w for w in report["warnings"])


def test_inner_join_does_not_warn_about_denominators(tmp_path):
    repo = _repo(tmp_path, {
        "spine": pd.DataFrame({"ric": ["A", "B"]}),
        "attr": pd.DataFrame({"ric": ["A", "B"], "y": [10.0, 20.0]}),
    })
    spec = _spec(metrics=[{"function": "mean", "column": "y", "as": "mean_y"}])
    report = preflight_execution_spec(repo, spec)
    assert not any("row counts" in w for w in report["warnings"])
