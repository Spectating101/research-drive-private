#!/usr/bin/env python3
"""The parts of a Synthesis method surface that are measured, not reasoned.

Half that surface needs no model. column_profiles, unit_conflict and
join_candidates are facts about held bytes: how many rows a column has, whether
two columns about to be combined disagree in magnitude, how much of one dataset
a candidate key can actually reach. The reasoning provider being down blocks the
recommendation and the method; it does not block any of this.

The measurements already existed in data_profile.py and nothing called them.
This turns them into the fields synthesisContract.js validates, so the panels
can state real facts about a researcher's data before any model exists.

Nothing here recommends. A unit conflict reports both outcomes and picks
neither, because the desk cannot tell which series is correct — only that they
cannot both be. Choosing for the researcher there is how a plausible wrong
number reaches a paper.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

# synthesisContract.js validates exactly these keys on a column profile.
_PROFILE_KEYS = ("column", "kind", "rows", "blanks", "distinct", "flags")


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
    """column_profiles for one mapped input, or the reason there are none."""
    from scripts.research_data_mcp.synthesis.data_profile import profile_columns

    path, why = _dataset_file(gateway, dataset_id)
    if not path:
        return {"dataset_id": dataset_id, "column_profiles": [], "unmeasured_because": why}
    try:
        rows = profile_columns(path)
    except Exception as exc:
        return {
            "dataset_id": dataset_id,
            "column_profiles": [],
            "unmeasured_because": f"could not read {path.suffix or 'file'}: {type(exc).__name__}",
        }
    return {
        "dataset_id": dataset_id,
        "column_profiles": [_contract_profile(r) for r in rows],
        "unmeasured_because": "",
        "_raw": rows,
    }


def unit_conflict_from(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Two columns of the same cardinality whose magnitudes disagree ~100x.

    data_profile already flags these as unit twins. Subtracting a percentage
    from a fraction returns a plausible number and every statistic downstream
    inherits it, so this is one of the few things worth stopping a researcher
    for — and one of the few where the desk must not choose.
    """
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


def join_candidates_for(gateway: Any, left_id: str, right_id: str) -> dict[str, Any]:
    """How much of the left side a shared key actually reaches."""
    from scripts.research_data_mcp.synthesis.data_profile import join_coverage

    left, lwhy = _dataset_file(gateway, left_id)
    right, rwhy = _dataset_file(gateway, right_id)
    if not left or not right:
        return {"join_candidates": [], "unmeasured_because": lwhy or rwhy}
    try:
        rows = join_coverage(left, right)
    except Exception as exc:
        return {"join_candidates": [], "unmeasured_because": f"join probe failed: {type(exc).__name__}"}
    return {"join_candidates": list(rows or []), "unmeasured_because": ""}


def measured_state(gateway: Any, nodes: list[dict[str, Any]], *, max_inputs: int = 4) -> dict[str, Any]:
    """Everything a thread's mapped evidence can state without a model.

    A dataset whose bytes are unreachable is named with its reason rather than
    dropped: a method surface that silently profiles three of five inputs is
    worse than one that says which two it could not read.
    """
    ids = [str(n.get("dataset_id") or "").strip() for n in (nodes or [])]
    ids = [i for i in ids if i][:max_inputs]
    if not ids:
        return {"column_profiles": [], "unmeasured": [], "reason": "no mapped evidence to measure"}

    profiles: list[dict[str, Any]] = []
    unmeasured: list[dict[str, str]] = []
    conflict: dict[str, Any] | None = None
    for dataset_id in ids:
        got = profiles_for(gateway, dataset_id)
        if got["unmeasured_because"]:
            unmeasured.append({"dataset_id": dataset_id, "reason": got["unmeasured_because"]})
            continue
        for row in got["column_profiles"]:
            profiles.append({**row, "dataset_id": dataset_id})
        if conflict is None:
            conflict = unit_conflict_from(got.get("_raw") or [])

    out: dict[str, Any] = {
        "column_profiles": profiles,
        "unmeasured": unmeasured,
        "measured_inputs": len(ids) - len(unmeasured),
        "reason": "",
        "needs_model": False,
    }
    if conflict:
        out["unit_conflict"] = conflict
    if len(ids) >= 2 and len(unmeasured) == 0:
        joins = join_candidates_for(gateway, ids[0], ids[1])
        if joins["join_candidates"]:
            out["join_candidates"] = joins["join_candidates"]
        elif joins["unmeasured_because"]:
            out["join_unmeasured_because"] = joins["unmeasured_because"]
    return out
