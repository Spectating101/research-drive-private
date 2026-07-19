#!/usr/bin/env python3
"""Three-tier storage: canonical (GDrive), cache (USB bulk), hot (NVMe desk)."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

from scripts.research_data_mcp.data_paths import (
    MARKER,
    bulk_data_lake_root,
    bulk_storage_root,
    local_data_lake_root,
)

_CONFIG_NAME = "storage_tiers.json"


def tiers_config_path(repo_root: Path) -> Path:
    return repo_root / "config" / _CONFIG_NAME


def load_storage_tiers(repo_root: Path) -> dict[str, Any]:
    path = tiers_config_path(repo_root)
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _norm_rel(value: str | Path) -> str:
    return str(value).replace("\\", "/").lstrip("/")


def is_hot_path(repo_root: Path, value: str | Path) -> bool:
    """Paths that must stay on NVMe even when bulk cache is mounted."""
    cfg = load_storage_tiers(repo_root)
    prefixes = (cfg.get("tiers") or {}).get("hot", {}).get("path_prefixes") or []
    rel = _norm_rel(value)
    if not rel.startswith("data_lake"):
        return False
    for prefix in prefixes:
        p = _norm_rel(prefix)
        if rel == p or rel.startswith(p + "/"):
            return True
    return False


def is_bulk_cache_path(repo_root: Path, value: str | Path) -> bool:
    """Heavy pipeline trees that belong on USB cache, not NVMe."""
    cfg = load_storage_tiers(repo_root)
    rel = _norm_rel(value)
    if not rel.startswith("data_lake"):
        return False
    if is_hot_path(repo_root, rel):
        return False
    subdirs = (cfg.get("tiers") or {}).get("cache", {}).get("bulk_subdirs") or []
    rest = rel.removeprefix("data_lake/").removeprefix("data_lake")
    if not rest:
        return False
    top = rest.split("/", 1)[0]
    return top in subdirs


def canonical_drive_root(repo_root: Path) -> str:
    cfg = load_storage_tiers(repo_root)
    tier = (cfg.get("tiers") or {}).get("canonical") or {}
    if tier.get("drive_root"):
        return str(tier["drive_root"])
    # Fallback: yzu_cluster.json
    yzu = repo_root / "config" / "yzu_cluster.json"
    if yzu.is_file():
        data = json.loads(yzu.read_text(encoding="utf-8"))
        return str((data.get("storage") or {}).get("drive_root") or "")
    return ""


def gdelt_normalized_drive_roots(repo_root: Path) -> list[str]:
    cfg = load_storage_tiers(repo_root)
    roots = (cfg.get("tiers") or {}).get("canonical", {}).get("gdelt_normalized_roots")
    if roots:
        return [str(r) for r in roots]
    return []


def resolve_data_path_tiered(repo_root: Path, value: str | Path) -> Path:
    """Resolve registry paths: hot → NVMe; bulk → cache when mounted and present; else NVMe."""
    p = Path(value)
    if p.is_absolute():
        return p.resolve()

    rel = _norm_rel(p)
    local_target = (repo_root / rel).resolve()
    if is_hot_path(repo_root, rel):
        return local_target

    if rel == "data_lake" or rel.startswith("data_lake/"):
        suffix = rel.removeprefix("data_lake/").removeprefix("data_lake")
        bulk = bulk_data_lake_root()
        cfg = load_storage_tiers(repo_root)
        prefer_cache = bool((cfg.get("rules") or {}).get("prefer_cache_for_bulk_reads", True))
        if bulk is not None and prefer_cache and is_bulk_cache_path(repo_root, rel):
            cache_target = (bulk / suffix).resolve() if suffix else bulk
            if cache_target.exists():
                return cache_target
            # USB mounted but tree missing — fall back to NVMe mirror/stub
            if local_target.exists():
                return local_target
            parent = cache_target.parent
            if suffix and parent.is_dir() and any(parent.iterdir()):
                return cache_target
    return local_target


def nvme_disk_headroom_gb(repo_root: Path) -> tuple[float, int]:
    """Return (free_gb, required_min_gb) for NVMe root based on cache mount state.

    free_gb is rounded to 1 decimal (not truncated) so 39.7 GB is not reported as 39.
    """
    cfg = load_storage_tiers(repo_root)
    rules = cfg.get("rules") or {}
    free_kb = shutil.disk_usage(repo_root).free
    free_gb = round(free_kb / (1024**3), 1)
    if bulk_storage_root() is not None:
        required = int(rules.get("nvme_min_free_gb_when_cache_mounted", 40))
    else:
        required = int(rules.get("nvme_min_free_gb_when_cache_offline", 60))
    return free_gb, required


def cache_retention_mode(repo_root: Path) -> str:
    cfg = load_storage_tiers(repo_root)
    return str(
        (cfg.get("tiers") or {})
        .get("cache", {})
        .get("retention_after_canonical_verify", "compact_staging_only")
    )


def storage_tiers_status(repo_root: Path) -> dict[str, Any]:
    """Desk health: canonical + cache + hot snapshot."""
    cfg = load_storage_tiers(repo_root)
    tiers = cfg.get("tiers") or {}
    hot = tiers.get("hot") or {}
    canonical = tiers.get("canonical") or {}
    cache_tier = tiers.get("cache") or {}

    nvme_free, nvme_required = nvme_disk_headroom_gb(repo_root)
    try:
        nvme_usage = shutil.disk_usage(repo_root)
        nvme_pct = round(100.0 * nvme_usage.used / nvme_usage.total, 1)
    except OSError:
        nvme_pct = None

    bulk_root = bulk_storage_root()
    cache_block: dict[str, Any] = {
        "mounted": bulk_root is not None,
        "role": cache_tier.get("role", "bulk_analysis_cache"),
        "label": cache_tier.get("label", "Bulk cache"),
        "retention": cache_retention_mode(repo_root),
    }
    if bulk_root is not None:
        try:
            usage = shutil.disk_usage(bulk_root)
            lake = bulk_root / "data_lake"
            cache_block.update(
                {
                    "root": str(bulk_root),
                    "data_lake": str(lake) if lake.is_dir() else None,
                    "total_gb": round(usage.total / (1024**3), 2),
                    "used_gb": round(usage.used / (1024**3), 2),
                    "free_gb": round(usage.free / (1024**3), 2),
                    "mobile": True,
                }
            )
        except OSError as exc:
            cache_block["error"] = str(exc)
    else:
        cache_block["message"] = (
            "Bulk cache offline — canonical data on GDrive; hydrate cache for local analysis."
        )

    return {
        "architecture": cfg.get("summary", ""),
        "canonical": {
            "label": canonical.get("label", "Google Drive vault"),
            "role": canonical.get("role", "source_of_truth"),
            "drive_root": canonical_drive_root(repo_root),
            "upload_policy": canonical.get("upload_policy", "copy_verify"),
            "completion_requires_verify": bool(canonical.get("completion_requires_verify", True)),
            "pool_tb": float(canonical.get("drive_total_tb") or 5),
            "quota_tb": float(canonical.get("archive_quota_tb") or 3),
        },
        "cache": cache_block,
        "hot": {
            "label": hot.get("label", "NVMe desk"),
            "role": hot.get("role", "latency_and_sqlite"),
            "data_lake": str(local_data_lake_root(repo_root)),
            "free_gb": nvme_free,
            "required_min_gb": nvme_required,
            "used_pct": nvme_pct,
            "headroom_ok": nvme_free >= nvme_required,
        },
        "rules": cfg.get("rules") or {},
    }


def load_unified_storage_policy(repo_root: Path) -> dict[str, Any]:
    """Merged policy for procurement agents and catalog."""
    cfg = load_storage_tiers(repo_root)
    canonical = (cfg.get("tiers") or {}).get("canonical") or {}
    cache = (cfg.get("tiers") or {}).get("cache") or {}
    drive_root = canonical_drive_root(repo_root)
    bulk = bulk_storage_root()
    note = (
        "Drive-first: canonical writes go to GDrive collection partitions on job completion. "
        "Local staging is ephemeral and may be compacted after verify. "
        "Use collection_hydrate to pull partition bytes to desk for analysis. "
        "USB bulk cache ({cache}) is optional read cache only."
    ).format(
        cache=str(bulk) if bulk else "offline",
    )
    return {
        "local_staging": "data_lake",
        "procured_root": "data_lake/procured",
        "acquisitions_root": "data_lake/yzu_cluster/acquisitions",
        "gdrive_root": drive_root,
        "canonical_archive": drive_root,
        "bulk_cache_root": str(bulk) if bulk else None,
        "upload_policy": canonical.get("upload_policy", "copy_verify"),
        "cache_retention": cache.get("retention_after_canonical_verify", "compact_staging_only"),
        "auto_archive_procured": True,
        "drive_first": bool((cfg.get("rules") or {}).get("drive_first")),
        "completion_requires_drive_verify": True,
        "policy_note": note,
        "tiers": storage_tiers_status(repo_root),
    }
