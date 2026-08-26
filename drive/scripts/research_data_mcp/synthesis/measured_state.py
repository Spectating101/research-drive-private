#!/usr/bin/env python3
"""The parts of a Synthesis method surface that are measured, not reasoned.

Column profiles, unit conflicts, join coverage, and higher-order key overlap are
facts about held bytes. They remain available while the reasoning provider is
down and they never recommend a methodological choice.

The important boundary here is identity. A generic numeric measurement can have
excellent apparent value overlap with another dataset while being nonsense as a
join key. Shared identity/time/key-like fields therefore outrank arbitrary
measurements whenever such a domain exists. When an entity and a time dimension
are both shared, the composite panel key is measured before either partial key so
coverage cannot silently collapse an entity-period panel to entity-only identity.
"""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any

# synthesisContract.js validates exactly these keys on a column profile.
_PROFILE_KEYS = ("column", "kind", "rows", "blanks", "distinct", "flags")
MAX_INPUTS = 8
ENTITY_KEYISH = re.compile(
    r"(?:^|_)(?:id|entity|symbol|ticker|ric|isin|cusip|permno|gvkey)(?:_|$)",
    re.I,
)
TIME_KEYISH = re.compile(
    r"(?:^|_)(?:date|day|week|month|quarter|year|period|timestamp|time)(?:_|$)",
    re.I,
)
KEYISH = re.compile(
    r"(?:^|_)(?:id|entity|symbol|ticker|ric|isin|cusip|permno|gvkey|date|day|week|month|quarter|year|period|timestamp|time)(?:_|$)",
    re.I,
)


def _dataset_file(gateway: Any, dataset_id: str) -> tuple[Path | None, str]:
    from scripts.research_data_mcp.synthesis.dataset_paths import resolve_dataset_file

    try:
        spec = gateway.describe_dataset(dataset_id) or {}
    except Exception as exc:
        return None, f"registry read failed: {type(exc).__name__}"
    path, why = resolve_dataset_file(gateway.repo_root, spec)
    return path, ("" if path else str(why or "no reachable bytes"))


def _contract_profile(row: dict[str, Any]) -> dict[str, Any]:
    out = {k: row.get(k) for k in _PROFILE_KEYS}
    out["flags"] = list(row.get("flags") or [])
    return out


def profiles_for(gateway: Any, dataset_id: str) -> dict[str, Any]:
    """Column profiles for one mapped input, plus its resolved path when usable."""
    from scripts.research_data_mcp.synthesis.data_profile import profile_columns

    path, why = _dataset_file(gateway, dataset_id)
    if not path:
        return {
            "dataset_id": dataset_id,
            "column_profiles": [],
            "unmeasured_because": why,
            "path": None,
        }
    try:
        rows = profile_columns(path)
    except Exception as exc:
        return {
            "dataset_id": dataset_id,
            "column_profiles": [],
            "unmeasured_because": f"could not read {path.suffix or 'file'}: {type(exc).__name__}",
            "path": path,
        }
    return {
        "dataset_id": dataset_id,
        "column_profiles": [_contract_profile(r) for r in rows],
        "unmeasured_because": "",
        "_raw": rows,
        "path": path,
    }


