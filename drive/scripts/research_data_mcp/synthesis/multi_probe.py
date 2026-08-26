"""Bounded, honest multi-source key overlap for Synthesis.

Pairwise coverage cannot recover a triple intersection. This probe reads the
actual join-key bytes for 2..8 registered inputs and counts exclusive membership
patterns directly. It is intentionally read-only: no artifact, job, registry
entry, or materialisation is created.

Large sources are bounded per input. When a cap is reached the receipt says so;
callers must describe the result as a bounded overlap window rather than a
full-population fact. The bounded window is deterministic, not a representative
random sample.
"""

from __future__ import annotations

from typing import Any

from scripts.research_data_mcp.synthesis.pair_probe import _read_key_column

MAX_SOURCES = 8
DEFAULT_ROW_CAP_PER_SOURCE = 500_000


def _keys(key: str | list[str]) -> list[str]:
    raw = [key] if isinstance(key, str) else list(key or [])
    return [str(value).strip() for value in raw if str(value).strip()]


def probe_many(
    sources: list[dict[str, Any]],
    key: str | list[str],
    *,
    row_cap_per_source: int = DEFAULT_ROW_CAP_PER_SOURCE,
) -> dict[str, Any]:
    """Measure exclusive key intersections across 2..8 real dataset paths.

    ``intersections`` are exclusive membership regions: mask 0b101 means a key
    is present in sources 0 and 2 and absent from every other measured source.
    Those counts are sufficient for a true 3-set Venn and for an UpSet plot at
    4+ sets.

    Any read error invalidates the whole overlap measurement, even if the reader
    collected values first. Partial source bytes cannot support an exact-looking
    higher-order intersection.
    """
    rows = [dict(source or {}) for source in (sources or [])]
    key_parts = _keys(key)
    cap = max(1, min(int(row_cap_per_source or DEFAULT_ROW_CAP_PER_SOURCE), 2_000_000))
    out: dict[str, Any] = {
        "applicable": False,
        "key": key if isinstance(key, str) else list(key_parts),
        "key_parts": key_parts,
        "source_count": len(rows),
        "row_cap_per_source": cap,
        "bounded": False,
        "sources": [],
        "union_distinct": 0,
        "all_shared_distinct": 0,
        "intersections": [],
        "pairwise": [],
        "probe_error": None,
    }
    if len(rows) < 2:
        out["probe_error"] = "multi-source overlap requires at least two sources"
        return out
    if len(rows) > MAX_SOURCES:
        out["probe_error"] = f"multi-source overlap is limited to {MAX_SOURCES} sources"
        return out
    if not key_parts:
        out["probe_error"] = "no common join key supplied"
        return out

    sets: list[set[Any]] = []
    for index, source in enumerate(rows):
        dataset_id = str(source.get("dataset_id") or source.get("id") or f"source_{index + 1}")
        label = str(source.get("label") or dataset_id)
        path = source.get("path")
        values, error = _read_key_column(path, key_parts, cap) if path else ([], "unresolved dataset path")
        if error:
            out["probe_error"] = f"{dataset_id}: {error}"
            return out
        distinct = set(values)
        # _read_key_column stops exactly at the non-null key cap. It cannot cheaply
        # know whether a CSV has one more valid key row, so equality is
        # conservatively treated as potentially truncated rather than overstated
        # as population-complete.
        truncated = len(values) >= cap
        out["bounded"] = bool(out["bounded"] or truncated)
        out["sources"].append(
            {
                "index": index,
                "dataset_id": dataset_id,
                "label": label,
                "rows_read": len(values),
                "distinct": len(distinct),
                "truncated": truncated,
                "read_warning": None,
            }
        )
        sets.append(distinct)

    union = set().union(*sets)
    counts: dict[int, int] = {}
    for value in union:
        mask = 0
        for index, values in enumerate(sets):
            if value in values:
                mask |= 1 << index
        if mask:
            counts[mask] = counts.get(mask, 0) + 1

    all_mask = (1 << len(sets)) - 1
    intersections = []
    for mask, count in counts.items():
        indexes = [index for index in range(len(sets)) if mask & (1 << index)]
        intersections.append(
            {
                "mask": mask,
                "source_indexes": indexes,
                "dataset_ids": [out["sources"][index]["dataset_id"] for index in indexes],
                "order": len(indexes),
                "count": count,
                "percent_of_union": round(100 * count / len(union), 3) if union else 0.0,
            }
        )
    intersections.sort(key=lambda row: (-int(row["count"]), -int(row["order"]), int(row["mask"])))

    pairwise = []
    for left in range(len(sets)):
        for right in range(left + 1, len(sets)):
            shared = len(sets[left] & sets[right])
            pairwise.append(
                {
                    "left_index": left,
                    "right_index": right,
                    "left_dataset_id": out["sources"][left]["dataset_id"],
                    "right_dataset_id": out["sources"][right]["dataset_id"],
                    "shared_distinct": shared,
                    "coverage_left_pct": round(100 * shared / len(sets[left]), 3) if sets[left] else 0.0,
                    "coverage_right_pct": round(100 * shared / len(sets[right]), 3) if sets[right] else 0.0,
                }
            )

    out.update(
        {
            "applicable": True,
            "union_distinct": len(union),
            "all_shared_distinct": counts.get(all_mask, 0),
            "intersections": intersections,
            "pairwise": pairwise,
            "exact_for_read_window": True,
            "note": (
                "Bounded key-overlap window; one or more sources reached the read cap. "
                "This deterministic window is not a representative sample."
                if out["bounded"]
                else "Exact key overlap for the resolved input bytes."
            ),
        }
    )
    return out
