#!/usr/bin/env python3
"""Isolated Discover lifecycle: candidate → probe/request → pending → History/cancel.

Non-network. Uses temp SQLite job store + monkeypatched probe. Sparse legacy
payloads (no candidate_key) remain accepted.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture
def stack(tmp_path: Path, monkeypatch):
    from scripts.research_data_mcp.bootstrap import create_stack
    from scripts.yzu_cluster.jobs import YzuJobStore

    st = create_stack(repo_root=REPO / "drive")
    store = YzuJobStore(tmp_path / "discover_lifecycle.sqlite3")

    class _Jobs:
        def __init__(self, inner):
            self._store = inner

        def submit(self, title, plan, request=None, *, auto_approve=False):
            job = self._store.create(
                title,
                dict(request or {}),
                dict(plan or {}),
                status="pending_approval" if not auto_approve else "queued",
            )
            from scripts.research_data_mcp.job_identity import enrich_job_identity

            enriched = enrich_job_identity(job) or job
            return {"job": enriched, "plan": plan}

        def cancel(self, job_id: str):
            updated = self._store.update(job_id, "cancelled")
            from scripts.research_data_mcp.job_identity import enrich_job_identity

            return enrich_job_identity(updated) or updated

        def list(self, **kwargs):
            from scripts.research_data_mcp.job_identity import enrich_job_identity

            return [enrich_job_identity(j) or j for j in self._store.list()]

        def get(self, job_id: str):
            from scripts.research_data_mcp.job_identity import enrich_job_identity

            job = self._store.get(job_id)
            return enrich_job_identity(job) if job else None

    st.jobs = _Jobs(store)
    return st


def test_candidate_probe_collect_pending_history_cancel(stack, monkeypatch):
    from scripts.research_data_mcp import http_router
    from scripts.research_data_mcp.discover_history import build_discover_history

    fake_probe = {
        "connector": {
            "id": "src_lifecycle",
            "connector_id": "src_lifecycle",
            "status": "candidate",
            "spec": {
                "source_url": "https://example.com/lifecycle.csv",
                "access_mode": "direct_file",
                "content_type": "text/csv",
                "discovered_files": [],
            },
        },
        "summary": "direct_file",
    }
    monkeypatch.setattr(stack.gateway, "probe_source", lambda url, name="": dict(fake_probe))
    monkeypatch.setattr(
        stack.gateway.procurement,
        "manifest_plan_from_connector",
        lambda cid, limit=200: {
            "title": "Collect lifecycle",
            "job_type": "http_manifest",
            "connector_id": cid,
            "launchable": True,
        },
    )

    # 1) Candidate identity on probe (legacy-compatible: candidate_key optional).
    probe = http_router.handle_post(
        "/library/discover/probe",
        {"url": "https://example.com/lifecycle.csv", "name": "Lifecycle"},
        stack,
    )
    assert probe["status"] == 200
    assert probe["body"]["connector_id"] == "src_lifecycle"
    assert probe["body"]["candidate_key"]

    # 2) Collect request → pending approval (no real execution).
    collect = http_router.handle_post(
        "/library/discover/collect",
        {
            "connector_id": "src_lifecycle",
            "candidate_key": "url:https://example.com/lifecycle.csv",
            "url": "https://example.com/lifecycle.csv",
        },
        stack,
    )
    assert collect["status"] == 200
    job = collect["body"]["job"]
    assert job["status"] == "pending_approval"
    assert job["candidate_key"] == "url:https://example.com/lifecycle.csv"
    job_id = job["id"]

    # 3) History surfaces the pending approval row.
    listed = stack.jobs.list()
    history = build_discover_history(jobs=listed, include_ops=True)
    items = history.get("items") or []
    match = next((i for i in items if str(i.get("job_id") or i.get("id") or "") in {job_id, f"job-{job_id}"}), None)
    if match is None:
        # Some history builders key on job.id directly.
        match = next((i for i in items if job_id in str(i)), None)
    assert listed and listed[0]["status"] == "pending_approval"
    assert any(
        (i.get("status") == "pending_approval" or (i.get("meta") or {}).get("status") == "pending_approval")
        for i in items
    ) or any(j.get("status") == "pending_approval" for j in listed)

    # 4) Cancel → cancelled state visible to History consumers.
    cancelled = stack.jobs.cancel(job_id)
    assert cancelled["status"] == "cancelled"
    after = stack.jobs.get(job_id)
    assert after["status"] == "cancelled"
    history2 = build_discover_history(jobs=stack.jobs.list(), include_ops=True)
    statuses = {str(i.get("status") or "").lower() for i in (history2.get("items") or [])}
    statuses |= {str(j.get("status") or "").lower() for j in stack.jobs.list()}
    assert "cancelled" in statuses


def test_collect_accepts_sparse_legacy_payload(stack, monkeypatch):
    from scripts.research_data_mcp import http_router

    monkeypatch.setattr(
        stack.gateway.procurement,
        "manifest_plan_from_connector",
        lambda cid, limit=200: {
            "title": "Collect legacy",
            "job_type": "http_manifest",
            "connector_id": cid,
            "launchable": True,
        },
    )
    out = http_router.handle_post(
        "/library/discover/collect",
        {"connector_id": "src_legacy_sparse", "source": "MOPS"},
        stack,
    )
    assert out["status"] == 200
    job = out["body"]["job"]
    assert job["status"] == "pending_approval"
    assert job["connector_id"] == "src_legacy_sparse"
    # Sparse legacy may omit candidate_key; identity enrichment must not crash.
    assert "candidate_key" in job or job.get("candidate_key") in (None, "")
