#!/usr/bin/env python3
"""Vault partition status cards — NOT acquisition/product capability lanes.

Drive partitions are organizational folders. Desk capability is AI identify +
custom procure. Only surfaces partitions that already hold local bytes, or the
generic acquired.procured land zone. Empty vendor-named slots never appear.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any


@lru_cache(maxsize=4)
def _load_partitions(repo_root: str) -> dict[str, Any]:
    path = Path(repo_root).resolve() / "config/collection_partitions.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _canonical_remote(repo_root: Path, part: dict[str, Any], *, use_target: bool = False) -> str | None:
    root = str(_load_partitions(str(repo_root)).get("canonical_root", "")).rstrip("/")
    if not root:
        return None
    rel = part.get("target_drive_path") if use_target else part.get("legacy_drive_path")
    if not rel:
        return None
    return f"{root}/{rel}"


def _local_storage_path(repo_root: Path, part: dict[str, Any]) -> Path | None:
    raw = part.get("legacy_local_path")
    if not raw:
        return None
    return Path(repo_root).resolve() / str(raw)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _local_bytes(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size
    total = 0
    for p in path.rglob("*"):
        if p.is_file():
            try:
                total += p.stat().st_size
            except OSError:
                pass
    return total


def _stage_for_status(status: str, *, local_ok: bool) -> tuple[str, str]:
    s = (status or "unknown").lower()
    if s in {"frozen_release", "complete", "migrated", "synced"} and local_ok:
        return "complete", "green"
    if s in {"active", "procurement_wired", "running"}:
        return "running" if local_ok else "idle", "blue" if local_ok else "amber"
    if s == "local_only":
        return "idle", "amber"
    return "idle", "amber" if not local_ok else "green"


def _release_meta(repo_root: Path, part: dict[str, Any]) -> dict[str, Any] | None:
    local = _local_storage_path(repo_root, part)
    if not local or not local.is_dir():
        return None
    for child in sorted(local.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        rel = child / "RELEASE.json"
        if rel.is_file():
            try:
                return json.loads(rel.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return None
    return None


def _should_surface(part: dict[str, Any], *, local_bytes: int) -> bool:
    """Never sell empty/example vendor folders as desk capabilities."""
    if part.get("professor_visible") is False:
        return False
    domain = str(part.get("domain") or "")
    if domain == "backend":
        return False
    status = str(part.get("status") or "").lower()
    if status in {"example_slot", "example_reference", "catalog_only"}:
        return False
    pid = str(part.get("id") or "")
    # Generic land zone is always a valid desk surface.
    if pid == "acquired.procured" or domain == "acquired":
        return True
    # Only held vault drawers with real local bytes.
    return local_bytes > 0


def partition_lane(repo_root: Path, part: dict[str, Any]) -> dict[str, Any] | None:
    local = _local_storage_path(repo_root, part)
    local_ok = bool(local and local.exists())
    local_bytes = _local_bytes(local) if local_ok and local else 0
    if not _should_surface(part, local_bytes=local_bytes):
        return None

    domain = str(part.get("domain") or "")
    pid = str(part.get("id") or "")
    registry_ids = list(part.get("registry_dataset_ids") or [])
    status = str(part.get("status") or "unknown")
    stage, tone = _stage_for_status(status, local_ok=local_ok)
    release = _release_meta(repo_root, part) if status == "frozen_release" else None

    amount_bits: list[str] = []
    if registry_ids:
        amount_bits.append(f"{len(registry_ids)} registry datasets")
    if local_bytes:
        gib = local_bytes / (1024**3)
        amount_bits.append(f"{gib:.2f} GiB local" if gib >= 0.1 else f"{local_bytes / (1024**2):.0f} MiB local")
    elif not local_ok:
        amount_bits.append("land via custom procure")

    progress = 100.0 if stage == "complete" else (50.0 if local_ok else 0.0)
    if release:
        progress = 100.0
        stage = "complete"
        tone = "green"

    remote = _canonical_remote(repo_root, part, use_target=True) or _canonical_remote(repo_root, part)
    subtitle = str(part.get("professor_label") or part.get("title") or pid)
    detail: dict[str, Any] = {
        "partition_id": pid,
        "domain": domain,
        "status": status,
        "local_path": str(local) if local else None,
        "local_present": local_ok,
        "registry_dataset_ids": registry_ids,
        "target_drive_path": part.get("target_drive_path"),
        "canonical_remote": remote,
        "role": "vault_holding" if local_bytes > 0 else "generic_land_zone",
    }
    if release:
        detail["release"] = {
            "release_id": release.get("release_id"),
            "frozen_at": release.get("frozen_at"),
            "platform_readiness": release.get("platform_readiness"),
            "bulk_harvest_policy": release.get("bulk_harvest_policy"),
        }

    return {
        "id": f"partition_{pid.replace('.', '_')}",
        "partition_id": pid,
        "name": str(part.get("title") or pid),
        "subtitle": subtitle,
        "professor_label": subtitle,
        "professor_visible": True,
        "scope": str(part.get("description") or "")[:160],
        "stage": stage,
        "tone": tone,
        "progress": progress,
        "amount": " · ".join(amount_bits) if amount_bits else "partition",
        "worker": "cluster archive",
        "destination": remote or str(part.get("target_drive_path") or ""),
        "updated_at": (release or {}).get("frozen_at") or _now(),
        "detail": detail,
        # Kept kind for FE back-compat; role clarifies these are not product lanes.
        "kind": "collection_partition",
        "role": detail["role"],
    }


def partition_lanes(repo_root: Path) -> list[dict[str, Any]]:
    cfg = _load_partitions(str(repo_root))
    lanes: list[dict[str, Any]] = []
    for part in cfg.get("partitions") or []:
        row = partition_lane(repo_root, part)
        if row:
            lanes.append(row)
    lanes.sort(key=lambda r: (r.get("stage") != "complete", r.get("name", "")))
    return lanes
