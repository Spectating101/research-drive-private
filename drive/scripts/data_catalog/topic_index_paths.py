#!/usr/bin/env python3
"""Resolve topic-index and index_v3 paths (NVMe repo vs bulk USB)."""

from __future__ import annotations

import os
from pathlib import Path

from scripts.research_data_mcp.data_paths import bulk_data_lake_root


def index_v3_root(repo_root: Path) -> Path:
    env = (os.environ.get("DATACITE_INDEX_V3_ROOT") or os.environ.get("DATACITE_LOCAL_ROOT") or "").strip()
    if env:
        p = Path(env)
        return p if p.is_absolute() else (Path(repo_root).resolve() / p)
    if os.environ.get("DATACITE_TOPIC_INDEX_ON_BULK", "0") == "1":
        bulk = bulk_data_lake_root()
        if bulk is not None:
            return bulk / "dataset_catalog/index_v3"
    return Path(repo_root).resolve() / "data_lake/dataset_catalog/index_v3"


def topic_index_root(repo_root: Path) -> Path:
    env = (os.environ.get("DATACITE_TOPIC_INDEX_ROOT") or "").strip()
    if env:
        p = Path(env)
        return p if p.is_absolute() else (Path(repo_root).resolve() / p)
    if os.environ.get("DATACITE_TOPIC_INDEX_ON_BULK", "0") == "1":
        bulk = bulk_data_lake_root()
        if bulk is not None:
            return bulk / "dataset_catalog/_topic_index"
    return Path(repo_root).resolve() / "data_lake/dataset_catalog/_topic_index"


def shard_index_dir(repo_root: Path) -> Path:
    return topic_index_root(repo_root) / "shards"


def shard_index_candidates(repo_root: Path, *, interactive: bool = True) -> list[Path]:
    """Search paths for shard FTS.

    Interactive desk search uses NVMe repo shards only — never USB bulk (too slow).
    Batch/deep callers pass interactive=False to include bulk USB when configured.
    """
    repo_root = Path(repo_root).resolve()
    seen: set[str] = set()
    out: list[Path] = []
    roots: list[Path] = []
    if interactive:
        roots.append(repo_root / "data_lake/dataset_catalog/_topic_index")
    else:
        bulk = bulk_data_lake_root()
        if bulk is not None:
            roots.append(bulk / "dataset_catalog/_topic_index")
        roots.append(repo_root / "data_lake/dataset_catalog/_topic_index")
    for root in roots:
        key = str(root.resolve())
        if key in seen:
            continue
        seen.add(key)
        shard_dir = root / "shards"
        if shard_dir.is_dir():
            out.append(shard_dir)
    return out
