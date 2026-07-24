#!/usr/bin/env python3
"""Bulk storage (mobile USB) + repo data_lake path resolution."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

MARKER = ".sharpe_research_bulk"

# Checked in order; first *marked* mount wins unless RESEARCH_BULK_ROOT is set.
# Prefer Transcend1 over leftover /media/.../Transcend stubs (empty NVMe dirs after remount).
DEFAULT_BULK_CANDIDATES = (
    "/mnt/research-data/sharpe-renaissance",
    "/media/phyrexian/Transcend1/sharpe-renaissance",
    "/media/phyrexian/Transcend/sharpe-renaissance",
)


def bulk_storage_root() -> Path | None:
    """Root of external bulk store, or None if unplugged / unset.

    Prefer a directory with MARKER so empty remount stubs (data_lake present, no bytes)
    cannot shadow the real USB.
    """
    env = (os.environ.get("RESEARCH_BULK_ROOT") or "").strip()
    candidates: list[str] = []
    if env:
        candidates.append(env)
    candidates.extend(DEFAULT_BULK_CANDIDATES)
    seen: set[str] = set()
    marked: Path | None = None
    lake_only: Path | None = None
    for raw in candidates:
        if not raw or raw in seen:
            continue
        seen.add(raw)
        root = Path(raw).expanduser()
        if not root.is_dir():
            continue
        resolved = root.resolve()
        if (resolved / MARKER).is_file():
            if marked is None:
                marked = resolved
            continue
        if lake_only is None and (resolved / "data_lake").is_dir():
            lake_only = resolved
    return marked or lake_only


def bulk_data_lake_root() -> Path | None:
    root = bulk_storage_root()
    if root is None:
        return None
    lake = root / "data_lake"
    return lake.resolve() if lake.is_dir() else None


def local_data_lake_root(repo_root: Path) -> Path:
    return (repo_root / "data_lake").resolve()


def resolve_data_path(repo_root: Path, value: str | Path) -> Path:
    """Resolve registry/script paths (hot → NVMe, bulk → USB cache when mounted)."""
    from scripts.research_data_mcp.storage_tiers import resolve_data_path_tiered

    return resolve_data_path_tiered(repo_root, value)


def bulk_storage_status() -> dict[str, Any]:
    """Legacy desk health slice — prefer storage_tiers_status() for full picture."""
    """Desk health payload for mobile bulk disk."""
    root = bulk_storage_root()
    if root is None:
        return {
            "mounted": False,
            "label": "Mobile bulk storage",
            "message": "Bulk drive not mounted — using local data_lake only.",
        }
    try:
        usage = shutil.disk_usage(root)
    except OSError as exc:
        return {"mounted": False, "error": str(exc)}
    lake = root / "data_lake"
    return {
        "mounted": True,
        "root": str(root),
        "data_lake": str(lake) if lake.is_dir() else None,
        "label": "Transcend bulk",
        "total_gb": round(usage.total / (1024**3), 2),
        "used_gb": round(usage.used / (1024**3), 2),
        "free_gb": round(usage.free / (1024**3), 2),
        "mobile": True,
    }
