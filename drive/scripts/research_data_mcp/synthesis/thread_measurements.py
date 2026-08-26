"""Read-only measurements from mapped Synthesis evidence bytes."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from scripts.research_data_mcp.synthesis.data_profile import profile_columns
from scripts.research_data_mcp.synthesis.dataset_paths import resolve_dataset_file
from scripts.research_data_mcp.synthesis.multi_probe import probe_many
from scripts.research_data_mcp.synthesis.pair_probe import probe_pair

MAX_INPUTS = 8
KEYISH = re.compile(r"(?:^|_)(?:id|symbol|ticker|ric|isin|cusip|permno|gvkey|date|week|month|year)(?:_|$)", re.I)


def _mapped(thread: dict[str, Any]) -> list[dict[str, Any]]:
    state = thread.get("state") or {}
    out, seen = [], set()
    for node in state.get("nodes") or []:
        if not isinstance(node, dict):
            continue
        if node.get("layer") != "evidence" and node.get("type") not in {"source", "construct"}:
            continue
        dataset_id = str(node.get("dataset_id") or node.get("registered_dataset_id") or "").strip()
        if dataset_id and dataset_id not in seen:
            seen.add(dataset_id)
            out.append({**node, "dataset_id": dataset_id})
    return out


def _registry(repo_root: Path) -> dict[str, dict[str, Any]]:
    payload = json.loads((repo_root / "config/research_query_registry.json").read_text(encoding="utf-8"))
    return {str(row["dataset_id"]): row for row in payload.get("datasets") or [] if row.get("dataset_id")}


def _shared_keys(left: list[dict[str, Any]], right: list[dict[str, Any]]) -> list[str]:
    lmap = {str(row.get("column")): row for row in left if row.get("column")}
    rset = {str(row.get("column")) for row in right if row.get("column")}
    common = [name for name in lmap if name in rset]
    common.sort(key=lambda name: (0 if KEYISH.search(name) else 1, -int(lmap[name].get("distinct") or 0), name))
    return common[:8]


def _candidate(probe: dict[str, Any], key: str) -> dict[str, Any]:
    error = str(probe.get("probe_error") or "").strip()
    right_rows = int(probe.get("right_rows") or 0)
    right_distinct = int(probe.get("right_distinct") or 0)
    matched = int(probe.get("shared_distinct") or 0)
    usable = not error and right_distinct > 0
    reason = error or ("the column is empty on the right side" if not right_distinct else None)
    if usable and not matched:
        reason = "no value in common"
    return {
        "left_key": key, "right_key": key,
        "matched": matched,
        "left_distinct": int(probe.get("left_distinct") or 0),
        "right_distinct": right_distinct,
        "right_duplicate_rows": max(right_rows - right_distinct, 0),
        "match_rate_pct": float(probe.get("coverage_left_pct") or 0),
        "usable": usable, "reason": reason,
    }


def measure_thread(repo_root: Path | str, thread: dict[str, Any], *, max_inputs: int = MAX_INPUTS) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    limit = max(1, min(int(max_inputs or MAX_INPUTS), MAX_INPUTS))
    nodes = _mapped(thread)
    selected = nodes[:limit]
    registry = _registry(root)
    measured, unmeasured = [], []

    for node in selected:
        dataset_id = node["dataset_id"]
        source = registry.get(dataset_id)
        if not source:
            unmeasured.append({"dataset_id": dataset_id, "reason": "dataset is not registered"})
            continue
        path, reason = resolve_dataset_file(root, source)
        if path is None:
            unmeasured.append({"dataset_id": dataset_id, "reason": reason or "dataset bytes unresolved"})
            continue
        try:
            profiles = [{**row, "dataset_id": dataset_id} for row in profile_columns(path)]
        except Exception as exc:
            unmeasured.append({"dataset_id": dataset_id, "reason": str(exc)[:500]})
            continue
        measured.append({
            "dataset_id": dataset_id,
            "label": str(node.get("label") or source.get("title") or dataset_id),
            "path": path,
            "profiles": profiles,
            "rows": max((int(row.get("rows") or 0) for row in profiles), default=0),
        })

    joins = []
    join_reason = ""
    if len(measured) >= 2:
        left, right = measured[:2]
        for key in _shared_keys(left["profiles"], right["profiles"]):
            joins.append(_candidate(probe_pair(left["path"], right["path"], key), key))
        joins.sort(key=lambda row: (-(row["match_rate_pct"] or 0), row["left_key"]))
        if not joins:
            join_reason = "the first two measured inputs expose no shared candidate key"
    elif selected:
        join_reason = "at least two measured inputs are required for join coverage"

    multi = None
    if len(measured) >= 3:
        common = set(row["column"] for row in measured[0]["profiles"])
        for source in measured[1:]:
            common &= {row["column"] for row in source["profiles"]}
        ranked = sorted(common, key=lambda name: (0 if KEYISH.search(name) else 1, name))
        if ranked:
            multi = probe_many(
                [{"dataset_id": row["dataset_id"], "label": row["label"], "path": row["path"]} for row in measured],
                ranked[0],
            )
        else:
            multi = {"applicable": False, "source_count": len(measured), "probe_error": "no common key across measured inputs"}

    return {
        "thread_id": thread.get("id"), "writes": False,
        "measurement_basis": "mapped_library_bytes",
        "input_dataset_ids": [row["dataset_id"] for row in selected],
        "measured_inputs": len(measured),
        "unmeasured": unmeasured,
        "column_profiles": measured[0]["profiles"] if measured else [],
        "column_profiles_by_dataset": {row["dataset_id"]: row["profiles"] for row in measured},
        "input_measurements": [{"dataset_id": row["dataset_id"], "label": row["label"], "rows": row["rows"], "columns": len(row["profiles"])} for row in measured],
        "join_candidates": joins,
        "join_candidate_dataset_id": measured[1]["dataset_id"] if len(measured) >= 2 else "",
        "join_candidate_rows": measured[1]["rows"] if len(measured) >= 2 else 0,
        "join_unmeasured_because": join_reason,
        "multi_overlap": multi,
        "truncated_inputs": max(len(nodes) - len(selected), 0), "max_inputs": limit,
        "note": "Read-only measurements from resolved Library bytes; no assistant or thread mutation.",
    }
