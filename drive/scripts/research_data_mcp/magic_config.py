#!/usr/bin/env python3
"""Load magic-button procurement policy from config/procurement_magic.json."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def load_magic_config(repo_root: Path) -> dict[str, Any]:
    path = repo_root / "config/procurement_magic.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _runtime_minutes(estimated_runtime: str) -> int | None:
    text = (estimated_runtime or "").lower()
    if "under 1 minute" in text or "<1 minute" in text:
        return 1
    match = re.search(r"(\d+)\s*-\s*(\d+)\s*minute", text)
    if match:
        return int(match.group(2))
    match = re.search(r"(\d+)\s*minute", text)
    if match:
        return int(match.group(1))
    if "hour" in text:
        return 999
    return None


def is_datacite_collect_plan(plan: dict[str, Any]) -> bool:
    return bool(plan.get("datacite_doi")) and str(plan.get("job_type") or "") == "http_manifest"


def is_trusted_plan(plan: dict[str, Any], config: dict[str, Any], *, queue_tasks: list[dict[str, Any]] | None = None) -> bool:
    if not plan or not plan.get("launchable"):
        return False
    # Collects always require explicit researcher approve — never "trusted" auto.
    if is_datacite_collect_plan(plan):
        return False
    if str(plan.get("job_type") or "") in {"http_manifest", "scraper_run"}:
        return False
    policy = config.get("auto_approve") or {}
    job_type = str(plan.get("job_type") or "")
    if job_type in set(policy.get("job_types") or []):
        if job_type == "harvest_shard":
            return str(plan.get("action") or "") in set(policy.get("harvest_shard_actions") or ["status"])
        return True
    if job_type == "collection_queue_task":
        task_id = str(plan.get("task_id") or "")
        if task_id in set(policy.get("queue_task_ids") or []):
            return True
        max_minutes = int(policy.get("queue_task_max_runtime_minutes") or 0)
        if max_minutes and queue_tasks:
            task = next((row for row in queue_tasks if row.get("id") == task_id), None)
            if task:
                minutes = _runtime_minutes(str(task.get("estimated_runtime") or ""))
                if minutes is not None and minutes <= max_minutes:
                    return True
    if job_type == "registered_pipeline":
        pipeline_id = str(plan.get("pipeline_id") or "")
        if pipeline_id in set(policy.get("pipeline_ids") or []):
            return True
    return False


def should_auto_execute(plan: dict[str, Any], config: dict[str, Any]) -> bool:
    # Never auto-execute acquisition jobs — approve_collect / human approve only.
    if is_datacite_collect_plan(plan):
        return False
    if str(plan.get("job_type") or "") in {"http_manifest", "scraper_run"}:
        return False
    job_type = str(plan.get("job_type") or "")
    allowed = set((config.get("execute") or {}).get("auto_execute_job_types") or [])
    if job_type not in allowed:
        return False
    if job_type == "harvest_shard":
        actions = set((config.get("auto_approve") or {}).get("harvest_shard_actions") or ["status"])
        return str(plan.get("action") or "") in actions
    return True


def wants_discovery(message: str, config: dict[str, Any]) -> bool:
    discovery = config.get("discovery") or {}
    if not discovery.get("enabled", True):
        return False
    lower = message.lower()
    keywords = discovery.get("trigger_keywords") or []
    return any(keyword in lower for keyword in keywords)
