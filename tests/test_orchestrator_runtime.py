from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest

from scripts.yzu_cluster.orchestrator import YzuOrchestrator


def _orchestrator(tmp_path: Path, *, operations: dict | None = None, agent_allowed: list[str] | None = None) -> YzuOrchestrator:
    (tmp_path / "config").mkdir()
    (tmp_path / "config/yzu_cluster.json").write_text(
        json.dumps(
            {
                "controller": {
                    "hostname": "optiplex-test",
                    "jobs_root": "data/jobs",
                    "status_root": "data/status",
                },
                "operations": {"disable_local_http_collect": False, **(operations or {})},
                "agent": {"allowed_job_types": agent_allowed or ["http_manifest", "scraper_run"]},
                "worker_pools": {
                    "optiplex": {
                        "enabled": True,
                        "capabilities": ["controller_ui", "cluster_orchestration", "python", "pipeline", "archive"],
                    }
                },
                "storage": {},
            }
        ),
        encoding="utf-8",
    )
    return YzuOrchestrator(tmp_path)


def test_orchestrator_projects_idempotent_runtime_jobs(tmp_path: Path) -> None:
    orchestrator = _orchestrator(tmp_path)
    plan = {"job_type": "http_manifest", "url": "https://example.test"}
    request = {"idempotency_key": "probe-example"}

    submitted = orchestrator.submit("Probe example", plan, request, auto_approve=True)
    replay = orchestrator.submit("Probe example", plan, request, auto_approve=True)

    assert replay["id"] == submitted["id"] == "probe-example"
    assert submitted["runtime"]["status"] == "queued"
    with pytest.raises(ValueError, match="different request"):
        orchestrator.submit("Different title", plan, request, auto_approve=True)


def test_orchestrator_executes_only_a_claimed_compatible_job(tmp_path: Path) -> None:
    orchestrator = _orchestrator(tmp_path)
    orchestrator.executor.execute = lambda _job_id, _plan: {"outputs": ["probe-output"]}  # type: ignore[method-assign]
    job = orchestrator.submit(
        "Probe example",
        {"job_type": "http_manifest", "url": "https://example.test", "outputs": ["probe-output"]},
        {"idempotency_key": "probe-execute"},
        auto_approve=True,
    )

    completed = orchestrator.execute_job(job["id"])

    assert completed["status"] == "completed"
    assert completed["runtime"]["status"] == "completed"
    assert completed["runtime"]["attempt"] == 1


def test_browser_job_stays_queued_without_a_live_browser_worker(tmp_path: Path) -> None:
    orchestrator = _orchestrator(tmp_path)
    job = orchestrator.submit(
        "Scrape example",
        {"job_type": "scraper_run", "script_key": "generic_url_scrape", "url": "https://example.test"},
        {"idempotency_key": "browser-queued"},
        auto_approve=True,
    )

    waiting = orchestrator.execute_job(job["id"])

    assert waiting["status"] == "queued"
    assert waiting["runtime"]["status"] == "queued"


def test_runtime_lease_recovery_reconciles_legacy_running_job(tmp_path: Path) -> None:
    orchestrator = _orchestrator(tmp_path)
    job = orchestrator.submit(
        "Probe example",
        {"job_type": "http_manifest", "url": "https://example.test"},
        {"idempotency_key": "lease-reconcile"},
        auto_approve=True,
    )
    claim = orchestrator.runtime.claim_job(job["id"], lease_seconds=1)
    assert claim is not None
    orchestrator.runtime.start(claim, lease_seconds=1)
    orchestrator.store.update(job["id"], "running")

    orchestrator.runtime.store.reap_expired(at="2099-01-01T00:00:00Z")
    orchestrator.reconcile_runtime()

    assert orchestrator.store.get(job["id"])["status"] == "queued"
    assert orchestrator.runtime.snapshot(job["id"])["status"] == "retrying"


