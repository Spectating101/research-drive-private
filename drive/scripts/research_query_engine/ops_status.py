#!/usr/bin/env python3
"""Operational status helpers for collection queue and local DataCite harvest."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def collection_queue_status(repo_root: Path) -> dict[str, Any]:
    status_dir = repo_root / "data_lake/data_collection_queue"
    log_dir = repo_root / "logs/data_collection_queue"
    queue_config = repo_root / "config/data_collection_queue.json"
    out: dict[str, Any] = {"status_dir": str(status_dir)}

    if queue_config.exists():
        cfg = json.loads(queue_config.read_text(encoding="utf-8"))
        tasks = cfg.get("tasks") or []
        out["queue_name"] = cfg.get("name")
        out["task_count"] = len(tasks)
        out["enabled_tasks"] = [t.get("id") for t in tasks if t.get("enabled")]

    lock = status_dir / "queue.lock"
    if lock.exists():
        try:
            obj = json.loads(lock.read_text(encoding="utf-8"))
            pid = int(obj.get("pid", 0))
            out["lock"] = {
                "pid": pid,
                "alive": pid_alive(pid),
                "started_at": obj.get("started_at"),
            }
        except Exception as exc:
            out["lock"] = {"error": f"{type(exc).__name__}: {exc}"}
    else:
        out["lock"] = None

    latest = status_dir / "latest.json"
    if latest.exists():
        try:
            out["latest"] = json.loads(latest.read_text(encoding="utf-8"))
        except Exception:
            out["latest_raw"] = latest.read_text(encoding="utf-8", errors="replace")[:4000]

    status = status_dir / "status.jsonl"
    if status.exists():
        lines = status.read_text(encoding="utf-8", errors="replace").splitlines()
        out["status_line_count"] = len(lines)
        out["recent_status"] = [json.loads(line) for line in lines[-8:] if line.strip()]

    if log_dir.exists():
        out["recent_logs"] = [
            {"path": str(p.relative_to(repo_root)), "bytes": p.stat().st_size}
            for p in sorted(log_dir.glob("*.log"), key=lambda item: item.stat().st_mtime)[-8:]
        ]
    return out


def datacite_local_harvest_status(repo_root: Path, lane: str = "") -> dict[str, Any]:
    root = repo_root / "data_lake/dataset_catalog/index_v3"
    out: dict[str, Any] = {"local_root": str(root), "lanes": []}
    if not root.exists():
        out["error"] = "missing local DataCite index root"
        return out

    manifest = root / "full_index_manifest.json"
    if manifest.exists():
        try:
            out["full_index_manifest"] = json.loads(manifest.read_text(encoding="utf-8"))
        except Exception:
            out["full_index_manifest_error"] = "unreadable"

    lane_dirs = sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith("."))
    if lane.strip():
        lane_dirs = [p for p in lane_dirs if p.name == lane.strip()]

    total_shards = 0
    for lane_dir in lane_dirs:
        checkpoint_path = lane_dir / "datacite.checkpoint.json"
        heartbeat_path = lane_dir / "datacite.heartbeat.json"
        shard_files = list(lane_dir.glob("datacite_*.jsonl.gz"))
        total_shards += len(shard_files)
        lane_info: dict[str, Any] = {
            "lane": lane_dir.name,
            "local_shard_files": len(shard_files),
            "local_shard_bytes": sum(p.stat().st_size for p in shard_files),
        }
        if checkpoint_path.exists():
            try:
                lane_info["checkpoint"] = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            except Exception as exc:
                lane_info["checkpoint_error"] = str(exc)
        if heartbeat_path.exists():
            try:
                lane_info["heartbeat"] = json.loads(heartbeat_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        out["lanes"].append(lane_info)

    out["lane_count"] = len(out["lanes"])
    out["total_local_shard_files"] = total_shards
    out["note"] = (
        "Primary shard archive may be on GDrive/cluster; local tree often holds checkpoints only."
    )
    return out
