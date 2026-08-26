"""Bounded Synthesis Preview/Test authority contract.

These tests prove the authority boundary rather than only response shape:
Preview uses production recipe semantics without materialising an asset; repeating
a Preview can never become an approval request; and approval is available only
for the exact accepted spec and input revisions the researcher previewed.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest


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
    registry = {
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
    (root / "config/research_query_registry.json").write_text(
        json.dumps(registry), encoding="utf-8"
    )
    spec = {
        "input_dataset_id": "fixture_input",
        "output_dataset_id": "synthesis_fixture_weekly_mean",
        "group_by": ["asset"],
        "metrics": [{"function": "mean", "column": "value", "as": "mean_value"}],
        "transforms": [],
    }
    return root, spec


def test_preview_reuses_execution_semantics_without_materialising(tmp_path: Path):
    from scripts.research_data_mcp.synthesis_preview import run_bounded_preview

    root, spec = _repo(tmp_path)
    # The safety contract intentionally clamps tiny requests to ten rows.
    receipt = run_bounded_preview(root, spec, input_row_limit=10, output_row_limit=10)

    assert receipt["status"] == "succeeded"
    assert receipt["bounded"] is True
    assert receipt["sampling"]["source_rows"] == 12
    assert receipt["sampling"]["previewed_rows"] == 10
    assert receipt["sampling"]["source_truncated"] is True
    assert receipt["rows"]["preview_input"] == 10
    assert receipt["rows"]["output"] == 2
    assert receipt["output"]["columns"] == ["asset", "mean_value"]
    assert receipt["output"]["rows"][0]["asset"] == "A"
    assert receipt["output"]["rows"][0]["mean_value"] == 3.5
    assert receipt["input_revisions"][0]["dataset_id"] == "fixture_input"
    assert receipt["input_revisions"][0]["declared"]["revision"] == "fixture-r1"
    assert receipt["authority_hash"]
    assert receipt["materialised"] is False
    assert receipt["registered"] is False
    assert not (root / "data_lake/synthesis/thread_outputs").exists()


class _FakeJobs:
    def __init__(self):
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


def _accepted_gateway(tmp_path: Path):
    # Import the install hook explicitly so this test remains robust if tool
    # registration order changes later.
    from scripts.research_data_mcp.synthesis_preview import execution_spec_hash
    from scripts.research_data_mcp.synthesis_preview_gate import install_synthesis_preview_gate
    from scripts.research_data_mcp.synthesis_thread_store import SynthesisThreadStore
    from scripts.research_data_mcp.gateway import ResearchDataGateway
    from scripts.research_data_mcp.synthesis_executor import validate_execution_spec

    install_synthesis_preview_gate()
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


def test_approval_before_preview_is_refused_and_creates_no_job(tmp_path: Path):
    gateway, _store, thread, _spec = _accepted_gateway(tmp_path)

    with pytest.raises(ValueError, match="run and review Preview first"):
        gateway.synthesis_thread_submit_execution(thread["id"], action="request_approval")

    assert gateway.jobs.submitted == []


def test_preview_action_records_receipt_and_creates_no_job(tmp_path: Path):
    gateway, store, thread, _spec = _accepted_gateway(tmp_path)

    out = gateway.synthesis_thread_submit_execution(thread["id"], action="preview")

    assert out["preview_only"] is True
    assert out["execution_submitted"] is False
    assert out["preview_reused"] is False
    assert out["preview"]["status"] == "succeeded"
    assert out["preview"]["materialised"] is False
    assert out["preview"]["authority_hash"]
    assert gateway.jobs.submitted == []
    durable = store.get(thread["id"])["state"]
    assert durable["preview"]["status"] == "succeeded"
    assert durable["preview"]["spec_hash"] == durable["accepted_spec_hash"]
    assert durable["execution"]["status"] == "spec_accepted"


def test_lost_preview_response_retry_stays_preview_and_never_creates_job(tmp_path: Path):
    gateway, _store, thread, _spec = _accepted_gateway(tmp_path)

    first = gateway.synthesis_thread_submit_execution(thread["id"], action="preview")
    # Model a browser that never received `first` and repeats the same visible action.
    second = gateway.synthesis_thread_submit_execution(thread["id"], action="preview")

    assert first["preview"]["status"] == "succeeded"
    assert second["preview_only"] is True
    assert second["execution_submitted"] is False
    assert second["preview_reused"] is True
    assert second["preview"]["authority_hash"] == first["preview"]["authority_hash"]
    assert second["preview"]["created_at"] == first["preview"]["created_at"]
    assert gateway.jobs.submitted == []


def test_explicit_approval_after_preview_creates_pending_approval(tmp_path: Path):
    gateway, store, thread, _spec = _accepted_gateway(tmp_path)

    preview = gateway.synthesis_thread_submit_execution(thread["id"], action="preview")
    assert preview["preview_only"] is True
    submitted = gateway.synthesis_thread_submit_execution(thread["id"], action="request_approval")

    assert submitted["preview_only"] is False
    assert submitted["execution_submitted"] is True
    assert len(gateway.jobs.submitted) == 1
    job = submitted["job"]
    assert job["status"] == "pending_approval"
    assert job["plan"]["job_type"] == "synthesis_execute"
    durable = store.get(thread["id"])["state"]
    assert durable["execution"]["status"] == "pending_approval"
    assert durable["execution"]["spec_hash"] == durable["preview"]["spec_hash"]


def test_changed_spec_requires_a_new_explicit_preview(tmp_path: Path):
    from scripts.research_data_mcp.synthesis_preview import execution_spec_hash
    from scripts.research_data_mcp.synthesis_executor import validate_execution_spec

    gateway, store, thread, spec = _accepted_gateway(tmp_path)
    first = gateway.synthesis_thread_submit_execution(thread["id"], action="preview")
    old_hash = first["preview"]["spec_hash"]

    changed = validate_execution_spec(
        {
            **spec,
            "output_dataset_id": "synthesis_fixture_weekly_count",
            "metrics": [{"function": "count", "as": "row_count"}],
        }
    )
    state = store.get(thread["id"])["state"]
    state["execution_spec"] = changed
    state["accepted_spec_hash"] = execution_spec_hash(changed)
    state["execution"] = {
        "status": "spec_accepted",
        "spec_hash": state["accepted_spec_hash"],
        "output_dataset_id": changed["output_dataset_id"],
    }
    store._save_state(thread["id"], state)

    with pytest.raises(ValueError, match="run and review Preview first"):
        gateway.synthesis_thread_submit_execution(thread["id"], action="request_approval")
    assert gateway.jobs.submitted == []

    out = gateway.synthesis_thread_submit_execution(thread["id"], action="preview")
    assert out["preview_only"] is True
    assert out["execution_submitted"] is False
    assert out["preview"]["spec_hash"] != old_hash
    assert out["preview"]["spec_hash"] == execution_spec_hash(changed)
    assert gateway.jobs.submitted == []


def test_changed_input_bytes_invalidate_preview_before_approval(tmp_path: Path):
    gateway, _store, thread, _spec = _accepted_gateway(tmp_path)
    first = gateway.synthesis_thread_submit_execution(thread["id"], action="preview")
    first_authority = first["preview"]["authority_hash"]

    # Same accepted method, different bytes. Size changes deterministically even
    # on filesystems whose timestamp resolution is coarse.
    with (gateway.repo_root / "data/input.csv").open("a", encoding="utf-8") as fh:
        fh.write("B,2026-W4,99\n")

    with pytest.raises(ValueError, match="different input revisions"):
        gateway.synthesis_thread_submit_execution(thread["id"], action="request_approval")
    assert gateway.jobs.submitted == []

    refreshed = gateway.synthesis_thread_submit_execution(thread["id"], action="preview")
    assert refreshed["preview"]["status"] == "succeeded"
    assert refreshed["preview"]["authority_hash"] != first_authority
    assert refreshed["preview_reused"] is False
    assert gateway.jobs.submitted == []


def test_failed_preview_persists_failure_and_never_submits(tmp_path: Path):
    gateway, store, thread, _spec = _accepted_gateway(tmp_path)
    # Remove the accepted input bytes after acceptance to prove Preview is a real
    # bounded execution, not merely a restatement of structural preflight.
    (gateway.repo_root / "data/input.csv").unlink()

    out = gateway.synthesis_thread_submit_execution(thread["id"], action="preview")

    assert out["preview_only"] is True
    assert out["execution_submitted"] is False
    assert out["preview"]["status"] == "failed"
    assert gateway.jobs.submitted == []
    assert store.get(thread["id"])["state"]["preview"]["status"] == "failed"

    with pytest.raises(ValueError, match="run and review Preview first"):
        gateway.synthesis_thread_submit_execution(thread["id"], action="request_approval")
    assert gateway.jobs.submitted == []
