"""probe_pair reports what the bytes say, and refuses to report anything else."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

from scripts.research_data_mcp.synthesis.pair_probe import probe_pair, probe_summary


def _write(tmp_path: Path, name: str, frame: pd.DataFrame) -> Path:
    path = tmp_path / name
    frame.to_parquet(path)
    return path


def test_perfect_overlap_is_reported_as_measured(tmp_path):
    left = _write(tmp_path, "l.parquet", pd.DataFrame({"ric": ["A", "B", "C"]}))
    right = _write(tmp_path, "r.parquet", pd.DataFrame({"ric": ["A", "B", "C"], "v": [1, 2, 3]}))
    p = probe_pair(left, right, "ric")
    assert p["shared_distinct"] == 3
    assert p["coverage_left_pct"] == 100.0
    assert p["coverage_right_pct"] == 100.0
    assert p["probe_error"] is None


def test_partial_overlap_is_not_rounded_up(tmp_path):
    left = _write(tmp_path, "l.parquet", pd.DataFrame({"ric": ["A", "B", "C", "D"]}))
    right = _write(tmp_path, "r.parquet", pd.DataFrame({"ric": ["C", "D", "E"]}))
    p = probe_pair(left, right, "ric")
    assert p["shared_distinct"] == 2
    assert p["coverage_left_pct"] == 50.0
    assert p["coverage_right_pct"] == pytest.approx(66.7, abs=0.1)


def test_zero_overlap_reports_zero_not_a_floor(tmp_path):
    """The retired heuristic invented 35% from a grain match. A probe cannot."""
    left = _write(tmp_path, "l.parquet", pd.DataFrame({"ric": ["A", "B"]}))
    right = _write(tmp_path, "r.parquet", pd.DataFrame({"ric": ["X", "Y"]}))
    p = probe_pair(left, right, "ric")
    assert p["shared_distinct"] == 0
    assert p["coverage_left_pct"] == 0.0
    assert p["coverage_right_pct"] == 0.0


def test_one_to_many_side_is_flagged_for_an_explicit_collapse(tmp_path):
    left = _write(tmp_path, "l.parquet", pd.DataFrame({"ric": ["A", "B"]}))
    right = _write(tmp_path, "r.parquet", pd.DataFrame({"ric": ["A", "A", "B"], "metric": [1, 2, 3]}))
    p = probe_pair(left, right, "ric")
    assert p["left_cardinality"] == "1:1"
    assert p["right_cardinality"] == "1:N"
    assert p["collapse_required"] is True
    assert "collapse rule is required" in probe_summary(p)


def test_one_to_one_needs_no_collapse(tmp_path):
    left = _write(tmp_path, "l.parquet", pd.DataFrame({"ric": ["A", "B"]}))
    right = _write(tmp_path, "r.parquet", pd.DataFrame({"ric": ["A", "B"], "v": [1, 2]}))
    p = probe_pair(left, right, "ric")
    assert p["collapse_required"] is False


def test_missing_key_yields_an_error_and_no_numbers(tmp_path):
    left = _write(tmp_path, "l.parquet", pd.DataFrame({"ric": ["A"]}))
    right = _write(tmp_path, "r.parquet", pd.DataFrame({"other": ["A"]}))
    p = probe_pair(left, right, "ric")
    assert p["probe_error"]
    assert p["shared_distinct"] == 0
    assert p["coverage_left_pct"] is None
    assert probe_summary(p).startswith("Not probed")


def test_unresolved_path_is_an_error_not_an_assumption(tmp_path):
    left = _write(tmp_path, "l.parquet", pd.DataFrame({"ric": ["A"]}))
    p = probe_pair(left, tmp_path / "nope", "ric")
    assert p["probe_error"]
    assert p["coverage_right_pct"] is None


def test_no_key_supplied_is_refused(tmp_path):
    left = _write(tmp_path, "l.parquet", pd.DataFrame({"ric": ["A"]}))
    p = probe_pair(left, left, "")
    assert p["probe_error"] == "no join key supplied"


def test_key_match_is_case_insensitive_on_the_column_name(tmp_path):
    left = _write(tmp_path, "l.parquet", pd.DataFrame({"RIC": ["A", "B"]}))
    right = _write(tmp_path, "r.parquet", pd.DataFrame({"ric": ["A", "B"]}))
    p = probe_pair(left, right, "ric")
    assert p["shared_distinct"] == 2


def test_probe_carries_a_timestamp_so_a_result_can_go_stale(tmp_path):
    left = _write(tmp_path, "l.parquet", pd.DataFrame({"ric": ["A"]}))
    p = probe_pair(left, left, "ric")
    assert p["probed_at"]


def test_partial_key_on_a_panel_overstates_joinability(tmp_path):
    """A (symbol, week) panel probed on symbol alone reports coverage no join achieves."""
    left = _write(tmp_path, "l.parquet", pd.DataFrame(
        {"sym": ["A", "A", "B"], "week": ["w1", "w2", "w1"]}))
    right = _write(tmp_path, "r.parquet", pd.DataFrame(
        {"sym": ["A", "B"], "week": ["w1", "w9"], "v": [1, 2]}))
    partial = probe_pair(left, right, "sym")
    composite = probe_pair(left, right, ["sym", "week"])
    assert partial["coverage_right_pct"] == 100.0
    assert composite["coverage_right_pct"] == 50.0
    assert composite["key_parts"] == ["sym", "week"]


def test_composite_key_resolves_a_panel_to_one_to_one(tmp_path):
    left = _write(tmp_path, "l.parquet", pd.DataFrame(
        {"sym": ["A", "A"], "week": ["w1", "w2"]}))
    right = _write(tmp_path, "r.parquet", pd.DataFrame(
        {"sym": ["A", "A"], "week": ["w1", "w2"], "v": [1, 2]}))
    assert probe_pair(left, right, "sym")["collapse_required"] is True
    assert probe_pair(left, right, ["sym", "week"])["collapse_required"] is False


def test_missing_one_part_of_a_composite_key_is_an_error(tmp_path):
    left = _write(tmp_path, "l.parquet", pd.DataFrame({"sym": ["A"], "week": ["w1"]}))
    right = _write(tmp_path, "r.parquet", pd.DataFrame({"sym": ["A"]}))
    p = probe_pair(left, right, ["sym", "week"])
    assert p["probe_error"]
    assert "not fully present" in p["probe_error"]
