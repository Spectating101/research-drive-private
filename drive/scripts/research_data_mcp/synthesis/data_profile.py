"""What a column is, and what it would do to a study — measured, not named.

A researcher choosing evidence needs three things a schema does not carry: what
kind of thing the column holds, how much of it is missing, and whether using it
would quietly damage the result. All three are derivable from the data, and the
damage cases are the ones worth naming:

    lookahead   a forward-return column. A model given it predicts what it was
                already shown. idn_fry_daily_cross_section carries nine.
    unit twin   two columns with identical cardinality whose typical magnitudes
                differ by about 100×. return_1d and return_1d_pct are the same
                series in different units; using both counts evidence twice, and
                subtracting one from a third column in the other unit is a 100×
                error that produces a plausible number rather than a failure.
    sparse      mostly blank. days_to_10pct is blank in 93% of rows, so a metric
                over it is computed on 7% of the panel.
    score       stored as a float but holding a handful of levels. Averaging
                cs_move_decile averages a category code.
    constant    one value throughout. It cannot separate anything, so grouping or
                filtering on it does nothing a reader would expect.
    empty       present in the schema, never populated. refinitiv's isin column
                has 0 values across 570 rows.

Columns are read one at a time through pyarrow rather than by materialising the
frame. Profiling idn_fry_daily_cross_section as a frame costs about a gigabyte;
per column it costs a column.
"""

from __future__ import annotations

from collections import Counter
import re
from pathlib import Path
from typing import Any

FORWARD_LOOKING = re.compile(r"(^|_)(fwd|forward|future|next|lead)(_|\d|$)", re.I)
SPARSE_AT = 0.5
SCORE_LEVELS = 12
TWIN_RATIO = (50, 200)
TWIN_MIN_DISTINCT = 1000


def _kind(arrow_type, distinct: int, is_int: bool) -> str:
    import pyarrow as pa

    if pa.types.is_temporal(arrow_type):
        return "date"
    if pa.types.is_string(arrow_type) or pa.types.is_large_string(arrow_type):
        return "label" if distinct <= 25 else "name"
    if distinct <= 1:
        return "constant"
    if is_int and distinct <= 2:
        return "yes/no"
    if distinct <= SCORE_LEVELS:
        return "score"
    return "measurement"


MAX_NON_PARQUET_BYTES = 256 * 1024 * 1024


def profile_columns(path: Path | str) -> list[dict[str, Any]]:
    """One pass per column, so a 35-column panel costs a column and not a gigabyte.

    Only parquet can be read a column at a time. csv and jsonl have to be parsed
    whole, so they are profiled through pandas and refused above a size where that
    would cost more memory than the answer is worth.
    """
    path = Path(path)
    if path.suffix.lower() != ".parquet":
        return _profile_via_pandas(path)
    import pyarrow as pa
    import pyarrow.compute as pc
    import pyarrow.parquet as pq

    handle = pq.ParquetFile(str(path))
    total = handle.metadata.num_rows
    schema = handle.schema_arrow
    out: list[dict[str, Any]] = []
    for name in schema.names:
        column = handle.read(columns=[name]).column(name)
        arrow_type = schema.field(name).type
        blanks = int(column.null_count)
        try:
            distinct = int(pc.count_distinct(column).as_py() or 0)
        except pa.ArrowNotImplementedError:
            distinct = 0
        numeric = pa.types.is_floating(arrow_type) or pa.types.is_integer(arrow_type)
        magnitude = None
        if numeric and blanks < total:
            try:
                magnitude = pc.mean(pc.abs(column)).as_py()
            except (pa.ArrowNotImplementedError, pa.ArrowInvalid):
                magnitude = None
        row = {
            "column": name,
            "kind": _kind(arrow_type, distinct, pa.types.is_integer(arrow_type)),
            "rows": total,
            "blanks": blanks,
            "distinct": distinct,
            "typical_magnitude": magnitude,
            "flags": [],
        }
        if total and blanks == total:
            row["flags"].append("empty")
        elif total and blanks / total > SPARSE_AT:
            row["flags"].append("sparse")
        if FORWARD_LOOKING.search(name):
            row["flags"].append("lookahead")
        if row["kind"] == "score" and pa.types.is_floating(arrow_type):
            row["flags"].append("score")
        if row["kind"] == "constant" and "empty" not in row["flags"]:
            row["flags"].append("constant")
        out.append(row)
        del column
    _mark_unit_twins(out)
    return out


