#!/usr/bin/env python3
"""Resolve collection partition IDs to canonical / local paths."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

SIZE_HINT_RE = re.compile(r"^([\d.]+)\s*(GiB|MiB|TiB|KiB)$", re.I)
UNIT_BYTES = {"kib": 1024, "mib": 1024**2, "gib": 1024**3, "tib": 1024**4}


@lru_cache(maxsize=1)
def load_partitions(repo_root: Path) -> dict[str, Any]:
    path = Path(repo_root).resolve() / "config/collection_partitions.json"
    return json.loads(path.read_text(encoding="utf-8"))


def partition_by_id(repo_root: Path, partition_id: str) -> dict[str, Any] | None:
    cfg = load_partitions(repo_root)
    for part in cfg.get("partitions") or []:
        if str(part.get("id")) == partition_id:
            return part
    return None


def parse_size_hint(hint: str | None) -> int:
    if not hint:
        return 0
    m = SIZE_HINT_RE.match(str(hint).strip())
    if not m:
        return 0
    mult = UNIT_BYTES.get(m.group(2).lower(), 1)
    return int(float(m.group(1)) * mult)


def canonical_remote(repo_root: Path, part: dict[str, Any], *, use_target: bool = False) -> str | None:
    root = str(load_partitions(repo_root).get("canonical_root", "")).rstrip("/")
    if not root:
        return None
    rel = part.get("target_drive_path") if use_target else part.get("legacy_drive_path")
    if not rel:
        return None
    return f"{root}/{rel}"


def local_storage_path(repo_root: Path, part: dict[str, Any]) -> Path | None:
    raw = part.get("legacy_local_path")
    if not raw:
        return None
    return Path(repo_root).resolve() / str(raw)


def collection_slot(repo_root: Path, part: dict[str, Any]) -> Path:
    root = str(load_partitions(repo_root).get("collection_root", "data_lake/collection"))
    return Path(repo_root).resolve() / root / str(part["path"])


def list_shards(repo_root: Path, partition_id: str = "catalog.datacite-harvest") -> list[dict[str, str]]:
    """DataCite harvest shards from operator list file."""
    part = partition_by_id(repo_root, partition_id)
    if not part:
        return []
    rel = str(part.get("shard_manifest") or "scripts/data_catalog/datacite_y2025_parallel_shards.list")
    path = Path(repo_root).resolve() / rel
    if not path.is_file():
        return []
    rows: list[dict[str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        bits = [b.strip() for b in line.split("|")]
        if len(bits) < 2:
            continue
        rows.append(
            {
                "shard": bits[0],
                "host": bits[1] if len(bits) > 1 else "",
                "created_years": bits[2] if len(bits) > 2 else "",
                "query": bits[3] if len(bits) > 3 else "",
                "target_records": bits[4] if len(bits) > 4 else "",
            }
        )
    return rows
