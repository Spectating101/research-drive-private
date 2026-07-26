#!/usr/bin/env python3
"""Truthful /health UI projection for Header, Settings, and Resources."""

from __future__ import annotations

from scripts.research_data_mcp.desk_health_projection import build_health_projection


def test_healthy_facts_project_ok_never_demo_or_degraded():
    health = {
        "status": "ok",
        "datasets": 12,
        "desk": {
            "composer_configured": True,
            "composer_status": "ready",
            "mcp_tools": {"total": 40},
            "gdrive": {"ok": True, "ready": True, "drive_root": "gdrive:Research"},
            "jobs": {"pending_approval": 0, "failed_recent": 0},
            "storage_tiers": {"hot": {"headroom_ok": True, "used_pct": 40}},
        },
        "cluster": {"registry_datasets": 12},
    }
    proj = build_health_projection(health)
    assert proj["desk_status"] == "ok"
    assert proj["status"] == "ok"
    assert proj["desk_status"] not in {"demo", "degraded"}
    assert proj["components"]["api"]["ok"] is True
    assert proj["components"]["composer"]["ok"] is True
    assert proj["components"]["registry"]["ok"] is True
    assert proj["components"]["gdrive"]["ok"] is True
    assert "demo" not in str(proj).lower() or proj["desk_status"] != "demo"


def test_nvme_headroom_failure_is_degraded_from_facts():
    health = {
        "status": "degraded",
        "datasets": 3,
        "desk": {
            "composer_configured": True,
            "jobs": {"pending_approval": 2, "failed_recent": 0},
            "storage_tiers": {
                "hot": {"headroom_ok": False, "free_gb": 2, "required_min_gb": 20, "used_pct": 95}
            },
            "ops_warnings": ["nvme_headroom: 2 GB free < min 20 GB"],
            "gdrive": {"ok": True},
        },
    }
    proj = build_health_projection(health)
    assert proj["desk_status"] == "degraded"
    assert proj["status"] == "degraded"
    assert proj["components"]["storage_hot"]["ok"] is False
    assert proj["components"]["storage_hot"]["status"] == "degraded"


def test_pending_approval_alone_does_not_force_degraded_or_demo():
    health = {
        "status": "ok",
        "datasets": 5,
        "desk": {
            "composer_configured": False,
            "composer_status": "direct",
            "jobs": {"pending_approval": 4, "failed_recent": 0},
            "storage_tiers": {"hot": {"headroom_ok": True}},
            "ops_warnings": ["pending_approval=4"],
            "gdrive": {"rclone_installed": True, "ready": None, "probe_skipped": "non_live_fast_path"},
        },
    }
    proj = build_health_projection(health)
    assert proj["desk_status"] == "ok"
    assert proj["status"] == "ok"
    assert proj["desk_status"] != "demo"
    assert proj["components"]["composer"]["ok"] is False
    assert proj["components"]["composer"]["status"] == "needs_key"
    assert proj["components"]["jobs"]["pending_approval"] == 4


def test_empty_registry_projects_empty_not_demo():
    health = {
        "status": "ok",
        "datasets": 0,
        "desk": {
            "composer_configured": True,
            "jobs": {},
            "storage_tiers": {"hot": {"headroom_ok": True}},
            "gdrive": {"ok": True},
        },
        "cluster": {"registry_datasets": 0},
    }
    proj = build_health_projection(health)
    assert proj["desk_status"] == "empty"
    assert proj["status"] == "ok"
    assert proj["desk_status"] != "demo"
    assert proj["components"]["registry"]["status"] == "empty"


def test_desk_health_attaches_projection(monkeypatch):
    from pathlib import Path
    from unittest.mock import MagicMock

    from scripts.research_data_mcp.gateway import ResearchDataGateway

    monkeypatch.setattr(
        "scripts.research_data_mcp.desk_brain.composer_runtime_status",
        lambda repo_root=None: {
            "brain": "direct",
            "composer_configured": False,
            "composer_status": "direct",
        },
    )
    monkeypatch.setattr(
        "scripts.research_data_mcp.storage_tiers.storage_tiers_status",
        lambda _root: {
            "canonical": {
                "quota_tb": 1,
                "pool_tb": 1,
                "label": "test",
                "drive_root": "/tmp",
                "role": "canonical",
                "used_tb": 0,
            },
            "cache": {},
            "hot": {"headroom_ok": True, "used_pct": 10},
        },
    )
    monkeypatch.setattr("scripts.research_data_mcp.desk_auth.access_token_required", lambda: False)
    monkeypatch.setattr("scripts.research_data_mcp.llm_client.llm_configured", lambda: False)

    gateway = MagicMock()
    gateway.repo_root = Path(".")
    gateway.orchestrator = MagicMock()
    gateway.orchestrator.stats.return_value = {"pending_approval": 0, "failed_recent": 0}
    gateway.orchestrator.cfg = {"storage": {}}
    gateway._serve_ui = False
    gateway.inventory_summary = MagicMock(
        return_value={
            "totals": {"registered": 2, "visible_to_desk": 2, "excluded_operational_test": 0},
            "by_analysis_readiness": {"registered": {}},
            "by_materialization_query_ready": {"registered": {}},
            "registry_revision": {"fingerprint": "test"},
        }
    )
    gateway.engine = MagicMock()
    gateway.engine.list_datasets.return_value = [{"dataset_id": "a"}, {"dataset_id": "b"}]
    gateway.platform_state = MagicMock(return_value={"found": False})

    out = ResearchDataGateway.desk_health(gateway, live=False)
    assert "projection" in out
    assert out["projection"]["desk_status"] in {"ok", "empty", "degraded"}
    assert out["projection"]["desk_status"] != "demo"
    assert out["status"] != "demo"
    assert out["projection"]["components"]["api"]["ok"] is True
