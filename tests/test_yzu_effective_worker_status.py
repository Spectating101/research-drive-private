#!/usr/bin/env python3
"""Runtime stale must not become desk idle/available."""

from __future__ import annotations

from scripts.yzu_cluster.api import _effective_worker_status


def test_stale_runtime_stays_stale_not_idle() -> None:
    honesty = _effective_worker_status(
        inventory_status="joined",
        runtime_worker={
            "id": "windows-01",
            "status": "stale",
            "stored_status": "idle",
            "freshness": {"state": "stale", "age_seconds": 3600.0, "stale_after_seconds": 300},
        },
    )
    assert honesty["effective_status"] == "stale"


def test_fresh_runtime_is_online() -> None:
    honesty = _effective_worker_status(
        inventory_status="joined",
        runtime_worker={
            "id": "windows-02",
            "status": "online",
            "stored_status": "online",
            "freshness": {"state": "fresh", "age_seconds": 12.0, "stale_after_seconds": 300},
        },
    )
    assert honesty["effective_status"] == "online"


def test_missing_runtime_is_joined_unseen() -> None:
    honesty = _effective_worker_status(inventory_status="joined", runtime_worker=None)
    assert honesty["effective_status"] == "joined_unseen"
