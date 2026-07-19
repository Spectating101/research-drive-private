#!/usr/bin/env python3
"""Professor-facing pipeline difficulty tiers — derived from registry access, not query regex."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from scripts.research_data_mcp.registry_access import QUERY_GUARDED, QUERY_INSTANT
from sharpe_kernel.paths import repo_root_from_file

PIPELINE_TIERS: dict[str, dict[str, Any]] = {
    "T1_instant": {
        "label": "Instant registry query",
        "professor_analogy": "Registry panel with instant query backend",
        "stack_depth": "research_query_dataset(limit=N)",
        "typical_latency": "sub-second to few seconds",
    },
    "T2_vault": {
        "label": "Vault partition / local corpus",
        "professor_analogy": "Partition holdings on Drive or local cache",
        "stack_depth": "describe + partition browse; optional plan_collect for refresh",
        "typical_latency": "seconds (metadata); hours-days if refresh",
    },
    "T3_guarded_remote": {
        "label": "Guarded BigQuery / remote SQL",
        "professor_analogy": "Guarded remote SQL (BigQuery) without full local clone",
        "stack_depth": "dry_run → confirm run → optional archive to GDrive",
        "typical_latency": "seconds dry-run; minutes guarded export",
    },
    "T4_procure_miss": {
        "label": "Hard miss procurement",
        "professor_analogy": "Obscure paper URL, niche panel not in registry",
        "stack_depth": "web_discover → probe → plan_collect",
        "typical_latency": "minutes planning; depends on source",
    },
    "T5_job_acquire": {
        "label": "Cluster job + vault archive",
        "professor_analogy": "Spectator scrape, long backfill, GDrive promotion",
        "stack_depth": "yzu_submit_job → worker → archive_upload",
        "typical_latency": "minutes to hours",
    },
}


@lru_cache(maxsize=1)
def load_pipeline_benchmark_cases() -> list[dict[str, Any]]:
    path = repo_root_from_file(__file__) / "config/procurement_benchmark_cases.json"
    if not path.is_file():
        return []
    doc = json.loads(path.read_text(encoding="utf-8"))
    return list(doc.get("composer_workflow_cases") or doc.get("pipeline_tier_cases") or [])


# Backward-compatible name for benchmark scripts.
def pipeline_benchmark_cases() -> list[dict[str, Any]]:
    return load_pipeline_benchmark_cases()


def tier_from_access_tier(access_tier: str) -> str:
    if access_tier == QUERY_INSTANT:
        return "T1_instant"
    if access_tier == QUERY_GUARDED:
        return "T3_guarded_remote"
    return "T2_vault"


def expected_tier_for_query(query: str, *, profile: dict[str, Any] | None = None) -> str:
    """Benchmark helper only — production tiers come from observed_pipeline_tier + describe."""
    _ = query, profile
    return "T2_vault"


def observed_pipeline_tier(workflow: dict[str, Any], followthrough: dict[str, Any]) -> str:
    if followthrough.get("collect_submit", {}).get("ok") or followthrough.get("collect_job_id"):
        return "T5_job_acquire"
    if followthrough.get("bigquery_dry_run") or followthrough.get("sample_query", {}).get("meta", {}).get("mode") == "dry_run":
        bq_meta = (followthrough.get("bigquery_dry_run") or followthrough.get("sample_query") or {}).get("meta") or {}
        if bq_meta.get("within_execution_guard") is not False:
            return "T3_guarded_remote"
    index_miss = bool(workflow.get("index_miss"))
    strong_local = bool(workflow.get("strong_local_hit"))
    if index_miss and (
        followthrough.get("plan_collect")
        or followthrough.get("probe")
        or (workflow.get("web_discover") or {}).get("results")
    ):
        return "T4_procure_miss"
    rows = len((followthrough.get("sample_query") or {}).get("rows") or [])
    if rows > 0:
        return "T1_instant"
    top = ((workflow.get("discover") or {}).get("candidates") or [{}])[0]
    if strong_local:
        for cand in (workflow.get("discover") or {}).get("candidates") or []:
            if cand.get("dataset_id"):
                top = cand
                break
    access_tier = str(top.get("access_tier") or followthrough.get("describe", {}).get("access_tier") or "")
    if access_tier:
        return tier_from_access_tier(access_tier)
    if (workflow.get("discover") or {}).get("bigquery_hints"):
        return "T3_guarded_remote"
    if bool(top.get("local_ready")) and str(top.get("collect_via") or "") == "local_open":
        return "T2_vault"
    if top.get("partition_id") or str(top.get("kind") or "") == "partition":
        return "T2_vault"
    if workflow.get("ladder_reached") == "web_discover" and index_miss and not strong_local:
        return "T4_procure_miss"
    return "T2_vault"


def tier_summary(tier_id: str) -> dict[str, Any]:
    base = dict(PIPELINE_TIERS.get(tier_id) or {})
    base["tier_id"] = tier_id
    return base
