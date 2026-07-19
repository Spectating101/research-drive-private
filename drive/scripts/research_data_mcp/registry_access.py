#!/usr/bin/env python3
"""Infer registry access tier for Composer — honest query vs catalog-only."""

from __future__ import annotations

from pathlib import Path
from typing import Any

QUERY_INSTANT = "query_instant"
QUERY_GUARDED = "query_guarded"
CATALOG_ONLY = "catalog_only"
JOB_ONLY = "job_only"
METADATA_SEARCH = "metadata_search"

_LOCAL_SAMPLE_BACKENDS = frozenset(
    {
        "local_json_glob",
        "local_json_file",
        "local_csv_file",
        "local_file",
        "local_parquet_panel",
    }
)


def local_data_ready(row: dict[str, Any], repo_root: Path | None) -> bool:
    return _local_data_ready(row, repo_root)


def _local_data_ready(row: dict[str, Any], repo_root: Path | None) -> bool:
    if repo_root is None:
        return False
    from scripts.research_data_mcp.procurement_fast import local_path_has_data

    pattern = str(row.get("local_path") or row.get("local_root") or "").strip()
    return bool(pattern and local_path_has_data(repo_root, pattern))


def access_tier(row: dict[str, Any], *, repo_root: Path | None = None) -> str:
    readiness = str(row.get("analysis_readiness") or "")
    backend = str(row.get("backend") or "")
    if readiness == "instant":
        return QUERY_INSTANT
    if readiness in {"dry_run_before_execution", "minutes_rate_limited", "procurement_planning"}:
        return QUERY_GUARDED
    if readiness in {"sample_now_full_later", "metadata_search"} and backend in _LOCAL_SAMPLE_BACKENDS:
        if _local_data_ready(row, repo_root):
            return QUERY_INSTANT
    if backend in {"local_file", "local_csv_file"} and _local_data_ready(row, repo_root):
        return QUERY_INSTANT
    if readiness == "metadata_search":
        return METADATA_SEARCH
    if backend in {"local_file", "local_csv_file"}:
        return CATALOG_ONLY
    return CATALOG_ONLY


def access_tier_note(tier: str) -> str:
    return {
        QUERY_INSTANT: "Safe to call research_query_dataset for sample rows (use include_payload=true for JSON trees).",
        QUERY_GUARDED: "Call research_query_dataset with action=dry_run or guarded params first.",
        METADATA_SEARCH: "Describe/card or research_analyze_dataset when local bytes exist; else acquire.",
        CATALOG_ONLY: "Path reference — use research_open_dataset or research_analyze_dataset.",
        JOB_ONLY: "Launch via yzu_submit_job, collection queue task, or registered pipeline.",
    }.get(tier, "Check research_describe_dataset.")


def describe_access(gateway: Any, dataset_id: str) -> dict[str, Any]:
    row = gateway.describe_dataset(dataset_id)
    repo_root = Path(getattr(gateway, "repo_root", "."))
    tier = access_tier(row, repo_root=repo_root)
    return {
        "dataset_id": dataset_id,
        "access_tier": tier,
        "note": access_tier_note(tier),
        "analysis_readiness": row.get("analysis_readiness"),
        "backend": row.get("backend"),
        "limitations": row.get("limitations"),
        "local_ready": _local_data_ready(row, repo_root),
    }
