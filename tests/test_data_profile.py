"""A column's danger is derivable from the data, so derive it before a study uses it.

Every flag here was first found by hand on idn_fry_daily_cross_section, which
carries nine forward-return columns, one pair of the same series in two units,
one column blank in 93% of rows, and four floats holding a handful of levels.
The profiler reproduces that set, and these fixtures pin each rule separately so
a failure names which one broke.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from scripts.research_data_mcp.synthesis.data_profile import (
    join_coverage,
    profile_columns,
    summarise,
)


def _write(tmp_path: Path, frame: pd.DataFrame, name: str = "a") -> Path:
    path = tmp_path / f"{name}.parquet"
    frame.to_parquet(path)
    return path


def _flags(rows, column):
    return next(r["flags"] for r in rows if r["column"] == column)


def test_a_forward_looking_column_is_flagged(tmp_path):
    rows = profile_columns(_write(tmp_path, pd.DataFrame(
        {"ret": [i / 40 for i in range(40)],
         "fwd_5d": [i / 30 for i in range(40)],
         "fwd_max_1d": [i / 20 for i in range(40)]})))
    assert "lookahead" in _flags(rows, "fwd_5d")
    assert "lookahead" in _flags(rows, "fwd_max_1d")
    assert _flags(rows, "ret") == []


def test_a_past_looking_name_is_not_flagged(tmp_path):
    """dd_60d and rsi14 are backward looking; only forward names are excluded."""
    rows = profile_columns(_write(tmp_path, pd.DataFrame(
        {"dd_60d": [i / 40 for i in range(40)],
         "rsi14": [i / 30 for i in range(40)],
         "backward_ret": [i / 20 for i in range(40)]})))
    assert all(r["flags"] == [] for r in rows)


def test_two_columns_of_the_same_series_in_different_units_are_paired(tmp_path):
    values = [i / 1000 for i in range(2000)]
    rows = profile_columns(_write(tmp_path, pd.DataFrame(
        {"r": values, "r_pct": [v * 100 for v in values]})))
    assert "unit_twin" in _flags(rows, "r")
    assert "unit_twin" in _flags(rows, "r_pct")
    assert next(r for r in rows if r["column"] == "r")["twin_of"] == "r_pct"


def test_two_unrelated_measurements_are_not_paired(tmp_path):
    """Same cardinality alone must not pair them; the magnitudes must differ ~100x."""
    values = [i / 1000 for i in range(2000)]
    rows = profile_columns(_write(tmp_path, pd.DataFrame(
        {"r": values, "s": [v * 1.5 for v in values]})))
    assert all("unit_twin" not in r["flags"] for r in rows)


def test_a_mostly_blank_column_is_flagged(tmp_path):
    column = [1.0] * 5 + [None] * 95
    rows = profile_columns(_write(tmp_path, pd.DataFrame({"sparse": column})))
    assert "sparse" in _flags(rows, "sparse")
    assert next(r for r in rows if r["column"] == "sparse")["blanks"] == 95


def test_a_never_populated_column_is_empty_not_sparse(tmp_path):
    rows = profile_columns(_write(tmp_path, pd.DataFrame({"isin": [None] * 50}, dtype="float64")))
    assert "empty" in _flags(rows, "isin")
    assert "sparse" not in _flags(rows, "isin")


def test_a_float_holding_ten_levels_is_a_score_not_a_measurement(tmp_path):
    rows = profile_columns(_write(tmp_path, pd.DataFrame({"decile": [float(i % 10) for i in range(200)]})))
    entry = next(r for r in rows if r["column"] == "decile")
    assert entry["kind"] == "score"
    assert "score" in entry["flags"]


def test_kinds_are_named_in_research_language(tmp_path):
    rows = profile_columns(_write(tmp_path, pd.DataFrame({
        "d": pd.to_datetime(["2024-01-01"] * 40),
        "sector": ["a", "b"] * 20,
        "symbol": [f"S{i}" for i in range(40)],
        "flag": [0, 1] * 20,
        "v": [float(i) for i in range(40)]})))
    kinds = {r["column"]: r["kind"] for r in rows}
    assert kinds == {"d": "date", "sector": "label", "symbol": "name",
                     "flag": "yes/no", "v": "measurement"}


def test_the_summary_counts_what_is_unremarkable(tmp_path):
    rows = profile_columns(_write(tmp_path, pd.DataFrame(
        {"ok": [float(i) for i in range(40)], "fwd_1d": [i / 7 for i in range(40)]})))
    out = summarise(rows)
    assert out["columns"] == 2
    assert out["unflagged"] == 1
    assert out["by_flag"]["lookahead"] == ["fwd_1d"]


# join coverage — cardinality is the question people ask, coverage decides the study

@pytest.fixture
def sides(tmp_path):
    left = _write(tmp_path, pd.DataFrame({"sym": [f"S{i}" for i in range(10)]}), "l")
    right = _write(tmp_path, pd.DataFrame({
        "sym": ["S0", "S1", "S1"], "ric": ["S0.JK", "S1.JK", "S1.JK"],
        "other": ["x", "y", "z"], "isin": [None, None, None]}), "r")
    return left, right


def test_coverage_reports_the_share_of_the_left_side_reached(sides):
    left, right = sides
    row = join_coverage(left, right, ["sym"])[0]
    assert row["matched"] == 2
    assert row["left_distinct"] == 10
    assert row["match_rate_pct"] == 20.0


def test_duplicate_right_rows_are_counted_separately_from_coverage(sides):
    left, right = sides
    row = join_coverage(left, right, ["sym"])[0]
    assert row["right_duplicate_rows"] == 1


def test_a_cross_named_key_is_supported(sides):
    """The engine takes left_on and right_on, so a same-name check would miss links."""
    left, right = sides
    row = join_coverage(left, right, [("sym", "ric")])[0]
    assert row["left_key"] == "sym" and row["right_key"] == "ric"
    assert row["matched"] == 0
    assert row["reason"] == "no value in common"


def test_an_empty_right_column_says_so(sides):
    left, right = sides
    row = join_coverage(left, right, [("sym", "isin")])[0]
    assert row["usable"] is False
    assert row["reason"] == "the column is empty on the right side"


def test_a_missing_column_is_reported_not_raised(sides):
    left, right = sides
    row = join_coverage(left, right, [("sym", "nope")])[0]
    assert row["reason"] == "not present on both sides"


def test_candidates_are_ranked_by_coverage(sides):
    left, right = sides
    rows = join_coverage(left, right, [("sym", "ric"), "sym"])
    assert [r["right_key"] for r in rows] == ["sym", "ric"]


def test_a_single_valued_column_is_constant_not_a_score(tmp_path):
    """A column with one value cannot separate anything; calling it a score invites
    a group-by that returns one row."""
    rows = profile_columns(_write(tmp_path, pd.DataFrame({"same": [0.1] * 40})))
    entry = next(r for r in rows if r["column"] == "same")
    assert entry["kind"] == "constant"
    assert entry["flags"] == ["constant"]


def test_a_csv_is_profiled_the_same_way(tmp_path):
    """stablecoin_trust_engagement_weekly is csv; a parquet-only profiler saw nothing."""
    frame = pd.DataFrame({"sym": [f"S{i}" for i in range(40)],
                          "fwd_1d": [i / 7 for i in range(40)],
                          "blank": [None] * 40})
    path = tmp_path / "a.csv"
    frame.to_csv(path, index=False)
    rows = profile_columns(path)
    assert {r["column"] for r in rows} == {"sym", "fwd_1d", "blank"}
    assert "lookahead" in _flags(rows, "fwd_1d")
    assert "empty" in _flags(rows, "blank")


def test_a_large_non_parquet_file_is_refused_with_a_reason(tmp_path, monkeypatch):
    """Parsing a whole csv to describe it can cost more than the answer is worth."""
    from scripts.research_data_mcp.synthesis import data_profile

    path = tmp_path / "a.csv"
    pd.DataFrame({"v": [1.0, 2.0]}).to_csv(path, index=False)
    monkeypatch.setattr(data_profile, "MAX_NON_PARQUET_BYTES", 1)
    with pytest.raises(ValueError, match="not parquet"):
        data_profile.profile_columns(path)
