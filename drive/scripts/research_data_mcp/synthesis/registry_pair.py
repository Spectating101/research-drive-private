"""Registry dataset pair synthesis — metadata overlap + optional entity join."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


def _normalize_keys(keys: list[str] | None) -> set[str]:
    return {str(k).strip().lower() for k in (keys or []) if str(k).strip()}


def _registry_key_sets(row: dict[str, Any]) -> tuple[set[str], set[str], str]:
    join_keys = _normalize_keys(row.get("join_keys"))
    entity_fields = _normalize_keys(row.get("entity_fields"))
    grain = str(row.get("grain") or "").strip().lower()
    union = join_keys | entity_fields
    return join_keys, union, grain


def metadata_overlap(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    join_a, union_a, grain_a = _registry_key_sets(left)
    join_b, union_b, grain_b = _registry_key_sets(right)
    shared_join = sorted(join_a & join_b)
    shared_union = sorted(union_a & union_b)
    only_left = sorted(union_a - union_b)
    only_right = sorted(union_b - union_a)
    union_size = len(union_a | union_b)
    key_pct = round(100 * len(shared_union) / union_size, 1) if union_size else 0.0
    grain_match = bool(grain_a and grain_a == grain_b)
    overlap_pct = key_pct if not grain_match else max(key_pct, 35.0)

    return {
        "left_dataset_id": left.get("dataset_id"),
        "right_dataset_id": right.get("dataset_id"),
        "left_title": left.get("name") or left.get("dataset_id"),
        "right_title": right.get("name") or right.get("dataset_id"),
        "shared_join_keys": shared_join,
        "shared_fields": shared_union,
        "only_left_fields": only_left,
        "only_right_fields": only_right,
        "grain_left": grain_a or None,
        "grain_right": grain_b or None,
        "grain_match": grain_match,
        "overlap_pct": overlap_pct,
        "synthesis_viable": bool(shared_join or (grain_match and shared_union)),
        "recommended_join": " · ".join(shared_join) if shared_join else ("grain:" + grain_a if grain_match else "partial"),
        "note": (
            "Metadata-only synthesis — row-level join requires matching local panels or a dedicated profile."
            if not shared_join
            else "Use shared join keys for entity-level merge when both datasets expose local rows."
        ),
    }


def run_registry_pair(
    repo_root: Path,
    left_id: str,
    right_id: str,
    *,
    describe_fn: Callable[[str], dict[str, Any]],
) -> dict[str, Any]:
    left = describe_fn(left_id)
    right = describe_fn(right_id)
    overlap = metadata_overlap(left, right)

    suggested_profiles: list[str] = []
    ids = {left_id, right_id}
    if "skynet_stablecoin_harvest" in ids or any("etherscan" in str(x).lower() for x in ids):
        suggested_profiles.append("skynet_etherscan_stablecoin")

    return {
        "profile_id": f"pair:{left_id}:{right_id}",
        "title": f"Synthesis · {overlap['left_title']} × {overlap['right_title']}",
        "type": "registry_pair",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            **overlap,
            "type": "registry_pair",
            "both_count": None,
            "left_only_count": None,
            "right_only_count": None,
        },
        "left": {
            "dataset_id": left_id,
            "grain": left.get("grain"),
            "readiness": left.get("analysis_readiness"),
            "local_path": left.get("local_path"),
            "join_keys": left.get("join_keys") or [],
        },
        "right": {
            "dataset_id": right_id,
            "grain": right.get("grain"),
            "readiness": right.get("analysis_readiness"),
            "local_path": right.get("local_path"),
            "join_keys": right.get("join_keys") or [],
        },
        "insights": [
            {
                "kind": "metadata_overlap",
                "overlap_pct": overlap["overlap_pct"],
                "grain_match": overlap["grain_match"],
                "recommended_join": overlap["recommended_join"],
            }
        ],
        "suggested_profiles": suggested_profiles,
        "research_questions": [
            f"Which entities appear in both {left_id} and {right_id} on {overlap['recommended_join']}?",
            "What fields exist in one catalog entry but not the other (procurement gap)?",
        ],
        "artifacts": {},
        "repo_root": str(repo_root),
    }
