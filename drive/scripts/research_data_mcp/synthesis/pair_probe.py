"""Measured key overlap between two registry datasets.

Reads the actual bytes. Reports what the keys really share and how each side is
shaped. It states no verdict: a threshold is a research judgement, not a probe
result. Callers decide what is good enough.

The row cap is an execution bound, not merely a result truncation. CSV inputs
are projected to the key columns and streamed in chunks; Parquet inputs are
projected and read in bounded record batches. Large research files therefore do
not need to be materialised in memory just to measure key overlap.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SUPPORTED_SUFFIXES = (".parquet", ".csv", ".csv.gz")
READ_BATCH_ROWS = 100_000


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _data_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path] if path.name.endswith(SUPPORTED_SUFFIXES) else []
    if not path.is_dir():
        return []
    found: list[Path] = []
    for suffix in SUPPORTED_SUFFIXES:
        found.extend(sorted(path.rglob(f"*{suffix}")))
    return found


def _append_frame_keys(frame: Any, cols: list[str], values: list[Any], row_cap: int) -> None:
    if len(values) >= row_cap:
        return
    subset = frame[cols].dropna().astype(str)
    take = row_cap - len(values)
    values.extend(map(tuple, subset.values[:take]))


def _read_key_column(path: Path, keys: list[str], row_cap: int) -> tuple[list[Any], str | None]:
    """Read the composite key as tuples under a real memory/result bound.

    A panel keyed on (symbol, week) probed on `symbol` alone reports a coverage
    that no real join achieves, so every key part must be present.
    """
    try:
        import pandas as pd
    except Exception as exc:  # pragma: no cover - environment guard
        return [], f"pandas unavailable: {exc}"

    files = _data_files(path)
    if not files:
        return [], f"no readable data file under {path}"

    cap = max(1, int(row_cap or 1))
    wanted = [k.strip().lower() for k in keys]
    values: list[Any] = []
    last_error: str | None = None
    matched = False

    for file_path in files:
        if len(values) >= cap:
            break
        try:
            if file_path.name.endswith(".parquet"):
                import pyarrow.parquet as pq

                parquet = pq.ParquetFile(file_path)
                available = {str(c).strip().lower(): c for c in parquet.schema.names}
                if any(k not in available for k in wanted):
                    continue
                matched = True
                cols = [available[k] for k in wanted]
                remaining = cap - len(values)
                batch_rows = max(1, min(READ_BATCH_ROWS, remaining))
                for batch in parquet.iter_batches(batch_size=batch_rows, columns=cols):
                    _append_frame_keys(batch.to_pandas(), cols, values, cap)
                    if len(values) >= cap:
                        break
            else:
                # Read only a zero-row header first so we can project the actual
                # key columns. Then stream chunks instead of loading a multi-GB
                # CSV merely to use a few hundred thousand key values.
                header = pd.read_csv(file_path, nrows=0)
                available = {str(c).strip().lower(): c for c in header.columns}
                if any(k not in available for k in wanted):
                    continue
                matched = True
                cols = [available[k] for k in wanted]
                remaining = cap - len(values)
                chunk_rows = max(1, min(READ_BATCH_ROWS, remaining))
                for frame in pd.read_csv(
                    file_path,
                    usecols=cols,
                    low_memory=False,
                    chunksize=chunk_rows,
                ):
                    _append_frame_keys(frame, cols, values, cap)
                    if len(values) >= cap:
                        break
        except Exception as exc:
            last_error = f"{file_path.name}: {exc}"
            continue

    if not matched:
        missing = ", ".join(repr(k) for k in keys)
        return [], f"key ({missing}) not fully present in any data file under {path}"
    return values, last_error


def _cardinality(rows: int, distinct: int) -> str:
    if not distinct:
        return "empty"
    return "1:1" if rows == distinct else "1:N"


def probe_pair(
    left_path: Path | str | None,
    right_path: Path | str | None,
    key: str | list[str],
    *,
    left_id: str | None = None,
    right_id: str | None = None,
    row_cap: int = 2_000_000,
) -> dict[str, Any]:
    """Intersect the real key values of two datasets.

    `key` may be a single column or the full composite key. Probing a partial key
    overstates joinability, so pass every part the join will use.

    Returns measured counts only. `probe_error` set means no number is trustworthy
    and callers must not fall back to declared metadata. A partial read is also an
    error: retaining values from earlier files and calling them measured coverage
    would turn an I/O failure into a plausible analytical result.
    """
    keys = [key] if isinstance(key, str) else [str(k) for k in (key or [])]
    keys = [k for k in keys if str(k).strip()]
    result: dict[str, Any] = {
        "left_dataset_id": left_id,
        "right_dataset_id": right_id,
        "key": key if isinstance(key, str) else list(keys),
        "key_parts": keys,
        "probed_at": _now(),
        "left_rows": 0,
        "right_rows": 0,
        "left_distinct": 0,
        "right_distinct": 0,
        "shared_distinct": 0,
        "coverage_left_pct": None,
        "coverage_right_pct": None,
        "left_cardinality": None,
        "right_cardinality": None,
        "collapse_required": None,
        "probe_error": None,
    }

    if not keys:
        result["probe_error"] = "no join key supplied"
        return result
    if not left_path or not right_path:
        result["probe_error"] = "unresolved dataset path"
        return result

    left_values, left_err = _read_key_column(Path(left_path), keys, row_cap)
    right_values, right_err = _read_key_column(Path(right_path), keys, row_cap)

    # Fail closed even when a reader managed to collect some values before the
    # error. Partial bytes are not a trustworthy denominator for join coverage.
    if left_err:
        result["probe_error"] = f"left: {left_err}"
        return result
    if right_err:
        result["probe_error"] = f"right: {right_err}"
        return result

    left_set = set(left_values)
    right_set = set(right_values)
    shared = left_set & right_set

    result["left_rows"] = len(left_values)
    result["right_rows"] = len(right_values)
    result["left_distinct"] = len(left_set)
    result["right_distinct"] = len(right_set)
    result["shared_distinct"] = len(shared)
    result["coverage_left_pct"] = round(100 * len(shared) / len(left_set), 1) if left_set else 0.0
    result["coverage_right_pct"] = round(100 * len(shared) / len(right_set), 1) if right_set else 0.0
    result["left_cardinality"] = _cardinality(len(left_values), len(left_set))
    result["right_cardinality"] = _cardinality(len(right_values), len(right_set))
    # Only a 1:N RIGHT side multiplies rows on merge. A 1:N left is the spine's own
    # grain and joining a 1:1 right onto it changes no row count.
    result["collapse_required"] = result["right_cardinality"] == "1:N"
    result["either_side_repeats"] = (
        result["left_cardinality"] == "1:N" or result["right_cardinality"] == "1:N"
    )
    return result


def probe_summary(probe: dict[str, Any]) -> str:
    """One researcher-facing line. Never asserts a verdict."""
    if probe.get("probe_error"):
        return f"Not probed — {probe['probe_error']}"
    shared = probe.get("shared_distinct") or 0
    right = probe.get("right_distinct") or 0
    pct = probe.get("coverage_right_pct")
    line = f"{shared} of {right} keys shared ({pct}% of the joining side)"
    if probe.get("collapse_required"):
        line += " · a side is 1:N, a collapse rule is required"
    return line
