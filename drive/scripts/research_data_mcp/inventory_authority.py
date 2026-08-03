#!/usr/bin/env python3
"""Canonical, versioned registry inventory projection.

Endpoints must embed this projection (or an explicit view_scope that points at it)
so UI layers cannot compare unrelated totals. Different views may legitimately use
different scopes — never collapse that by silently dropping filters.

Semantics preserved by contract:
  completed  → job lifecycle terminal (not a catalog count)
  registered → present in the registry authority (or verified receipt recovery)
  query_ready → materialization.query_ready proved queryable
  analysis_readiness → declared analysis posture on the registry card
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping

INVENTORY_SUMMARY_VERSION = 1

SCOPE_REGISTRY_ALL = "registry_all"
SCOPE_DESK_VISIBLE = "desk_visible"
SCOPE_SOURCE_MAPPED = "source_mapped"
SCOPE_RETURNED_WINDOW = "returned_window"

SCOPE_DESCRIPTIONS = {
    SCOPE_REGISTRY_ALL: (
        "All rows loaded from research_query_registry.json after in-memory "
        "runtime readiness reconciliation (does not mutate the registry file)."
    ),
    SCOPE_DESK_VISIBLE: (
        "Registry rows visible on the research desk — excludes operational/test "
        "cards (ops_status backends, fixture/test tags and ids)."
    ),
    SCOPE_SOURCE_MAPPED: (
        "Registry rows considered by the databank source-map audit "
        "(same registry revision; mapping filters are separate)."
    ),
    SCOPE_RETURNED_WINDOW: (
        "Rows returned by this endpoint after its own filters/limits "
        "(may include receipt recovery and may truncate)."
    ),
}


def registry_revision(registry_path: Path) -> dict[str, Any]:
    """Content fingerprint + metadata for the registry authority file."""
    path = Path(registry_path)
    revision: dict[str, Any] = {
        "path": str(path),
        "fingerprint": None,
        "byte_size": None,
        "mtime_ns": None,
        "updated_at": None,
        "dataset_count_on_disk": None,
    }
    if not path.is_file():
        revision["error"] = "registry_missing"
        return revision
    raw = path.read_bytes()
    revision["byte_size"] = len(raw)
    revision["fingerprint"] = hashlib.sha256(raw).hexdigest()[:24]
    try:
        revision["mtime_ns"] = path.stat().st_mtime_ns
    except OSError:
        pass
    try:
        doc = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        revision["error"] = f"registry_unreadable:{exc}"
        return revision
    if isinstance(doc, dict):
        revision["updated_at"] = doc.get("updated_at")
        datasets = doc.get("datasets")
        if isinstance(datasets, list):
            revision["dataset_count_on_disk"] = len(datasets)
    return revision


def is_excluded_operational_or_test(dataset: Mapping[str, Any]) -> bool:
    """Operational status cards and test/fixture rows are registered but not desk inventory."""
    access_shape = str(dataset.get("access_shape") or "").strip().lower()
    backend = str(dataset.get("backend") or "").strip().lower()
    dataset_id = str(dataset.get("dataset_id") or "").strip().lower()
    tags = {str(tag).strip().lower() for tag in (dataset.get("tags") or []) if str(tag).strip()}

    if dataset.get("desk_exclude") is True or dataset.get("exclude_from_desk") is True:
        return True
    if access_shape == "ops_status":
        return True
    if backend.endswith("_status") or "ops_status" in backend:
        return True
    if "test" in tags or "fixture" in tags or "operational" in tags:
        return True
    if (
        dataset_id.startswith("test_")
        or dataset_id.endswith("_test")
        or "_test_" in dataset_id
        or "_fixture_" in dataset_id
        or dataset_id.startswith("fixture_")
    ):
        return True
    return False


def _query_ready_bucket(dataset: Mapping[str, Any]) -> str:
    materialization = dataset.get("materialization")
    if not isinstance(materialization, Mapping):
        return "unset"
    if "query_ready" not in materialization:
        return "unset"
    value = materialization.get("query_ready")
    if value is True:
        return "true"
    if value is False:
        return "false"
    return "unset"


def _partition_projection(repo_root: Path | None) -> dict[str, Any]:
    if repo_root is None:
        return {"total": 0, "complete": 0, "professor_visible": 0, "lanes": []}
    try:
        from scripts.yzu_cluster.partition_lanes import partition_lanes

        lanes = partition_lanes(Path(repo_root))
    except Exception as exc:  # pragma: no cover - defensive for partial fixtures
        return {"total": 0, "complete": 0, "professor_visible": 0, "error": str(exc), "lanes": []}
    return {
        "total": len(lanes),
        "complete": sum(1 for lane in lanes if lane.get("stage") == "complete"),
        "professor_visible": sum(1 for lane in lanes if lane.get("professor_visible") is not False),
        "lanes": [
            {
                "id": lane.get("id"),
                "name": lane.get("name"),
                "stage": lane.get("stage"),
                "registry_datasets": len((lane.get("detail") or {}).get("registry_dataset_ids") or []),
            }
            for lane in lanes
        ],
    }


def build_inventory_summary(
    datasets: Iterable[Mapping[str, Any]],
    *,
    registry_path: Path,
    repo_root: Path | None = None,
    include_partition_lanes: bool = True,
) -> dict[str, Any]:
    """Build the canonical inventory projection from reconciled registry rows."""
    rows = [dict(row) for row in datasets]
    excluded = [row for row in rows if is_excluded_operational_or_test(row)]
    visible = [row for row in rows if not is_excluded_operational_or_test(row)]

    readiness = Counter(str(row.get("analysis_readiness") or "") or "unset" for row in rows)
    visible_readiness = Counter(str(row.get("analysis_readiness") or "") or "unset" for row in visible)
    query_ready = Counter(_query_ready_bucket(row) for row in rows)
    visible_query_ready = Counter(_query_ready_bucket(row) for row in visible)

    revision = registry_revision(registry_path)
    partitions = (
        _partition_projection(repo_root)
        if include_partition_lanes
        else {"total": None, "complete": None, "professor_visible": None, "lanes": []}
    )

    return {
        "version": INVENTORY_SUMMARY_VERSION,
        "registry_revision": revision,
        "totals": {
            "registered": len(rows),
            "visible_to_desk": len(visible),
            "excluded_operational_test": len(excluded),
        },
        "excluded_operational_test_ids": sorted(
            str(row.get("dataset_id") or "") for row in excluded if row.get("dataset_id")
        ),
        "by_analysis_readiness": {
            "registered": dict(sorted(readiness.items())),
            "visible_to_desk": dict(sorted(visible_readiness.items())),
        },
        "by_materialization_query_ready": {
            "registered": dict(sorted(query_ready.items())),
            "visible_to_desk": dict(sorted(visible_query_ready.items())),
        },
        "partitions": partitions,
        "semantics": {
            "completed": "Job lifecycle terminal state — not a registry inventory count.",
            "registered": "Rows present in the registry authority (in-memory reconciled view).",
            "visible_to_desk": "Registered rows excluding operational/test cards.",
            "query_ready": "materialization.query_ready proved queryable — distinct from registered.",
            "analysis_readiness": "Declared analysis posture on the registry card (instant/metadata_search/…).",
            "completed_ne_registered_ne_query_ready": True,
        },
    }


def view_scope(
    *,
    scope_id: str,
    primary_total: int,
    primary_total_field: str,
    inventory: Mapping[str, Any],
    filters: Mapping[str, Any] | None = None,
    note: str = "",
) -> dict[str, Any]:
    """Declare which inventory field/scope an endpoint's headline count reflects."""
    return {
        "scope": scope_id,
        "scope_description": SCOPE_DESCRIPTIONS.get(scope_id, scope_id),
        "primary_total": int(primary_total),
        "primary_total_field": primary_total_field,
        "registry_fingerprint": (inventory.get("registry_revision") or {}).get("fingerprint"),
        "inventory_version": inventory.get("version"),
        "filters": dict(filters or {}),
        "note": note
        or (
            "Do not compare primary_total across endpoints unless scope and "
            "registry_fingerprint match."
        ),
    }


