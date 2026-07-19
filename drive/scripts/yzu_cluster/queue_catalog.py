#!/usr/bin/env python3
"""Collection queue catalog for YZU."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_queue(repo_root: Path, queue_path: str | Path | None = None) -> dict[str, Any]:
    path = repo_root / (queue_path or "config/data_collection_queue.json")
    return json.loads(path.read_text(encoding="utf-8"))


def list_tasks(repo_root: Path, *, enabled_only: bool = False, runnable_only: bool = False) -> list[dict[str, Any]]:
    queue = load_queue(repo_root)
    rows: list[dict[str, Any]] = []
    for task in sorted(queue.get("tasks", []), key=lambda row: int(row.get("priority", 9999))):
        item = {
            "id": task.get("id"),
            "title": task.get("title", ""),
            "enabled": bool(task.get("enabled", False)),
            "credential_required": bool(task.get("credential_required", False)),
            "priority": int(task.get("priority", 9999)),
            "output_hint": task.get("output_hint", ""),
            "estimated_runtime": task.get("estimated_runtime", ""),
        }
        item["runnable"] = item["enabled"] and not item["credential_required"] and bool(task.get("command"))
        if enabled_only and not item["enabled"]:
            continue
        if runnable_only and not item["runnable"]:
            continue
        rows.append(item)
    return rows
