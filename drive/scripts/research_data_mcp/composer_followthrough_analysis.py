#!/usr/bin/env python3
"""Bounded dataset analysis pipes — hydrate + stats for MCP tools."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from scripts.research_data_mcp.collection_dictionary import build_dictionary, dictionary_path
from scripts.research_data_mcp.collection_hydrate import build_hydrate_plan, execute_hydrate

DEFAULT_SYNC_HYDRATE_MAX_MB = int(os.getenv("COMPOSER_SYNC_HYDRATE_MAX_MB", "2048"))


def _partition_dictionary_row(repo_root: Path, partition_id: str) -> dict[str, Any] | None:
    path = dictionary_path(repo_root)
    doc = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else build_dictionary(repo_root)
    for row in (doc.get("tables") or {}).get("partitions") or []:
        if str(row.get("id")) == partition_id:
            return row
    return None


def _partition_drive_mb(part: dict[str, Any] | None) -> float | None:
    if not part:
        return None
    hint = str(part.get("drive_size_hint") or "")
    import re

    m = re.search(r"([\d.]+)\s*GiB", hint)
    if m:
        return float(m.group(1)) * 1024
    m = re.search(r"([\d.]+)\s*MiB", hint)
    if m:
        return float(m.group(1))
    av = (part or {}).get("availability") or {}
    bytes_drive = int(av.get("bytes_drive") or av.get("drive_bytes") or 0)
    if bytes_drive > 0:
        return bytes_drive / (1024 * 1024)
    return None


def partition_needs_hydrate(repo_root: Path, partition_id: str) -> bool:
    row = _partition_dictionary_row(repo_root, partition_id)
    if not row:
        return False
    av = row.get("availability") or {}
    on_local = bool(av.get("on_local"))
    on_drive = str(av.get("on_drive") or "").lower() in {"yes", "expected"}
    return bool(on_drive and not on_local)


def try_sync_hydrate_partition(
    handlers: Any,
    *,
    partition_id: str,
    message: str = "",
    max_mb: int | None = None,
) -> dict[str, Any]:
    """Pull a partition from Drive when small enough for synchronous desk hydrate."""
    repo_root = Path(handlers.gateway.repo_root).resolve()
    if not partition_id:
        return {"skipped": True, "reason": "no_partition_id"}

    from scripts.research_data_mcp.collection_resolve import partition_by_id

    part = partition_by_id(repo_root, partition_id) or {}
    plan = build_hydrate_plan(repo_root, partition_id=partition_id, message=message)
    if plan.get("skip_reason"):
        return {"skipped": True, "reason": plan["skip_reason"], "partition_id": partition_id}

    scope = str(plan.get("scope") or "full")
    cap = max_mb if max_mb is not None else DEFAULT_SYNC_HYDRATE_MAX_MB
    drive_mb = _partition_drive_mb(part)
    if scope == "full" and drive_mb is not None and drive_mb > cap:
        return {
            "skipped": True,
            "reason": "partition_too_large_for_sync",
            "partition_id": partition_id,
            "drive_mb": round(drive_mb, 1),
            "sync_cap_mb": cap,
            "hydrate_plan": plan,
            "note": "Submit hydrate_plan via yzu_submit_job or research_collection_hydrate(async=True).",
        }

    try:
        result = execute_hydrate(repo_root, plan)
        return {
            "partition_id": partition_id,
            "scope": scope,
            "sync": True,
            "result": result,
            "local_ready": bool(result.get("local_ready")),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "partition_id": partition_id,
            "sync": True,
            "error": str(exc)[:400],
            "hydrate_plan": plan,
        }


def resolve_analyze_handle(*, dataset_id: str = "", top: dict[str, Any] | None = None) -> str:
    if dataset_id:
        return f"dataset:{dataset_id}"
    top = top or {}
    if top.get("dataset_id"):
        return f"dataset:{top['dataset_id']}"
    if top.get("handle"):
        return str(top["handle"])
    job_id = str(top.get("job_id") or top.get("scrape_job_id") or "")
    if job_id:
        return f"scrape:{job_id}"
    doi = str(top.get("doi") or "")
    if doi.startswith("10."):
        return f"doi:{doi}"
    return ""


def run_bounded_analyze(
    handlers: Any,
    *,
    query: str,
    dataset_id: str = "",
    handle: str = "",
    top: dict[str, Any] | None = None,
    row_cap: int = 2000,
) -> dict[str, Any]:
    from scripts.research_data_mcp.procurement_analyze import analyze_procured

    handle = handle or resolve_analyze_handle(dataset_id=dataset_id, top=top)
    if not handle:
        return {"skipped": True, "reason": "no_analyze_handle"}
    try:
        out = analyze_procured(
            handlers.gateway,
            handle=handle,
            question=query.strip(),
            row_cap=row_cap,
        )
        return {"handle": handle, **out}
    except Exception as exc:  # noqa: BLE001
        return {"handle": handle, "error": str(exc)[:400]}