def test_blocking_execution_renews_lease_before_concurrent_reaper(tmp_path: Path) -> None:
    orchestrator = _orchestrator(
        tmp_path,
        operations={"runtime_lease_seconds": 1, "runtime_heartbeat_seconds": 0.05},
    )

    def slow_execute(_job_id: str, _plan: dict) -> dict:
        time.sleep(1.3)
        return {"outputs": ["slow-output"]}

    orchestrator.executor.execute = slow_execute  # type: ignore[method-assign]
    job = orchestrator.submit(
        "Slow probe",
        {"job_type": "http_manifest", "url": "https://example.test", "outputs": ["slow-output"]},
        {"idempotency_key": "slow-probe"},
        auto_approve=True,
    )
    reaped: list[object] = []

    def reap_after_initial_lease() -> None:
        time.sleep(1.05)
        reaped.extend(orchestrator.runtime.reap_expired())

    reaper = threading.Thread(target=reap_after_initial_lease, daemon=True)
    reaper.start()
    completed = orchestrator.execute_job(job["id"])
    reaper.join(timeout=2)

    assert reaped == []
    assert completed["lifecycle"]["stage"] == "completed"
    assert completed["runtime"]["attempt"] == 1


def test_concurrent_identical_submission_returns_one_legacy_job(tmp_path: Path) -> None:
    orchestrator = _orchestrator(tmp_path)
    plan = {"job_type": "http_manifest", "url": "https://example.test"}
    request = {"idempotency_key": "concurrent-probe"}
    barrier = threading.Barrier(2)
    results: list[dict] = []
    errors: list[Exception] = []

    def submit() -> None:
        try:
            barrier.wait()
            results.append(orchestrator.submit("Probe example", plan, request, auto_approve=True))
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    first = threading.Thread(target=submit)
    second = threading.Thread(target=submit)
    first.start()
    second.start()
    first.join()
    second.join()

    assert errors == []
    assert {row["id"] for row in results} == {"concurrent-probe"}
    assert len(orchestrator.store.list(limit=10)) == 1


def test_post_registration_failure_does_not_fail_registered_run(tmp_path: Path) -> None:
    orchestrator = _orchestrator(tmp_path)
    orchestrator.executor.execute = lambda _job_id, _plan: {"outputs": ["probe-output"]}  # type: ignore[method-assign]

    def core(_job_id, _plan, result):
        result.update(
            {
                "drive_finalize": {"ok": True},
                "registration_evidence": {
                    "dataset_id": "probe-output",
                    "registry_id": "probe-output",
                    "manifest_id": "manifest-probe-v1",
                    "vault_path": "gdrive:archive/probe",
                    "archive_verified": True,
                    "registry_readback": True,
                    "readiness": "query_ready",
                },
            }
        )
        return [{"dataset_id": "probe-output"}]

    orchestrator.set_on_job_completed(core)
    orchestrator.set_on_job_post_completed(
        lambda *_args: (_ for _ in ()).throw(RuntimeError("semantic index offline"))
    )
    job = orchestrator.submit(
        "Probe example",
        {"job_type": "http_manifest", "url": "https://example.test", "outputs": ["probe-output"]},
        {"idempotency_key": "post-registration"},
        auto_approve=True,
    )

    completed = orchestrator.execute_job(job["id"])

    assert completed["status"] == "completed"
    assert completed["lifecycle"]["stage"] == "registered"
    assert completed["runtime"]["status"] == "registered"
    assert any("Post-registration follow-up failed" in row["message"] for row in completed["events"])


def _synthesis_plan() -> dict:
    return {
        "job_type": "synthesis_execute",
        "execution_spec": {
            "input_dataset_id": "google_trends_stablecoin_weekly",
            "output_dataset_id": "synthesis_orchestrator_out",
            "group_by": ["week"],
            "metrics": [{"function": "count", "as": "row_count"}],
        },
    }


def test_orchestrator_validates_synthesis_execute_with_configured_python_pool(tmp_path: Path) -> None:
    orchestrator = _orchestrator(tmp_path, agent_allowed=["synthesis_execute"])
    validated = orchestrator.validate_plan(_synthesis_plan())

    assert validated.get("launchable") is not False
    assert not validated.get("validation_error")


