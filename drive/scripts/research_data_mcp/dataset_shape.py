#!/usr/bin/env python3
"""Measured shape of a held dataset — L0 hands, no MCP required.

MCP tools exist so the model can call handlers. The desk can call them
in-process, and it must: the headless desk runs cloud Composer agents, which
cannot reach a stdio MCP server on this machine. Left to itself the model
answers row counts and date extents from priors.

Querying is measurement, not judgment, so it belongs to the hands.
"""

from __future__ import annotations

import logging
from typing import Any

_LOG = logging.getLogger(__name__)

PROFILE_LIMIT = 3
_CACHE: dict[str, dict[str, Any]] = {}


def _time_field(spec: dict[str, Any]) -> str:
    return str(spec.get("time_field") or "").strip()


def _parquet_footer(path: str, time_field: str = "") -> dict[str, Any]:
    """Row count and time extent from parquet metadata — footer only, no scan."""
    out: dict[str, Any] = {"row_count": None, "earliest": None, "latest": None}
    try:
        import pyarrow.parquet as pq
    except ImportError:
        return out
    try:
        pf = pq.ParquetFile(path)
    except Exception:  # noqa: BLE001
        return out
    md = pf.metadata
    if md is None:
        return out
    out["row_count"] = int(md.num_rows)
    if not time_field:
        return out
    try:
        idx = pf.schema_arrow.get_field_index(time_field)
    except Exception:  # noqa: BLE001
        idx = -1
    if idx < 0:
        return out
    lo: Any = None
    hi: Any = None
    for group in range(md.num_row_groups):
        stats = md.row_group(group).column(idx).statistics
        if stats is None or not stats.has_min_max:
            continue
        lo = stats.min if lo is None or stats.min < lo else lo
        hi = stats.max if hi is None or stats.max > hi else hi
    if lo is not None:
        out["earliest"] = str(lo)[:32]
    if hi is not None:
        out["latest"] = str(hi)[:32]
    return out


def measure_shape(gateway: Any, dataset_id: str, spec: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Row count, column names and observed time extent for one held dataset."""
    did = str(dataset_id or "").strip()
    if not did:
        return None
    if did in _CACHE:
        return _CACHE[did]
    try:
        head = gateway.query_dataset(did, {"limit": 1})
    except Exception:  # noqa: BLE001 - a shape probe must never fail a search
        _LOG.debug("shape probe failed for %s", did, exc_info=True)
        return None
    if not isinstance(head, dict):
        return None

    meta = head.get("meta") if isinstance(head.get("meta"), dict) else {}
    rows = head.get("rows") if isinstance(head.get("rows"), list) else []
    columns = sorted(rows[0].keys()) if rows and isinstance(rows[0], dict) else []

    total = meta.get("total_rows")
    if total is None:
        total = meta.get("row_count")
    try:
        total = int(total) if total is not None else None
    except (TypeError, ValueError):
        total = None

    out: dict[str, Any] = {
        "dataset_id": did,
        "row_count": total,
        "columns": columns[:12],
        "column_count": len(columns) or None,
    }

    # Preview-mode datasets return meta.mode=local_sample and ignore ordering, so
    # edge queries would report the head twice. Parquet keeps its row count and
    # per-column min/max in the footer — O(1), no scan.
    field = _time_field(spec or {})
    source = str(meta.get("source_path") or "")
    if source.lower().endswith(".parquet"):
        stats = _parquet_footer(source, field)
        out.update({k: v for k, v in stats.items() if v is not None})

    if not any(out.get(k) is not None for k in ("row_count", "column_count", "earliest", "latest")):
        return None
    _CACHE[did] = out
    return out


def shape_facts_lines(gateway: Any, held: list[dict[str, Any]], registry: dict[str, Any] | None = None) -> list[str]:
    """One measured line per query-ready held dataset, newest measurement wins."""
    registry = registry or {}
    lines: list[str] = []
    for row in held[:PROFILE_LIMIT]:
        if not isinstance(row, dict):
            continue
        did = str(row.get("dataset_id") or "").strip()
        if not did or not row.get("local_ready"):
            continue
        shape = measure_shape(gateway, did, registry.get(did) or {})
        if not shape:
            continue
        parts: list[str] = []
        if shape.get("row_count") is not None:
            parts.append(f"{shape['row_count']:,} rows")
        if shape.get("column_count"):
            parts.append(f"{shape['column_count']} columns")
        if shape.get("earliest") and shape.get("latest"):
            parts.append(f"{shape['earliest']} to {shape['latest']}")
        elif shape.get("earliest"):
            parts.append(f"from {shape['earliest']}")
        if parts:
            lines.append(f"- {did}: {' · '.join(parts)} (measured)")
    return lines


def reset_cache() -> None:
    _CACHE.clear()
