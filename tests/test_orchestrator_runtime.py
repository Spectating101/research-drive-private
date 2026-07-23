from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest

from scripts.yzu_cluster import executor as executor_module
from scripts.yzu_cluster.executor import YzuExecutor
from scripts.yzu_cluster.orchestrator import YzuOrchestrator
from scripts.yzu_cluster.worker_control import WorkerControlPlane


def _orchestrator(tmp_path: Path, *, operations: dict | None = None) -> YzuOrchestrator:
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
                "agent": {"allowed_job_types": ["http_manifest", "scraper_run", "source_probe"]},
                "worker_pools": {},
                "storage": {},
            }
        ),
        encoding="utf-8",
    )
    return YzuOrchestrator(tmp_path)


def test_orchestrator_projects_idempotent_runtime_jobs(tmp_path: Path) -> None:
    orchestrator = _orchestrator(tmp_path)
    plan = {"job_type": "http_manifest", "url": "https://8.8.8.8"}
    request = {"_ops_internal": True, "idempotency_key": "probe-example"}

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
        {"job_type": "http_manifest", "url": "https://8.8.8.8", "outputs": ["probe-output"]},
        {"_ops_internal": True, "idempotency_key": "probe-execute"},
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
        {"job_type": "scraper_run", "script_key": "generic_url_scrape", "url": "https://8.8.8.8"},
        {"_ops_internal": True, "idempotency_key": "browser-queued"},
        auto_approve=True,
    )

    waiting = orchestrator.execute_job(job["id"])

    assert waiting["status"] == "queued"
    assert waiting["runtime"]["status"] == "queued"


def test_controller_yields_http_run_to_fresh_windows_worker(tmp_path: Path) -> None:
    orchestrator = _orchestrator(tmp_path)
    control = WorkerControlPlane(orchestrator, token="secret-token")
    control.join(
        {
            "worker_id": "windows-01",
            "pool": "windows_lab",
            "capabilities": ["http"],
            "capacity": {"cpu_cores": 2, "memory_mb": 2048},
        }
    )
    job = orchestrator.submit(
        "Windows-first HTTP procurement",
        {"job_type": "http_manifest", "url": "https://8.8.8.8/data.csv"},
        {"_ops_internal": True, "idempotency_key": "windows-first-http"},
        auto_approve=True,
    )

    assert orchestrator.worker_tick() is None
    assert orchestrator.runtime.snapshot(job["id"])["status"] == "queued"
    claim = control.claim({"worker_id": "windows-01"})
    assert claim is not None
    item = claim["plan"]["items"][0]
    assert item["url"] == "https://8.8.8.8/data.csv"
    assert item["network_evidence"]["resolved_addresses"] == ["8.8.8.8"]
    assert item["network_evidence"]["host"] == "8.8.8.8"


def test_controller_still_claims_non_http_work_with_windows_worker_present(tmp_path: Path) -> None:
    orchestrator = _orchestrator(tmp_path)
    control = WorkerControlPlane(orchestrator, token="secret-token")
    control.join(
        {
            "worker_id": "windows-01",
            "pool": "windows_lab",
            "capabilities": ["http"],
            "capacity": {"cpu_cores": 2, "memory_mb": 2048},
        }
    )
    orchestrator.executor.execute = lambda _job_id, _plan: {"outputs": ["controller-output"]}  # type: ignore[method-assign]
    job = orchestrator.submit(
        "Controller-owned probe",
        {"job_type": "source_probe", "url": "https://8.8.8.8"},
        {"_ops_internal": True, "idempotency_key": "controller-probe-with-windows"},
        auto_approve=True,
    )
    completed = orchestrator.worker_tick()
    assert completed is not None
    assert completed["id"] == job["id"]
    assert completed["status"] == "completed"


def test_runtime_lease_recovery_reconciles_legacy_running_job(tmp_path: Path) -> None:
    orchestrator = _orchestrator(tmp_path)
    job = orchestrator.submit(
        "Probe example",
        {"job_type": "http_manifest", "url": "https://8.8.8.8"},
        {"_ops_internal": True, "idempotency_key": "lease-reconcile"},
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
        {"job_type": "http_manifest", "url": "https://8.8.8.8", "outputs": ["slow-output"]},
        {"_ops_internal": True, "idempotency_key": "slow-probe"},
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
    plan = {"job_type": "http_manifest", "url": "https://8.8.8.8"}
    request = {"_ops_internal": True, "idempotency_key": "concurrent-probe"}
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
        {"job_type": "http_manifest", "url": "https://8.8.8.8", "outputs": ["probe-output"]},
        {"_ops_internal": True, "idempotency_key": "post-registration"},
        auto_approve=True,
    )

    completed = orchestrator.execute_job(job["id"])

    assert completed["status"] == "completed"
    assert completed["lifecycle"]["stage"] == "registered"
    assert completed["runtime"]["status"] == "registered"
    assert any("Post-registration follow-up failed" in row["message"] for row in completed["events"])


def _http_executor(tmp_path: Path) -> YzuExecutor:
    executor = object.__new__(YzuExecutor)
    executor.repo_root = tmp_path
    executor.cfg = {
        "operations": {
            "cluster_only": True,
            "disable_local_http_collect": False,
            "http_remote_fallback": True,
        }
    }
    executor.agent_cfg = {}
    executor.jobs_root = tmp_path / "jobs"
    executor.procurement = object()
    executor._event = lambda *_args: None
    return executor


def test_http_manifest_does_not_hide_windows_failure_with_local_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executor = _http_executor(tmp_path)
    executor._http_manifest_remote = lambda *_args: (_ for _ in ()).throw(RuntimeError("provider rejected request"))  # type: ignore[method-assign]
    monkeypatch.setattr(
        "scripts.yzu_cluster.windows_lab_readiness.probe_windows_lab",
        lambda *_args, **_kwargs: {"http_shard_ready": True},
    )
    local_calls: list[str] = []
    monkeypatch.setattr(
        executor_module,
        "collect_local_manifest",
        lambda *_args, **_kwargs: local_calls.append("local") or {"collect_mode": "local"},
    )
    monkeypatch.setattr(executor_module, "materialize_job", lambda _root, _job, _plan, result, *, cfg: result)

    with pytest.raises(RuntimeError, match="provider rejected request"):
        executor._http_manifest(
            "windows-source-failure",
            {"job_type": "http_manifest", "url": "https://8.8.8.8", "items": [{"url": "https://8.8.8.8"}]},
        )

    assert local_calls == []


def test_http_manifest_uses_optiplex_only_when_windows_pool_is_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executor = _http_executor(tmp_path)
    executor._http_manifest_remote = lambda *_args: (_ for _ in ()).throw(RuntimeError("no joined windows_lab workers"))  # type: ignore[method-assign]
    monkeypatch.setattr(
        "scripts.yzu_cluster.windows_lab_readiness.probe_windows_lab",
        lambda *_args, **_kwargs: {"http_shard_ready": False},
    )
    monkeypatch.setattr(
        executor_module,
        "collect_local_manifest",
        lambda *_args, **_kwargs: {"collect_mode": "local"},
    )
    monkeypatch.setattr(executor_module, "materialize_job", lambda _root, _job, _plan, result, *, cfg: result)

    result = executor._http_manifest(
        "windows-pool-offline",
        {"job_type": "http_manifest", "url": "https://8.8.8.8", "items": [{"url": "https://8.8.8.8"}]},
    )

    assert result["collect_mode"] == "local_fallback"
