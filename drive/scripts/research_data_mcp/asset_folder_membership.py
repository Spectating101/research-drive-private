"""Canonical Library folder/asset membership facts.

Prevents deep-linked assets from appearing inside empty unrelated folders.
Membership is derived only from explicit partition_id or partition
registry_dataset_ids — never from name/path substring guessing.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any


def _registry_ids(part: dict[str, Any]) -> set[str]:
    detail = part.get("detail") if isinstance(part.get("detail"), dict) else {}
    ids = part.get("registry_dataset_ids") or detail.get("registry_dataset_ids") or []
    return {str(x).strip() for x in ids if str(x).strip()}


def _partition_id(part: dict[str, Any]) -> str:
    return str(part.get("partition_id") or part.get("id") or detail_pid(part) or "").strip()


def detail_pid(part: dict[str, Any]) -> str:
    detail = part.get("detail") if isinstance(part.get("detail"), dict) else {}
    return str(detail.get("partition_id") or "").strip()


def _shelf_id(part: dict[str, Any]) -> str:
    detail = part.get("detail") if isinstance(part.get("detail"), dict) else {}
    return str(part.get("shelf_id") or detail.get("shelf_id") or "").strip()


def folder_id_for(shelf_id: str, partition_id: str) -> str | None:
    sid = str(shelf_id or "").strip()
    pid = str(partition_id or "").strip()
    if sid and pid:
        return f"{sid}/{pid}"
    if pid:
        return pid
    return None


@lru_cache(maxsize=4)
def load_partition_membership_index(repo_root: str) -> tuple[dict[str, Any], ...]:
    """Load partition lane facts used for membership (cached per repo root)."""
    root = Path(repo_root).resolve()
    try:
        from scripts.yzu_cluster.partition_lanes import partition_lanes

        lanes = partition_lanes(root) or []
    except Exception:
        lanes = []
    # Normalize to a stable tuple of plain dicts for lru_cache.
    normalized: list[dict[str, Any]] = []
    for lane in lanes:
        if not isinstance(lane, dict):
            continue
        pid = _partition_id(lane)
        if not pid:
            continue
        detail = lane.get("detail") if isinstance(lane.get("detail"), dict) else {}
        normalized.append(
            {
                "partition_id": pid,
                "shelf_id": _shelf_id(lane),
                "registry_dataset_ids": sorted(_registry_ids(lane)),
                "detail": {
                    "partition_id": pid,
                    "shelf_id": detail.get("shelf_id") or _shelf_id(lane),
                    "registry_dataset_ids": sorted(_registry_ids(lane)),
                },
            }
        )
    return tuple(normalized)


def resolve_asset_membership(
    row: dict[str, Any] | None,
    *,
    partitions: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None = None,
    repo_root: Path | str | None = None,
) -> dict[str, Any]:
    """Resolve canonical folder membership for a registry asset.

    Basis precedence:
    1. explicit row.partition_id matching a known partition
    2. dataset_id listed in partition.registry_dataset_ids
    3. unknown (do not guess)
    """
    unknown = {
        "known": False,
        "folder_id": None,
        "shelf_id": None,
        "partition_id": None,
        "membership_basis": "unknown",
        "folder_ids": [],
    }
    if not isinstance(row, dict):
        return dict(unknown)

    parts: list[dict[str, Any]]
    if partitions is not None:
        parts = list(partitions)
    elif repo_root is not None:
        parts = list(load_partition_membership_index(str(Path(repo_root).resolve())))
    else:
        parts = []

    by_pid = {_partition_id(p): p for p in parts if _partition_id(p)}
    dataset_id = str(row.get("dataset_id") or "").strip()
    explicit_pid = str(
        row.get("partition_id") or (row.get("collection") or {}).get("partition_id") or ""
    ).strip()

    chosen: dict[str, Any] | None = None
    basis = "unknown"
    if explicit_pid and explicit_pid in by_pid:
        chosen = by_pid[explicit_pid]
        basis = "partition_id"
    elif explicit_pid and not by_pid:
        # Partition id present but index unavailable — still surface explicit id.
        folder_id = folder_id_for(str(row.get("shelf_id") or ""), explicit_pid)
        return {
            "known": bool(folder_id or explicit_pid),
            "folder_id": folder_id,
            "shelf_id": str(row.get("shelf_id") or "").strip() or None,
            "partition_id": explicit_pid,
            "membership_basis": "partition_id",
            "folder_ids": [folder_id] if folder_id else [],
        }
    elif dataset_id:
        for part in parts:
            if dataset_id in _registry_ids(part):
                chosen = part
                basis = "registry_dataset_ids"
                break

    if not chosen:
        return dict(unknown)

    pid = _partition_id(chosen)
    sid = _shelf_id(chosen)
    folder_id = folder_id_for(sid, pid)
    return {
        "known": True,
        "folder_id": folder_id,
        "shelf_id": sid or None,
        "partition_id": pid or None,
        "membership_basis": basis,
        "folder_ids": [folder_id] if folder_id else [],
    }


def asset_belongs_in_folder(membership: dict[str, Any] | None, folder_id: str | None) -> bool:
    """True only for an exact canonical folder_id match — never fuzzy shelf/name guesses."""
    if not isinstance(membership, dict) or not membership.get("known"):
        return False
    target = str(folder_id or "").strip()
    if not target:
        return False
    owned = {str(x).strip() for x in (membership.get("folder_ids") or []) if str(x).strip()}
    canonical = str(membership.get("folder_id") or "").strip()
    if canonical:
        owned.add(canonical)
    return target in owned


def stamp_asset_membership(
    row: dict[str, Any] | None,
    *,
    partitions: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None = None,
    repo_root: Path | str | None = None,
) -> dict[str, Any]:
    """Return a shallow copy of row stamped with canonical membership fields."""
    if not isinstance(row, dict):
        return {}
    out = dict(row)
    mem = resolve_asset_membership(out, partitions=partitions, repo_root=repo_root)
    out["membership"] = mem
    if mem.get("folder_id"):
        out["folder_id"] = mem["folder_id"]
    if mem.get("shelf_id"):
        out["shelf_id"] = mem["shelf_id"]
    if mem.get("partition_id") and not out.get("partition_id"):
        out["partition_id"] = mem["partition_id"]
    out["folder_ids"] = list(mem.get("folder_ids") or [])
    return out
