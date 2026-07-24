#!/usr/bin/env python3
"""Focused worker-honesty: stale is not available; fresh remains available."""

from __future__ import annotations

from scripts.research_data_mcp.desk_resources import _windows_lab_worker_rollup
from scripts.yzu_cluster.api import _effective_worker_status


def test_effective_status_keeps_runtime_stale_not_idle_or_online() -> None:
    for stored in ("online", "idle", "ready"):
        honesty = _effective_worker_status(
            inventory_status="joined",
            runtime_worker={
                "id": "windows-01",
                "status": "stale",
                "stored_status": stored,
                "freshness": {"state": "stale", "age_seconds": 3600},
            },
        )
        assert honesty["effective_status"] == "stale", stored


def test_effective_status_fresh_workers_remain_claimable() -> None:
    online = _effective_worker_status(
        inventory_status="joined",
        runtime_worker={
            "id": "windows-01",
            "status": "online",
            "stored_status": "online",
            "freshness": {"state": "fresh", "age_seconds": 12},
        },
    )
    idle = _effective_worker_status(
        inventory_status="joined",
        runtime_worker={
            "id": "windows-02",
            "status": "idle",
            "stored_status": "idle",
            "freshness": {"state": "fresh", "age_seconds": 40},
        },
    )
    assert online["effective_status"] == "online"
    assert idle["effective_status"] == "idle"


def test_stale_windows_workers_not_available() -> None:
    soft_idle = [
        {
            "hostname": f"win-{i}",
            "status": "idle",
            "inventory_status": "joined",
            "freshness": {"state": "stale", "age_seconds": 3600},
        }
        for i in range(3)
    ]
    explicit = [
        {
            "hostname": f"win-{i}",
            "status": "stale",
            "inventory_status": "joined",
            "freshness": {"state": "stale", "age_seconds": 7200},
        }
        for i in range(3)
    ]
    for nodes in (soft_idle, explicit):
        rollup = _windows_lab_worker_rollup(nodes)
        assert rollup["stale"] == 3
        assert rollup["idle"] == 0
        assert rollup["online"] == 0
        assert rollup["available"] == 0


def test_fresh_windows_workers_remain_available() -> None:
    nodes = [
        {
            "hostname": "win-a",
            "status": "online",
            "freshness": {"state": "fresh", "age_seconds": 12},
        },
        {
            "hostname": "win-b",
            "status": "idle",
            "freshness": {"state": "fresh", "age_seconds": 40},
        },
        {
            "hostname": "win-c",
            "status": "joined_unseen",
            "freshness": None,
        },
    ]
    rollup = _windows_lab_worker_rollup(nodes)
    assert rollup["online"] == 1
    assert rollup["idle"] == 1
    assert rollup["available"] == 2
    assert rollup["joined_unseen"] == 1
    assert rollup["stale"] == 0