def _profile_via_pandas(path: Path) -> list[dict[str, Any]]:
    import pandas as pd

    size = path.stat().st_size
    if size > MAX_NON_PARQUET_BYTES:
        raise ValueError(
            f"{path.name} is {size / 1e6:.0f} MB and not parquet, so profiling it "
            "would mean parsing the whole file; convert it or profile a sample")
    from scripts.research_data_mcp.synthesis_executor import _read_frame

    frame = _read_frame(path)
    total = len(frame)
    rows: list[dict[str, Any]] = []
    for name in frame.columns:
        column = frame[name]
        distinct = int(column.nunique(dropna=True))
        blanks = int(column.isna().sum())
        is_int = pd.api.types.is_integer_dtype(column)
        is_num = pd.api.types.is_numeric_dtype(column)
        if pd.api.types.is_datetime64_any_dtype(column):
            kind = "date"
        elif distinct <= 1:
            kind = "constant"
        elif not is_num:
            kind = "label" if distinct <= 25 else "name"
        elif is_int and distinct <= 2:
            kind = "yes/no"
        elif distinct <= SCORE_LEVELS:
            kind = "score"
        else:
            kind = "measurement"
        magnitude = float(column.abs().mean()) if is_num and blanks < total else None
        row = {"column": str(name), "kind": kind, "rows": total, "blanks": blanks,
               "distinct": distinct, "typical_magnitude": magnitude, "flags": []}
        if total and blanks == total:
            row["flags"].append("empty")
        elif total and blanks / total > SPARSE_AT:
            row["flags"].append("sparse")
        if FORWARD_LOOKING.search(str(name)):
            row["flags"].append("lookahead")
        if kind == "score" and pd.api.types.is_float_dtype(column):
            row["flags"].append("score")
        if kind == "constant" and "empty" not in row["flags"]:
            row["flags"].append("constant")
        rows.append(row)
    _mark_unit_twins(rows)
    return rows


def _mark_unit_twins(rows: list[dict[str, Any]]) -> None:
    """Same cardinality and ~100× apart is one series recorded in two units."""
    candidates = [r for r in rows
                  if r["kind"] == "measurement"
                  and r["distinct"] >= TWIN_MIN_DISTINCT
                  and r["typical_magnitude"]]
    low, high = TWIN_RATIO
    for i, a in enumerate(candidates):
        for b in candidates[i + 1:]:
            if a["distinct"] != b["distinct"]:
                continue
            ratio = a["typical_magnitude"] / b["typical_magnitude"]
            if low < ratio < high or low < 1 / ratio < high:
                for side, other in ((a, b), (b, a)):
                    if "unit_twin" not in side["flags"]:
                        side["flags"].append("unit_twin")
                    side.setdefault("twin_of", other["column"])


def summarise(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """The counts a caller shows before it shows any column."""
    flagged = [r for r in rows if r["flags"]]
    by_flag: dict[str, list[str]] = {}
    for row in flagged:
        for flag in row["flags"]:
            by_flag.setdefault(flag, []).append(row["column"])
    return {
        "columns": len(rows),
        "unflagged": len(rows) - len(flagged),
        "by_flag": by_flag,
    }


def join_coverage(left_path: Path | str, right_path: Path | str,
                  candidates: list[str | tuple[str, str]] | None = None) -> list[dict[str, Any]]:
    """How much of the left side a candidate key can actually reach.

    Cardinality is the question people ask about a join and coverage is the one
    that decides the study. The Indonesian panel joined to the Refinitiv spine on
    `yahoo_symbol` matches 50 of 635 symbols. An inner join there turns a
    635-stock panel into a 50-large-cap panel, which is a different research
    question rather than a smaller one, and nothing in the join itself says so.

    A candidate is a shared column name, or a (left, right) pair when the sides
    name the same identity differently — the engine already takes left_on and
    right_on, so a same-name-only check would miss every cross-named link.

    Only the key columns are read, so the cost is a column per side per candidate.
    """
    import pyarrow.parquet as pq

    left = pq.ParquetFile(str(left_path))
    right = pq.ParquetFile(str(right_path))
    left_names, right_names = left.schema_arrow.names, right.schema_arrow.names
    if candidates is None:
        candidates = [n for n in left_names if n in right_names]
    out: list[dict[str, Any]] = []
    for candidate in candidates:
        lk, rk = candidate if isinstance(candidate, tuple) else (candidate, candidate)
        row: dict[str, Any] = {"left_key": lk, "right_key": rk, "usable": False,
                               "left_distinct": None, "right_distinct": None,
                               "right_duplicate_rows": None, "matched": None,
                               "left_matched_rows": None, "inner_join_rows": None,
                               "fanout_multiplier": None,
                               "match_rate_pct": None, "reason": None}
        if lk not in left_names or rk not in right_names:
            row["reason"] = "not present on both sides"
            out.append(row)
            continue
        left_values = left.read(columns=[lk]).column(lk).to_pylist()
        right_values = right.read(columns=[rk]).column(rk).to_pylist()
        left_list = [v for v in left_values if v is not None]
        right_list = [v for v in right_values if v is not None]
        left_counts = Counter(left_list)
        right_counts = Counter(right_list)
        left_keys = set(left_counts)
        right_keys = set(right_counts)
        del left_values, right_values
        matched_keys = left_keys & right_keys
        matched = len(matched_keys)
        total = len(left_keys)
        left_matched_rows = sum(left_counts[key] for key in matched_keys)
        inner_join_rows = sum(left_counts[key] * right_counts[key] for key in matched_keys)
        row.update({
            "usable": bool(right_keys),
            "left_distinct": total,
            "right_distinct": len(right_keys),
            "right_duplicate_rows": len(right_list) - len(right_keys),
            "matched": matched,
            "left_matched_rows": left_matched_rows,
            "inner_join_rows": inner_join_rows,
            "fanout_multiplier": round(inner_join_rows / left_matched_rows, 3) if left_matched_rows else 0.0,
            "match_rate_pct": round(100 * matched / total, 3) if total else 0.0,
        })
        if not right_keys:
            row["reason"] = "the column is empty on the right side"
        elif matched == 0:
            row["reason"] = "no value in common"
        out.append(row)
    out.sort(key=lambda r: (-(r["match_rate_pct"] or 0), r["left_key"]))
    return out
