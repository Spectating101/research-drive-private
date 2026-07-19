#!/usr/bin/env python3
"""Desk runtime — activity tracking, index readiness, fleet yield.

Interactive desk optimizes **discovery** (find / probe / describe).
Heavy **procurement** (download, archive) is cluster background work.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

_PREPARED: dict[str, Any] = {"ready": False, "curated_fts": "", "prepared_at": 0.0}


def desk_active_path(repo_root: Path) -> Path:
    return Path(repo_root).resolve() / "data_lake/procurement_memory/desk_active.json"


def desk_active_window_seconds() -> float:
    return max(30.0, float(os.environ.get("DESK_ACTIVE_WINDOW_SECONDS", "180")))


def touch_desk_activity(repo_root: Path, *, route: str = "") -> None:
    """Mark the desk as actively serving faculty traffic."""
    path = desk_active_path(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "last_touch": time.time(),
        "route": str(route or "")[:200],
        "pid": os.getpid(),
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def desk_is_active(repo_root: Path) -> bool:
    path = desk_active_path(repo_root)
    if not path.is_file():
        return False
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        last = float(doc.get("last_touch") or 0.0)
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return False
    return (time.time() - last) <= desk_active_window_seconds()


def fleet_should_yield(repo_root: Path | None = None) -> bool:
    """Background GDELT workers should pause while faculty are on the desk."""
    if os.environ.get("DESK_FLEET_YIELD", "1") in {"0", "false", "no"}:
        return False
    if repo_root is None:
        from sharpe_kernel.paths import repo_root_from_file

        repo_root = repo_root_from_file(__file__)
    return desk_is_active(Path(repo_root))


def prepare_desk_indexes(repo_root: Path) -> dict[str, Any]:
    """Build/load NVMe search indexes before serving traffic — no USB shard reads."""
    repo_root = Path(repo_root).resolve()
    from scripts.data_catalog.build_curated_topic_fts import ensure_curated_topic_fts
    from scripts.research_data_mcp.datacite_vault_search import set_prepared_curated_index

    curated_path = ensure_curated_topic_fts(repo_root)
    set_prepared_curated_index(curated_path)
    scrape_built = False
    try:
        from scripts.data_catalog.build_scrape_snippet_fts import build_scrape_snippet_fts, snippet_index_path

        if snippet_index_path(repo_root).is_file():
            scrape_built = True
        else:
            meta = build_scrape_snippet_fts(repo_root)
            scrape_built = bool(meta.get("built"))
    except Exception:
        scrape_built = False

    _PREPARED.update(
        {
            "ready": curated_path.is_file(),
            "curated_fts": str(curated_path),
            "scrape_fts": scrape_built,
            "prepared_at": time.time(),
            "interactive_vault": "nvme_only",
        }
    )
    return dict(_PREPARED)


def desk_index_status() -> dict[str, Any]:
    return dict(_PREPARED)


def runtime_status(repo_root: Path) -> dict[str, Any]:
    active = desk_is_active(repo_root)
    return {
        "indexes": desk_index_status(),
        "desk_active": active,
        "fleet_yield": fleet_should_yield(repo_root),
        "active_window_seconds": desk_active_window_seconds(),
    }
