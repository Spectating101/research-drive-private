#!/usr/bin/env python3
"""Bulk storage (mobile USB) + repo data_lake path resolution."""

from __future__ import annotations

import json
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


def _configured_data_roots(repo_root: Path) -> list[str]:
    """Extra repo roots declared in ``config/storage_tiers.json``.

    Read with plain ``json`` rather than importing ``storage_tiers``, which
    imports this module.
    """
    path = repo_root / "config" / "storage_tiers.json"
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    roots = ((cfg.get("tiers") or {}).get("hot") or {}).get("data_roots") or []
    return [str(r) for r in roots if r]


def data_lake_search_roots(repo_root: Path) -> list[Path]:
    """Repo roots to search for an existing ``data_lake`` tree, in priority order.

    Several checkouts share one registry by symlink -- the front door, the
    security checkout and the runtime-integration checkout all resolve
    ``config/research_query_registry.json`` to the same file -- while each keeps
    its own ``data_lake``.  Registry paths are relative, so they resolved against
    whichever checkout happened to be serving, and the serving checkout holds a
    near-empty stub.  The result was that a dataset's bytes existed on disk and
    the probe still reported it unavailable.

    ``repo_root`` is always first, so anything that resolves today keeps
    resolving to exactly the same file and no currently-working path changes.
    Additional roots are consulted only when the repo-local path does not exist.
    """
    roots: list[Path] = [Path(repo_root)]
    env = (os.environ.get("RESEARCH_DATA_ROOTS") or os.environ.get("RESEARCH_DATA_ROOT") or "").strip()
    raw = [part for part in env.split(os.pathsep) if part.strip()]
    raw.extend(_configured_data_roots(repo_root))
    for entry in raw:
        candidate = Path(entry).expanduser()
        if not candidate.is_absolute():
            candidate = (repo_root / candidate)
        roots.append(candidate)
    seen: set[str] = set()
    ordered: list[Path] = []
    for root in roots:
        try:
            resolved = root.resolve()
        except OSError:
            continue
        key = str(resolved)
        if key in seen or not resolved.is_dir():
            continue
        seen.add(key)
        ordered.append(resolved)
    return ordered


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