def inventory_compatible(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    """True when two payloads share inventory version + registry fingerprint."""
    left_inv = left.get("inventory") if isinstance(left.get("inventory"), Mapping) else left
    right_inv = right.get("inventory") if isinstance(right.get("inventory"), Mapping) else right
    if not isinstance(left_inv, Mapping) or not isinstance(right_inv, Mapping):
        return False
    if left_inv.get("version") != right_inv.get("version"):
        return False
    left_fp = (left_inv.get("registry_revision") or {}).get("fingerprint")
    right_fp = (right_inv.get("registry_revision") or {}).get("fingerprint")
    return bool(left_fp) and left_fp == right_fp


def assert_same_authority(
    left: Mapping[str, Any],
    right: Mapping[str, Any],
    *,
    expect_same_scope: bool = True,
) -> None:
    """Raise AssertionError on silent inventory mismatch between equivalent views."""
    if not inventory_compatible(left, right):
        left_inv = left.get("inventory") if isinstance(left.get("inventory"), Mapping) else left
        right_inv = right.get("inventory") if isinstance(right.get("inventory"), Mapping) else right
        raise AssertionError(
            "inventory fingerprint/version mismatch: "
            f"left={(left_inv or {}).get('registry_revision')} "
            f"right={(right_inv or {}).get('registry_revision')}"
        )
    left_view = left.get("view_scope") if isinstance(left.get("view_scope"), Mapping) else {}
    right_view = right.get("view_scope") if isinstance(right.get("view_scope"), Mapping) else {}
    if expect_same_scope and left_view and right_view:
        if left_view.get("scope") != right_view.get("scope"):
            raise AssertionError(
                f"scope mismatch: left={left_view.get('scope')} right={right_view.get('scope')}"
            )
        if left_view.get("primary_total") != right_view.get("primary_total"):
            raise AssertionError(
                "silent primary_total mismatch under shared scope/fingerprint: "
                f"left={left_view.get('primary_total')} right={right_view.get('primary_total')}"
            )
    left_inv = left.get("inventory") if isinstance(left.get("inventory"), Mapping) else left
    right_inv = right.get("inventory") if isinstance(right.get("inventory"), Mapping) else right
    if isinstance(left_inv, Mapping) and isinstance(right_inv, Mapping):
        if left_inv.get("totals") != right_inv.get("totals"):
            raise AssertionError(
                "inventory totals diverged under shared fingerprint: "
                f"left={left_inv.get('totals')} right={right_inv.get('totals')}"
            )
