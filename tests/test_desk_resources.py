#!/usr/bin/env python3
"""Tests for desk usage ledger and resources rollup."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def repo_tmp(tmp_path: Path) -> Path:
    (tmp_path / "config").mkdir(parents=True)
    (tmp_path / "config" / "desk_sources.json").write_text(
        json.dumps(
            {
                "layers": [{"id": "a"}, {"id": "b"}],
                "sources": [
                    {"id": "gdelt", "show_on_resources": True},
                    {"id": "web", "show_on_resources": True},
                    {"id": "hidden"},
                ],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "config" / "procurement_governance.json").write_text(
        json.dumps({"budgets": {"max_tavily_live_per_magic": 6}}),
        encoding="utf-8",
    )
    return tmp_path


def test_desk_usage_counters(repo_tmp: Path) -> None:
    from scripts.research_data_mcp.desk_usage import (
        record_bq_bytes,
        record_tavily_call,
        today_summary,
    )

    assert today_summary(repo_tmp)["tavily_calls"] == 0
    record_tavily_call(repo_root=repo_tmp)
    record_bq_bytes(1024**3, repo_root=repo_tmp)
    summary = today_summary(repo_tmp)
    assert summary["tavily_calls"] == 1
    assert summary["bq_bytes_billed"] == 1024**3
    assert summary["bq_gib_billed"] == 1.0


def test_curated_connect_counts(repo_tmp: Path) -> None:
    from scripts.research_data_mcp.desk_resources import _curated_connect_counts

    sources, layers = _curated_connect_counts(repo_tmp)
    assert sources == 2
    assert layers == 2


def test_desk_activity_and_period(repo_tmp: Path) -> None:
    from scripts.research_data_mcp.desk_activity import read_recent, record_activity, top_bq_drivers
    from scripts.research_data_mcp.desk_usage import period_summary, record_bq_bytes

    record_activity("query", "gdelt_asia_daily", repo_root=repo_tmp, bq_gib=1.5)
    record_bq_bytes(int(0.5 * 1024**3), repo_root=repo_tmp)
    events = read_recent(limit=5, repo_root=repo_tmp)
    assert len(events) == 1
    assert events[0]["action"] == "query"
    drivers = top_bq_drivers(repo_root=repo_tmp)
    assert drivers[0]["bq_gib"] == 1.5
    period = period_summary(days=7, repo_root=repo_tmp)
    assert period["totals"]["bq_gib_billed"] >= 0.5


def test_effective_status_keeps_runtime_stale_not_idle_or_online() -> None:
    """Stored online/idle must not beat freshness stale for desk honesty labels."""
    from scripts.yzu_cluster.api import _effective_worker_status

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
    from scripts.yzu_cluster.api import _effective_worker_status

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
    unseen = _effective_worker_status(inventory_status="joined", runtime_worker=None)
    assert online["effective_status"] == "online"
    assert idle["effective_status"] == "idle"
    assert unseen["effective_status"] == "joined_unseen"


def test_stale_windows_workers_joined_not_schedulable() -> None:
    """Freshness-stale agents may soft-label idle; rollup must not advertise them."""
    from scripts.research_data_mcp.desk_resources import _windows_lab_worker_rollup

    soft_idle = [
        {
            "hostname": f"win-{i}",
            "pool": "windows_lab",
            "status": "idle",  # soft label that must not become available
            "inventory_status": "joined",
            "freshness": {"state": "stale", "age_seconds": 3600},
        }
        for i in range(3)
    ]
    explicit = [
        {
            "hostname": f"win-{i}",
            "pool": "windows_lab",
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
        assert rollup["joined_unseen"] == 0


def test_fresh_windows_workers_remain_available() -> None:
    from scripts.research_data_mcp.desk_resources import _windows_lab_worker_rollup

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


def test_build_desk_resources_keeps_joined_but_not_available_when_runtime_stale(
    repo_tmp: Path, monkeypatch
) -> None:
    """Inventory joined stays; hero/compute available follows runtime freshness."""
    from unittest.mock import MagicMock

    from scripts.research_data_mcp import desk_resources

    stale_runtime_workers = [
        {
            "id": f"win-{i}",
            "pool": "windows_lab",
            "status": "stale",
            "freshness": {"state": "stale", "age_seconds": 7200},
        }
        for i in range(3)
    ]
    honesty_nodes = [
        {
            "hostname": f"win-{i}",
            "pool": "windows_lab",
            "status": "stale",
            "inventory_status": "joined",
            "freshness": {"state": "stale", "age_seconds": 7200},
        }
        for i in range(3)
    ]

    gateway = MagicMock()
    gateway.repo_root = repo_tmp
    gateway.desk_health.return_value = {
        "status": "ok",
        "desk": {
            "storage_tiers": {"canonical": {}, "hot": {}, "cache": {}},
            "worker_pools": {"busy": 0, "total": 3},
            "mcp_tools": {"total": 0},
            "composer_configured": True,
            "legacy_llm_configured": False,
            "gdrive": {"ok": True},
        },
    }
    gateway.list_credential_profiles.return_value = {"profiles": []}
    gateway.procurement_catalog.return_value = {"summary": {}}
    gateway.cluster_status.return_value = {
        "worker_pools": {"windows_lab": {"joined": 3, "total": 3}},
        "datacite": {},
        "gdelt": {},
        "controller": "optiplex-test",
    }
    gateway.orchestrator.stats.return_value = {
        "pending_approval": 0,
        "failed_recent": 0,
        "failed_actionable": 0,
        "failed_ops_noise": 0,
        "recent_days": 7,
    }
    gateway.orchestrator.runtime_health.return_value = {
        "cluster": {
            "workers": stale_runtime_workers,
            "usage": {},
            "worker_pools": {"windows_lab": {"total": 3, "online": 0, "stale": 3}},
        },
        "desk": {
            "jobs": {},
            "worker_pools": {"total": 3, "busy": 0, "stale": 3},
        },
    }
    gateway.ops_status.return_value = {"collection_queue": {}, "datacite_harvest": {}}
    gateway.list_campaigns.return_value = {"campaigns": []}
    gateway.faculty_profile.return_value = {"found": False}
    gateway.yzu.workers.return_value = {"windows_lab": honesty_nodes}

    monkeypatch.setattr(
        "scripts.research_data_mcp.bigquery_client.status",
        lambda: {"credentials": "missing"},
    )
    monkeypatch.setattr(desk_resources, "_count_tavily_keys", lambda: 0)
    monkeypatch.setattr(desk_resources, "_vault_used_tb_cached", lambda live=False: None)
    monkeypatch.setattr(desk_resources, "_curated_connect_payload", lambda *a, **k: {})
    monkeypatch.setattr(
        "scripts.research_data_mcp.desk_usage.today_summary",
        lambda *_a, **_k: {},
    )
    monkeypatch.setattr(
        "scripts.research_data_mcp.desk_usage.period_summary",
        lambda **_k: {"totals": {}},
    )
    monkeypatch.setattr(
        "scripts.research_data_mcp.desk_activity.read_recent",
        lambda **_k: [],
    )
    monkeypatch.setattr(
        "scripts.research_data_mcp.desk_activity.top_bq_drivers",
        lambda **_k: [],
    )

    payload = desk_resources.build_desk_resources(gateway, live=False)
    hero = payload["hero"]["workers"]
    compute = payload["compute"]["windows_lab"]
    runtime_workers = payload["runtime"]["cluster"]["workers"]

    assert hero["joined"] == 3
    assert compute["joined"] == 3
    assert hero["stale"] == 3
    assert compute["stale"] == 3
    assert hero["idle"] == 0
    assert hero["online"] == 0
    assert hero["available"] == 0
    assert compute["available"] == 0
    assert compute["idle"] == 0
    assert all(w["freshness"]["state"] == "stale" for w in runtime_workers)
