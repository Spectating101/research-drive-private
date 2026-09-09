"""Freeze contract for Synthesis Preview -> approval -> worker authority.

These tests cover the actual public gateway intention, the faculty HTTP action
forwarding, and the final worker-time revision check. A green browser mock alone
is not sufficient evidence for this boundary.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest


class _FakeJobs:
    def __init__(self) -> None:
        self.submitted: list[dict] = []
        self.by_id: dict[str, dict] = {}

    def submit(self, title, plan, request, auto_approve=False):
        assert auto_approve is False
        job_id = f"job-{len(self.submitted) + 1}"
        job = {
            "id": job_id,
            "status": "pending_approval",
            "title": title,
            "plan": plan,
            "request": request,
        }
        self.submitted.append(job)
        self.by_id[job_id] = job
        return {"job": job, "plan": plan}

    def get(self, job_id):
        return self.by_id[job_id]


def _repo(tmp_path: Path) -> tuple[Path, dict]:
    root = tmp_path / "repo"
    (root / "config").mkdir(parents=True)
    (root / "data").mkdir(parents=True)
    source = root / "data/input.csv"
    with source.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["asset", "week", "value"])
        writer.writeheader()
        for i in range(12):
            writer.writerow(
                {
                    "asset": "A" if i < 6 else "B",
                    "week": f"2026-W{1 + (i % 3)}",
                    "value": i + 1,
                }
            )
    (root / "config/research_query_registry.json").write_text(
        json.dumps(
            {
                "datasets": [
                    {
                        "dataset_id": "fixture_input",
                        "name": "Fixture input",
                        "local_path": "data/input.csv",
                        "analysis_readiness": "query_ready",
                        "grain": "asset-week",
                        "revision": "fixture-r1",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    spec = {
        "input_dataset_id": "fixture_input",
        "output_dataset_id": "synthesis_fixture_weekly_mean",
        "group_by": ["asset"],
        "metrics": [{"function": "mean", "column": "value", "as": "mean_value"}],
        "transforms": [],
    }
    return root, spec


def _accepted_gateway(tmp_path: Path):
    from scripts.research_data_mcp.gateway import ResearchDataGateway
    from scripts.research_data_mcp.synthesis_preview import execution_spec_hash
    from scripts.research_data_mcp.synthesis_thread_store import SynthesisThreadStore
    from scripts.research_data_mcp.synthesis_executor import validate_execution_spec

    root, raw_spec = _repo(tmp_path)
    spec = validate_execution_spec(raw_spec)
    store = SynthesisThreadStore(root / "data_lake/procurement_memory/synthesis_threads.sqlite3")
    thread = store.create(objective="Build a weekly bounded fixture panel.")
    state = thread["state"]
    state["execution_spec"] = spec
    state["accepted_spec_hash"] = execution_spec_hash(spec)
    state["execution"] = {
        "status": "spec_accepted",
        "spec_hash": state["accepted_spec_hash"],
        "output_dataset_id": spec["output_dataset_id"],
    }
    thread = store._save_state(thread["id"], state)

    gateway = ResearchDataGateway.__new__(ResearchDataGateway)
    gateway.repo_root = root
    gateway.registry_path = root / "config/research_query_registry.json"
    gateway.jobs = _FakeJobs()
    gateway._synthesis_thread_store = lambda: store
    return gateway, store, thread, spec


def test_public_gateway_refuses_approval_before_preview(tmp_path: Path):
    gateway, _store, thread, _spec = _accepted_gateway(tmp_path)

    with pytest.raises(ValueError, match="run and review Preview first"):
        gateway.synthesis_thread_submit_execution(thread["id"], action="request_approval")

    assert gateway.jobs.submitted == []


def test_preview_is_idempotent_and_never_creates_a_job(tmp_path: Path):
    gateway, store, thread, _spec = _accepted_gateway(tmp_path)

    first = gateway.synthesis_thread_submit_execution(thread["id"], action="preview")
    second = gateway.synthesis_thread_submit_execution(thread["id"], action="preview")

    assert first["preview_only"] is True
    assert first["execution_submitted"] is False
    assert first["preview"]["status"] == "succeeded"
    assert first["preview"]["materialised"] is False
    assert second["preview_only"] is True
    assert second["preview_reused"] is True
    assert second["preview"]["authority_hash"] == first["preview"]["authority_hash"]
    assert second["preview"]["created_at"] == first["preview"]["created_at"]
    assert gateway.jobs.submitted == []
    assert store.get(thread["id"])["state"]["execution"]["status"] == "spec_accepted"


def test_approval_after_preview_carries_exact_authority_into_job(tmp_path: Path):
    gateway, store, thread, _spec = _accepted_gateway(tmp_path)

    preview = gateway.synthesis_thread_submit_execution(thread["id"], action="preview")
    submitted = gateway.synthesis_thread_submit_execution(thread["id"], action="request_approval")

    assert submitted["preview_only"] is False
    assert submitted["execution_submitted"] is True
    assert len(gateway.jobs.submitted) == 1
    job = submitted["job"]
    assert job["status"] == "pending_approval"
    assert job["plan"]["job_type"] == "synthesis_execute"
    assert job["plan"]["preview_authority_hash"] == preview["preview"]["authority_hash"]
    assert job["plan"]["preview_spec_hash"] == preview["preview"]["spec_hash"]
    assert job["plan"]["preview_input_revisions"] == preview["preview"]["input_revisions"]
    durable = store.get(thread["id"])["state"]
    assert durable["execution"]["status"] == "pending_approval"


def test_changed_bytes_before_approval_invalidate_preview(tmp_path: Path):
    gateway, _store, thread, _spec = _accepted_gateway(tmp_path)
    gateway.synthesis_thread_submit_execution(thread["id"], action="preview")

    with (gateway.repo_root / "data/input.csv").open("a", encoding="utf-8") as fh:
        fh.write("B,2026-W4,99\n")

    with pytest.raises(ValueError, match="different input revisions"):
        gateway.synthesis_thread_submit_execution(thread["id"], action="request_approval")
    assert gateway.jobs.submitted == []


def test_changed_bytes_after_approval_are_blocked_at_worker(tmp_path: Path, monkeypatch):
    from scripts.research_data_mcp import synthesis_executor
    from scripts.yzu_cluster.executor import YzuExecutor

    gateway, _store, thread, _spec = _accepted_gateway(tmp_path)
    gateway.synthesis_thread_submit_execution(thread["id"], action="preview")
    submitted = gateway.synthesis_thread_submit_execution(thread["id"], action="request_approval")
    plan = submitted["job"]["plan"]

    with (gateway.repo_root / "data/input.csv").open("a", encoding="utf-8") as fh:
        fh.write("A,2026-W5,101\n")

    executed = False

    def should_not_execute(*_args, **_kwargs):
        nonlocal executed
        executed = True
        raise AssertionError("production executor must not run after authority drift")

    monkeypatch.setattr(synthesis_executor, "execute", should_not_execute)
    executor = YzuExecutor.__new__(YzuExecutor)
    executor.repo_root = gateway.repo_root

    with pytest.raises(ValueError, match="inputs changed after Preview"):
        executor._synthesis_execute("job-1", plan)
    assert executed is False


def test_http_execute_route_forwards_preview_intent_without_reinterpreting_it():
    from scripts.research_data_mcp import http_router

    class Gateway:
        def __init__(self):
            self.calls = []

        def synthesis_thread_submit_execution(self, thread_id, action="request_approval"):
            self.calls.append((thread_id, action))
            return {"preview_only": action == "preview"}

    gateway = Gateway()
    stack = type("Stack", (), {"gateway": gateway})()
    handler = http_router._HANDLERS["library_synthesis_thread_execute"]

    out = handler(stack, {}, {"action": "preview"}, {"thread_id": "thread-1"})

    assert gateway.calls == [("thread-1", "preview")]
    assert out["preview_only"] is True


def test_mcp_surface_preserves_preview_vs_approval_intent():
    from scripts.research_data_mcp.tool_handlers import ResearchToolHandlers

    class Gateway:
        def __init__(self):
            self.calls = []

        def synthesis_thread_submit_execution(self, thread_id, action="request_approval"):
            self.calls.append((thread_id, action))
            if action == "preview":
                return {
                    "preview_only": True,
                    "execution_submitted": False,
                    "preview": {"status": "succeeded"},
                }
            return {
                "preview_only": False,
                "execution_submitted": True,
                "job": {"id": "job-1", "status": "pending_approval"},
            }

    handler = ResearchToolHandlers.__new__(ResearchToolHandlers)
    handler.gateway = Gateway()

    preview = handler.research_synthesis_submit_execution("thread-1", action="preview")
    approval = handler.research_synthesis_submit_execution("thread-1", action="request_approval")

    assert handler.gateway.calls == [
        ("thread-1", "preview"),
        ("thread-1", "request_approval"),
    ]
    assert preview["preview_only"] is True
    assert preview["job_id"] is None
    assert approval["preview_only"] is False
    assert approval["job_id"] == "job-1"


def test_unknown_execution_action_fails_closed(tmp_path: Path):
    gateway, _store, thread, _spec = _accepted_gateway(tmp_path)
    with pytest.raises(ValueError, match="must be preview or request_approval"):
        gateway.synthesis_thread_submit_execution(thread["id"], action="surprise")
    assert gateway.jobs.submitted == []
