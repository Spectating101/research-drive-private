#!/usr/bin/env python3
"""Wire procured datasets into collection partitions + GDrive archive paths."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from scripts.research_data_mcp.collection_resolve import partition_by_id

DEFAULT_PARTITION = "acquired.procured"


@lru_cache(maxsize=8)
def _registry_by_id(repo_root: str) -> dict[str, dict[str, Any]]:
    path = Path(repo_root).resolve() / "config/research_query_registry.json"
    if not path.is_file():
        return {}
    doc = json.loads(path.read_text(encoding="utf-8"))
    return {str(r.get("dataset_id") or ""): r for r in doc.get("datasets") or [] if r.get("dataset_id")}


def partition_id_for_dataset(repo_root: Path, dataset_id: str) -> str:
    row = _registry_by_id(str(repo_root.resolve())).get(str(dataset_id or "").strip()) or {}
    collection = row.get("collection") or {}
    pid = str(row.get("partition_id") or collection.get("partition_id") or "").strip()
    return pid or DEFAULT_PARTITION


def infer_partition_id(
    query: str,
    *,
    url: str = "",
    dataset_id: str = "",
    repo_root: Path | None = None,
) -> str:
    """Resolve partition from registry metadata — not query keyword rules."""
    _ = query, url
    rid = str(dataset_id or "").strip()
    if rid and repo_root is not None:
        return partition_id_for_dataset(repo_root, rid)
    return DEFAULT_PARTITION


def attach_partition_to_plan(plan: dict[str, Any], query: str, *, repo_root: Path | None = None) -> dict[str, Any]:
    if str(plan.get("partition_id") or "").strip():
        return plan
    out = dict(plan)
    ds = str(
        plan.get("dataset_id")
        or plan.get("registry_dataset_id")
        or plan.get("task_id")
        or ""
    ).strip()
    root = repo_root or Path.cwd()
    out["partition_id"] = infer_partition_id(query, url=str(plan.get("url") or ""), dataset_id=ds, repo_root=root)
    return out


def archive_remote_suffix(repo_root: Path, plan: dict[str, Any], dataset_id: str) -> str | None:
    """GDrive path under canonical collection layout: {target_drive_path}/{dataset_id}."""
    pid = str(plan.get("partition_id") or "").strip()
    if not pid:
        return None
    part = partition_by_id(repo_root, pid)
    if not part:
        return None
    base = str(part.get("target_drive_path") or "").strip().rstrip("/")
    if not base:
        return None
    return f"{base}/{dataset_id}"


def _partitions_path(repo_root: Path) -> Path:
    return Path(repo_root).resolve() / "config/collection_partitions.json"


def wire_promoted_to_partition(
    repo_root: Path,
    *,
    promoted: list[dict[str, Any]],
    plan: dict[str, Any],
    search_goal: str = "",
    registry_path: Path | None = None,
    rebuild_index: bool = True,
) -> dict[str, Any]:
    """Append promoted dataset_ids to partition.registry_dataset_ids; stamp registry rows."""
    if not promoted:
        return {"wired": False, "reason": "no_promoted"}

    first_id = str((promoted[0] or {}).get("dataset_id") or "").strip()
    pid = str(plan.get("partition_id") or "").strip()
    if not pid and first_id:
        pid = partition_id_for_dataset(repo_root, first_id)
    if not pid:
        pid = infer_partition_id(search_goal, url=str(plan.get("url") or ""), repo_root=repo_root)
    part = partition_by_id(repo_root, pid)
    if not part:
        return {"wired": False, "reason": "partition_not_found", "partition_id": pid}

    reg_path = registry_path or (Path(repo_root).resolve() / "config/research_query_registry.json")
    reg_doc = json.loads(reg_path.read_text(encoding="utf-8")) if reg_path.is_file() else {"datasets": []}
    reg_by_id = {str(r.get("dataset_id")): r for r in reg_doc.get("datasets") or []}

    wired_ids: list[str] = []
    for row in promoted:
        did = str(row.get("dataset_id") or "").strip()
        if not did:
            continue
        wired_ids.append(did)
        reg_row = reg_by_id.get(did) or {}
        reg_row = dict(reg_row)
        reg_row["partition_id"] = pid
        collection = dict(reg_row.get("collection") or {})
        collection["partition_id"] = pid
        collection["wired_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        reg_row["collection"] = collection
        reg_by_id[did] = reg_row

    reg_doc["datasets"] = list(reg_by_id.values())
    reg_path.write_text(json.dumps(reg_doc, indent=2) + "\n", encoding="utf-8")

    part_path = _partitions_path(repo_root)
    part_doc = json.loads(part_path.read_text(encoding="utf-8"))
    for p in part_doc.get("partitions") or []:
        if str(p.get("id")) != pid:
            continue
        ids = list(p.get("registry_dataset_ids") or [])
        for did in wired_ids:
            if did not in ids:
                ids.append(did)
        p["registry_dataset_ids"] = ids
        break
    part_path.write_text(json.dumps(part_doc, indent=2) + "\n", encoding="utf-8")

    if rebuild_index:
        from scripts.research_data_mcp.collection_dictionary import write_dictionary
        from scripts.research_data_mcp.collection_index import build_index

        write_dictionary(repo_root)
        build_index(repo_root)

    return {"wired": True, "partition_id": pid, "dataset_ids": wired_ids}
