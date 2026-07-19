#!/usr/bin/env python3
"""Auto-approve policy for desk/chat procurement — safe job types only."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.research_data_mcp.magic_config import is_datacite_collect_plan, is_trusted_plan, load_magic_config

NEVER_AUTO_APPROVE = frozenset({"scraper_run", "registered_pipeline", "archive_upload"})


def load_governance(repo_root: Path) -> dict[str, Any]:
    path = repo_root / "config/procurement_governance.json"
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def should_auto_approve_plan(
    plan: dict[str, Any],
    repo_root: Path,
    *,
    orchestrator: Any | None = None,
) -> bool:
    """Return True when a chat-submitted job may launch without human approval."""
    if not plan or not plan.get("launchable"):
        return False

    job_type = str(plan.get("job_type") or "")
    magic_cfg = load_magic_config(repo_root)
    queue_tasks = orchestrator.queue_tasks(runnable_only=False) if orchestrator else None
    if job_type in NEVER_AUTO_APPROVE:
        if job_type == "registered_pipeline" and is_trusted_plan(plan, magic_cfg, queue_tasks=queue_tasks):
            return True
        if job_type == "scraper_run" and plan.get("agent_initiated"):
            auto = (magic_cfg.get("auto_approve") or {}).get("agent_spectator_scrape", True)
            url = str(plan.get("url") or "")
            script_key = str(plan.get("script_key") or "generic_url_scrape")
            if auto and url.startswith("http") and script_key in {"", "generic_url_scrape"}:
                return True
        return False

    governance = load_governance(repo_root)
    if not governance.get("auto_approve_chat_collect", True):
        return False

    if is_trusted_plan(plan, magic_cfg, queue_tasks=queue_tasks):
        return True

    if job_type == "http_manifest":
        if is_datacite_collect_plan(plan):
            return True
        if governance.get("auto_approve_public_http_manifest", True) and (
            plan.get("public_direct_url") or plan.get("local_collect")
        ):
            collect_class = str(plan.get("collect_class") or "")
            allowed = set(
                governance.get("auto_collect_classes")
                or ["public_government", "public_academic", "public_unknown"]
            )
            if collect_class in allowed or plan.get("public_direct_url"):
                return True
        return False

    if job_type == "source_probe":
        return job_type in set((magic_cfg.get("auto_approve") or {}).get("job_types") or [])

    if job_type == "bigquery_query":
        return bool(plan.get("dry_run", True)) and not bool(plan.get("execute"))

    return False