def unit_conflict_from(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Two columns of the same cardinality whose magnitudes disagree ~100x."""
    twins = [r for r in rows if "unit_twin" in (r.get("flags") or []) and r.get("twin_of")]
    if not twins:
        return None
    left = twins[0]
    right = next((r for r in rows if r.get("column") == left.get("twin_of")), None)
    if not right:
        return None
    lm = float(left.get("typical_magnitude") or 0)
    rm = float(right.get("typical_magnitude") or 0)
    if not lm or not rm:
        return None
    ratio = max(lm, rm) / min(lm, rm)
    return {
        "left": {"column": left["column"], "typical": lm},
        "right": {"column": right["column"], "typical": rm},
        "outcomes": [
            {"id": "as_is", "label": "Combine as recorded", "result": None, "recommended": False},
            {"id": "rescale", "label": f"Rescale by {round(ratio):g}x first", "result": None, "recommended": False},
        ],
        "measured_ratio": round(ratio, 1),
        "undecided_because": "the desk cannot tell which series is correct, only that they cannot both be",
    }


def _rank_common_columns(
    left: list[dict[str, Any]], right: list[dict[str, Any]]
) -> list[str]:
    lmap = {str(row.get("column")): row for row in left if row.get("column")}
    rset = {str(row.get("column")) for row in right if row.get("column")}
    common = [name for name in lmap if name in rset]
    common.sort(
        key=lambda name: (
            0 if KEYISH.search(name) else 1,
            -int(lmap[name].get("distinct") or 0),
            name,
        )
    )
    keyish = [name for name in common if KEYISH.search(name)]
    return keyish or common


def _shared_key_specs(
    left: list[dict[str, Any]], right: list[dict[str, Any]]
) -> list[list[str]]:
    """Return measured key domains, preserving entity × time panel grain first."""
    ranked = _rank_common_columns(left, right)
    entity = next((name for name in ranked if ENTITY_KEYISH.search(name)), "")
    period = next((name for name in ranked if TIME_KEYISH.search(name)), "")

    specs: list[list[str]] = []
    if entity and period and entity != period:
        specs.append([entity, period])
    specs.extend([[name] for name in ranked])

    unique: list[list[str]] = []
    seen: set[tuple[str, ...]] = set()
    for spec in specs:
        identity = tuple(spec)
        if not identity or identity in seen:
            continue
        seen.add(identity)
        unique.append(spec)
        if len(unique) >= 8:
            break
    return unique


def _is_complete_identity_domain(key_parts: list[str]) -> bool:
    return (
        len(key_parts) > 1
        and any(ENTITY_KEYISH.search(name) for name in key_parts)
        and any(TIME_KEYISH.search(name) for name in key_parts)
    )


def _key_label(key_parts: list[str]) -> str:
    return " + ".join(key_parts)


def _candidate_from_probe(probe: dict[str, Any], key: str | list[str]) -> dict[str, Any]:
    key_parts = [str(key)] if isinstance(key, str) else [str(part) for part in key]
    key_parts = [part for part in key_parts if part.strip()]
    label = _key_label(key_parts)
    error = str(probe.get("probe_error") or "").strip()
    right_rows = int(probe.get("right_rows") or 0)
    right_distinct = int(probe.get("right_distinct") or 0)
    matched = int(probe.get("shared_distinct") or 0)
    usable = not error and right_distinct > 0
    reason = error or ("the key is empty on the right side" if not right_distinct else None)
    if usable and not matched:
        reason = "no value in common"
    return {
        "left_key": label,
        "right_key": label,
        "key_parts": key_parts,
        "complete_identity_domain": _is_complete_identity_domain(key_parts),
        "matched": matched,
        "left_distinct": int(probe.get("left_distinct") or 0),
        "right_distinct": right_distinct,
        "right_duplicate_rows": max(right_rows - right_distinct, 0),
        "match_rate_pct": float(probe.get("coverage_left_pct") or 0),
        "usable": usable,
        "reason": reason,
    }


def _join_candidates(left: dict[str, Any], right: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    from scripts.research_data_mcp.synthesis.pair_probe import probe_pair

    candidates = []
    for key_parts in _shared_key_specs(left["raw"], right["raw"]):
        candidates.append(
            _candidate_from_probe(
                probe_pair(
                    left["path"],
                    right["path"],
                    key_parts,
                    left_id=left["dataset_id"],
                    right_id=right["dataset_id"],
                ),
                key_parts,
            )
        )
    candidates.sort(
        key=lambda row: (
            0 if row["usable"] else 1,
            0 if row["complete_identity_domain"] else 1,
            -(row["match_rate_pct"] or 0),
            row["left_key"],
        )
    )
    reason = "" if candidates else "the first two measured inputs expose no shared candidate key"
    return candidates, reason


def _common_multi_key_parts(measured: list[dict[str, Any]]) -> list[str]:
    if len(measured) < 3:
        return []
    common = {str(row.get("column")) for row in measured[0]["raw"] if row.get("column")}
    for source in measured[1:]:
        common &= {str(row.get("column")) for row in source["raw"] if row.get("column")}
    ranked = sorted(common, key=lambda name: (0 if KEYISH.search(name) else 1, name))
    keyish = [name for name in ranked if KEYISH.search(name)]
    ranked = keyish or ranked
    entity = next((name for name in ranked if ENTITY_KEYISH.search(name)), "")
    period = next((name for name in ranked if TIME_KEYISH.search(name)), "")
    if entity and period and entity != period:
        return [entity, period]
    return [ranked[0]] if ranked else []


def _unique_dataset_ids(nodes: list[dict[str, Any]]) -> list[str]:
    """Preserve mapping order while refusing duplicate evidence as fake sources."""
    out: list[str] = []
    seen: set[str] = set()
    for node in nodes:
        dataset_id = str(node.get("dataset_id") or "").strip()
        if not dataset_id or dataset_id in seen:
            continue
        seen.add(dataset_id)
        out.append(dataset_id)
    return out


def measured_state(gateway: Any, nodes: list[dict[str, Any]], *, max_inputs: int = MAX_INPUTS) -> dict[str, Any]:
    """Everything mapped evidence can state from bytes without a model.

    Up to eight unique inputs are measured. Inputs whose bytes are unreachable
    are named explicitly rather than silently omitted. Higher-order overlap is
    computed only from successfully measured inputs sharing one real key domain.
    """
    all_nodes = [n for n in (nodes or []) if isinstance(n, dict)]
    all_ids = _unique_dataset_ids(all_nodes)
    limit = max(1, min(int(max_inputs or MAX_INPUTS), MAX_INPUTS))
    selected_ids = all_ids[:limit]
    selected_nodes = []
    remaining = list(selected_ids)
    for node in all_nodes:
        dataset_id = str(node.get("dataset_id") or "").strip()
        if dataset_id and dataset_id in remaining:
            selected_nodes.append(node)
            remaining.remove(dataset_id)
        if not remaining:
            break

    if not selected_ids:
        return {
            "column_profiles": [],
            "column_profiles_by_dataset": {},
            "input_measurements": [],
            "unmeasured": [],
            "measured_inputs": 0,
            "multi_overlap": None,
            "reason": "no mapped evidence to measure",
            "needs_model": False,
            "truncated_inputs": 0,
            "max_inputs": limit,
        }

    profiles: list[dict[str, Any]] = []
    profiles_by_dataset: dict[str, list[dict[str, Any]]] = {}
    unmeasured: list[dict[str, str]] = []
    measured: list[dict[str, Any]] = []
    conflict: dict[str, Any] | None = None

    label_by_id = {
        str(node.get("dataset_id") or "").strip(): str(
            node.get("label") or node.get("dataset_id") or ""
        )
        for node in selected_nodes
        if str(node.get("dataset_id") or "").strip()
    }

    for dataset_id in selected_ids:
        got = profiles_for(gateway, dataset_id)
        if got["unmeasured_because"]:
            unmeasured.append({"dataset_id": dataset_id, "reason": got["unmeasured_because"]})
            continue
        contract_rows = [
            {**row, "dataset_id": dataset_id} for row in got["column_profiles"]
        ]
        profiles.extend(contract_rows)
        profiles_by_dataset[dataset_id] = contract_rows
        raw = list(got.get("_raw") or [])
        rows = max((int(row.get("rows") or 0) for row in raw), default=0)
        measured.append(
            {
                "dataset_id": dataset_id,
                "label": label_by_id.get(dataset_id) or dataset_id,
                "path": got["path"],
                "raw": raw,
                "rows": rows,
            }
        )
        if conflict is None:
            conflict = unit_conflict_from(raw)

    out: dict[str, Any] = {
        "column_profiles": profiles,
        "column_profiles_by_dataset": profiles_by_dataset,
        "input_measurements": [
            {
                "dataset_id": row["dataset_id"],
                "label": row["label"],
                "rows": row["rows"],
                "columns": len(row["raw"]),
            }
            for row in measured
        ],
        "unmeasured": unmeasured,
        "measured_inputs": len(measured),
        "reason": "",
        "needs_model": False,
        "truncated_inputs": max(len(all_ids) - len(selected_ids), 0),
        "max_inputs": limit,
    }
    if conflict:
        out["unit_conflict"] = conflict

    if len(measured) >= 2:
        candidates, join_reason = _join_candidates(measured[0], measured[1])
        out["join_candidates"] = candidates
        out["join_candidate_dataset_id"] = measured[1]["dataset_id"]
        out["join_candidate_rows"] = measured[1]["rows"]
        if join_reason:
            out["join_unmeasured_because"] = join_reason
    elif selected_ids:
        out["join_unmeasured_because"] = "at least two measured inputs are required for join coverage"

    multi = None
    if len(measured) >= 3:
        from scripts.research_data_mcp.synthesis.multi_probe import probe_many

        key_parts = _common_multi_key_parts(measured)
        if key_parts:
            multi = probe_many(
                [
                    {
                        "dataset_id": row["dataset_id"],
                        "label": row["label"],
                        "path": row["path"],
                    }
                    for row in measured
                ],
                key_parts,
            )
        else:
            multi = {
                "applicable": False,
                "source_count": len(measured),
                "probe_error": "no common key across measured inputs",
            }
    out["multi_overlap"] = multi
    return out