def test_orchestrator_rejects_synthesis_without_configured_python_pool(tmp_path: Path) -> None:
    (tmp_path / "config").mkdir()
    (tmp_path / "config/yzu_cluster.json").write_text(
        json.dumps(
            {
                "controller": {
                    "hostname": "optiplex-test",
                    "jobs_root": "data/jobs",
                    "status_root": "data/status",
                },
                "operations": {"disable_local_http_collect": False},
                "agent": {"allowed_job_types": ["synthesis_execute"]},
                "worker_pools": {
                    "optiplex": {
                        "enabled": True,
                        "capabilities": ["controller_ui", "cluster_orchestration"],
                    }
                },
                "storage": {},
            }
        ),
        encoding="utf-8",
    )
    orchestrator = YzuOrchestrator(tmp_path)
    validated = orchestrator.validate_plan(_synthesis_plan())

    assert validated.get("launchable") is False
    assert "python" in str(validated.get("validation_error") or "")


def test_procurement_approval_queues_without_live_worker(tmp_path: Path) -> None:
    """Ordinary procurement must approve/queue even when no live worker is present."""
    orchestrator = _orchestrator(tmp_path, agent_allowed=["http_manifest"])
    # Drop the auto-registered controller so approval cannot depend on a live worker.
    with orchestrator.runtime._lock:
        orchestrator.runtime.connection.execute("DELETE FROM cluster_workers")
    assert orchestrator.runtime.eligible_workers(["http"]) == []

    pending = orchestrator.submit(
        "Probe example",
        {"job_type": "http_manifest", "url": "https://example.test", "launchable": True},
        {"idempotency_key": "procure-approve-no-worker"},
        auto_approve=False,
    )
    assert pending["status"] == "pending_approval"

    approved = orchestrator.approve(pending["id"])

    assert approved["status"] == "queued"
    assert approved["runtime"]["status"] == "queued"
    orchestrator.runtime.close()


def test_synthesis_approval_rejects_without_eligible_worker(tmp_path: Path) -> None:
    """Synthesis approve must fail closed when no fresh Python-capable worker exists."""
    (tmp_path / "config").mkdir()
    (tmp_path / "config/yzu_cluster.json").write_text(
        json.dumps(
            {
                "controller": {
                    "hostname": "optiplex-test",
                    "jobs_root": "data/jobs",
                    "status_root": "data/status",
                },
                "operations": {"disable_local_http_collect": False},
                "agent": {"allowed_job_types": ["synthesis_execute", "http_manifest"]},
                "worker_pools": {
                    "optiplex": {
                        "enabled": True,
                        # Pool lacks python — even a controller heartbeat cannot satisfy Synthesis.
                        "capabilities": ["controller_ui", "cluster_orchestration"],
                    }
                },
                "storage": {},
                "runtime": {"controller_heartbeat_seconds": 0},
            }
        ),
        encoding="utf-8",
    )
    orchestrator = YzuOrchestrator(tmp_path)
    plan = {
        **_synthesis_plan(),
        "launchable": True,
        # Bypass validate_plan live-worker gate so we exercise approve() itself.
        "validation_error": None,
    }
    # Create a pending Synthesis job directly; submit() would mark it non-launchable first.
    job = orchestrator.store.create(
        "Synthesis approve reject",
        {"idempotency_key": "synthesis-approve-reject"},
        plan,
        status="pending_approval",
        job_id="synthesis-approve-reject",
    )
    orchestrator.runtime.ensure(job)
    assert orchestrator.runtime.eligible_workers(["python"]) == []

    with pytest.raises(ValueError, match="no fresh compatible worker"):
        orchestrator.approve(job["id"])

    still = orchestrator.store.get(job["id"])
    assert still["status"] == "pending_approval"
    orchestrator.runtime.close()


