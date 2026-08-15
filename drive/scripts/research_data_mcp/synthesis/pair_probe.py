"""Measured key overlap between two registry datasets.

Reads the actual bytes. Reports what the keys really share and how each side is
shaped. It states no verdict: a threshold is a research judgement, not a probe
result. Callers decide what is good enough.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SUPPORTED_SUFFIXES = (".parquet", ".csv", ".csv.gz")


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


def _read_key_column(path: Path, keys: list[str], row_cap: int) -> tuple[list[Any], str | None]:
    """Read the composite key as tuples.

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

    wanted = [k.strip().lower() for k in keys]
    values: list[Any] = []
    last_error: str | None = None
    matched = False
    for file_path in files:
        if len(values) >= row_cap:
            break
        try:
            if file_path.name.endswith(".parquet"):
                # Project only the key columns — a probe never needs the payload.
                import pyarrow.parquet as pq

                available = {str(c).strip().lower(): c for c in pq.ParquetFile(file_path).schema.names}
                if any(k not in available for k in wanted):
                    continue
                frame = pd.read_parquet(file_path, columns=[available[k] for k in wanted])
            else:
                frame = pd.read_csv(file_path, low_memory=False)
        except Exception as exc:
            last_error = f"{file_path.name}: {exc}"
            continue
        lower = {str(c).strip().lower(): c for c in frame.columns}
        if any(k not in lower for k in wanted):
            continue
        matched = True
        cols = [lower[k] for k in wanted]
        subset = frame[cols].dropna().astype(str)
        take = row_cap - len(values)
        values.extend(map(tuple, subset.values[:take]))

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
    and callers must not fall back to declared metadata.
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

    if left_err and not left_values:
        result["probe_error"] = f"left: {left_err}"
        return result
    if right_err and not right_values:
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
