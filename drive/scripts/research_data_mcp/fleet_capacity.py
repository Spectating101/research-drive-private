#!/usr/bin/env python3
"""Measured worker fleet capacity — L0 hands for parallel planning.

Composer plans collection sequentially because nothing tells it a fleet
exists. This module measures online workers, cores, free disk and the
capability union so grounding can state what can run in parallel.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any

STALE_HEARTBEAT_SECONDS = 900


def _jobs_db_path() -> str:
    root = os.environ.get("YZU_RUNTIME_DRIVE_ROOT") or os.environ.get("SHARPE_DRIVE_ROOT") or ""
    if root:
        return os.path.join(root, "data_lake", "yzu_cluster", "jobs", "jobs.sqlite3")
    here = os.path.dirname(os.path.abspath(__file__))
    drive = os.path.abspath(os.path.join(here, "..", ".."))
    return os.path.join(drive, "data_lake", "yzu_cluster", "jobs", "jobs.sqlite3")


def _age_seconds(stamp: str) -> float | None:
    text = str(stamp or "").strip()
    if not text:
        return None
    try:
        when = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - when).total_seconds()


def measure_fleet(db_path: str | None = None) -> dict[str, Any]:
    path = db_path or _jobs_db_path()
    out: dict[str, Any] = {
        "available": False,
        "workers": [],
        "online_count": 0,
        "total_cores": 0.0,
        "total_free_disk_mb": 0.0,
        "capabilities": [],
        "parallel_slots": 0,
    }
    if not os.path.exists(path):
        return out
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        rows = con.execute(
            "select worker_id, pool, status, capabilities, capacity, heartbeat_at from cluster_workers"
        ).fetchall()
        con.close()
    except sqlite3.Error:
        return out

    caps: set[str] = set()
    for worker_id, pool, status, capabilities, capacity, heartbeat in rows:
        try:
            cap_list = json.loads(capabilities or "[]")
        except (TypeError, ValueError):
            cap_list = []
        try:
            cap = json.loads(capacity or "{}")
        except (TypeError, ValueError):
            cap = {}
        age = _age_seconds(heartbeat)
        fresh = age is not None and age <= STALE_HEARTBEAT_SECONDS
        online = str(status or "").strip().lower() == "online" and fresh
        entry = {
            "worker_id": worker_id,
            "pool": pool,
            "status": status,
            "online": online,
            "heartbeat_age_seconds": age,
            "cpu_cores": float(cap.get("cpu_cores") or 0),
            "free_disk_mb": float(cap.get("disk_mb") or 0),
            "capabilities": sorted(str(c) for c in cap_list if c),
        }
        out["workers"].append(entry)
        if online:
            out["online_count"] += 1
            out["total_cores"] += entry["cpu_cores"]
            out["total_free_disk_mb"] += entry["free_disk_mb"]
            caps.update(entry["capabilities"])

    out["capabilities"] = sorted(caps)
    out["parallel_slots"] = out["online_count"]
    out["available"] = out["online_count"] > 0
    return out


def workers_for_capability(fleet: dict[str, Any], capability: str) -> list[str]:
    want = str(capability or "").strip().lower()
    if not want:
        return []
    return [
        w["worker_id"]
        for w in fleet.get("workers") or []
        if w.get("online") and want in [c.lower() for c in w.get("capabilities") or []]
    ]


def fleet_facts_line(fleet: dict[str, Any] | None = None) -> str:
    fleet = fleet if isinstance(fleet, dict) else measure_fleet()
    if not fleet.get("available"):
        return "Worker fleet: no online workers measured — plan collection as single-node."
    http = workers_for_capability(fleet, "http")
    disk_gb = fleet.get("total_free_disk_mb", 0.0) / 1024.0
    parts = [
        f"Worker fleet: {fleet['online_count']} online",
        f"{fleet['total_cores']:.0f} cores",
        f"{disk_gb:,.0f} GB free across the fleet",
    ]
    line = " · ".join(parts) + "."
    if len(http) > 1:
        line += (
            f" {len(http)} workers can run http collection concurrently"
            f" ({', '.join(http)}) — split multi-file or multi-source collection across them"
            " instead of planning it serially."
        )
    return line