def test_synthesis_approval_queues_with_eligible_worker(tmp_path: Path) -> None:
    """Synthesis approve queues when Optiplex declares and advertises python."""
    orchestrator = _orchestrator(tmp_path, agent_allowed=["synthesis_execute"])
    assert orchestrator.runtime.eligible_workers(["python"]), "controller should advertise python"

    pending = orchestrator.submit(
        "Synthesis approve ok",
        {**_synthesis_plan(), "launchable": True},
        {"idempotency_key": "synthesis-approve-ok"},
        auto_approve=False,
    )
    assert pending["status"] == "pending_approval"

    approved = orchestrator.approve(pending["id"])

    assert approved["status"] == "queued"
    assert approved["runtime"]["status"] == "queued"
    assert approved["plan"]["job_type"] == "synthesis_execute"
    orchestrator.runtime.close()


def test_approve_rejects_non_pending_job(tmp_path: Path) -> None:
    orchestrator = _orchestrator(tmp_path)
    queued = orchestrator.submit(
        "Already queued",
        {"job_type": "http_manifest", "url": "https://example.test", "launchable": True},
        {"idempotency_key": "approve-non-pending"},
        auto_approve=True,
    )
    with pytest.raises(ValueError, match="not pending_approval"):
        orchestrator.approve(queued["id"])
    orchestrator.runtime.close()


def test_approve_handles_non_mapping_plan_without_nameerror(tmp_path: Path) -> None:
    """approve() must treat a non-mapping plan as {} (no Mapping NameError)."""
    orchestrator = _orchestrator(tmp_path)
    orchestrator.store.create(
        "Broken plan shape",
        {},
        {"job_type": "http_manifest", "url": "https://example.test", "launchable": True},
        status="pending_approval",
        job_id="approve-bad-plan-shape",
    )
    original_get = orchestrator.store.get

    def _get(job_id: str):
        row = dict(original_get(job_id))
        if job_id == "approve-bad-plan-shape":
            # Only corrupt plan shape; leave status so approve()/get_job() stay coherent.
            row["plan"] = "not-a-mapping"
        return row

    orchestrator.store.get = _get  # type: ignore[method-assign]
    approved = orchestrator.approve("approve-bad-plan-shape")
    assert approved["status"] == "queued"
    orchestrator.runtime.close()


def test_synthesis_approval_then_claim_on_optiplex(tmp_path: Path) -> None:
    orchestrator = _orchestrator(tmp_path, agent_allowed=["synthesis_execute"])
    pending = orchestrator.submit(
        "Synthesis claim path",
        {**_synthesis_plan(), "launchable": True},
        {"idempotency_key": "synthesis-approve-claim"},
        auto_approve=False,
    )
    approved = orchestrator.approve(pending["id"])
    assert approved["status"] == "queued"
    claim = orchestrator.runtime.claim_job(approved["id"])
    assert claim is not None
    assert claim.job_type == "synthesis_execute"
    assert "python" in claim.required_capabilities
    orchestrator.runtime.close()


def test_procurement_approval_does_not_require_python_capability(tmp_path: Path) -> None:
    (tmp_path / "config").mkdir()
    (tmp_path / "config/yzu_cluster.json").write_text(
        json.dumps(
            {
                "controller": {
                    "hostname": "optiplex-test",
                    "jobs_root": "data/jobs",
                    "status_root": "data/status",
                },
                "operations": {"disable_local_http_collect": False},
                "agent": {"allowed_job_types": ["http_manifest"]},
                "worker_pools": {
                    "optiplex": {
                        "enabled": True,
                        "capabilities": ["controller_ui", "cluster_orchestration", "http"],
                    }
                },
                "storage": {},
                "runtime": {"controller_heartbeat_seconds": 0},
            }
        ),
        encoding="utf-8",
    )
    orchestrator = YzuOrchestrator(tmp_path)
    pending = orchestrator.submit(
        "HTTP only pool",
        {"job_type": "http_manifest", "url": "https://example.test", "launchable": True},
        {"idempotency_key": "procure-no-python-pool"},
        auto_approve=False,
    )
    approved = orchestrator.approve(pending["id"])
    assert approved["status"] == "queued"
    orchestrator.runtime.close()
