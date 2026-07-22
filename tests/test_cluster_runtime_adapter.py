from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest

from scripts.yzu_cluster.jobs import YzuJobStore
from scripts.yzu_cluster.runtime_adapter import ClusterRuntimeAdapter


def _legacy_job(store: YzuJobStore, job_id: str = "collect-usdt") -> dict:
    return store.create(
        "Collect USDT history",
        {},
        {
            "job_type": "http_manifest",
            "inputs": ["usdt_contracts"],
            "dataset_id": "raw_usdt_history",
        },
        status="queued",
        job_id=job_id,
    )


def test_runtime_tables_do_not_replace_legacy_events(tmp_path: Path) -> None:
    database = tmp_path / "jobs.sqlite3"
    legacy = YzuJobStore(database)
    job = _legacy_job(legacy)
    legacy.event(job["id"], "info", "legacy event")

    runtime = ClusterRuntimeAdapter(database, {"controller": {"hostname": "optiplex"}})
    snapshot = runtime.ensure(job)

    with sqlite3.connect(database) as db:
        legacy_columns = {row[1] for row in db.execute("PRAGMA table_info(events)")}
        runtime_columns = {row[1] for row in db.execute("PRAGMA table_info(cluster_events)")}

    assert {"job_id", "level", "message"}.issubset(legacy_columns)
    assert {"run_id", "stage", "event_type", "attempt"}.issubset(runtime_columns)
    assert snapshot["id"] == job["id"]
    assert legacy.get(job["id"])["events"][-1]["message"] == "legacy event"


def test_runtime_claims_only_fresh_capable_workers_and_fences_attempts(tmp_path: Path) -> None:
    database = tmp_path / "jobs.sqlite3"
    legacy = YzuJobStore(database)
    runtime = ClusterRuntimeAdapter(database, {"controller": {"hostname": "optiplex"}})
    job = _legacy_job(legacy)
    runtime.ensure(job)

    claim = runtime.claim_next()
    assert claim is not None
    runtime.start(claim)
    runtime.complete(claim, {"outputs": ["raw_usdt_history"]})
    assert runtime.snapshot(job["id"])["status"] == "completed"

    with pytest.raises(PermissionError, match="stale execution attempt"):
        runtime.heartbeat(job["id"], claim.worker_id, attempt=claim.attempt + 1)


def test_runtime_requires_a_real_capability_for_browser_work(tmp_path: Path) -> None:
    database = tmp_path / "jobs.sqlite3"
    legacy = YzuJobStore(database)
    runtime = ClusterRuntimeAdapter(database, {"controller": {"hostname": "optiplex"}})
    job = legacy.create(
        "Collect source through browser",
        {},
        {"job_type": "scraper_run", "url": "https://example.test"},
        status="queued",
        job_id="browser-collect",
    )
    runtime.ensure(job)

    assert runtime.claim_next() is None
    assert runtime.snapshot(job["id"])["status"] == "queued"


def test_runtime_registers_only_explicit_readback_proof(tmp_path: Path) -> None:
    database = tmp_path / "jobs.sqlite3"
    legacy = YzuJobStore(database)
    runtime = ClusterRuntimeAdapter(database, {"controller": {"hostname": "optiplex"}})
    job = _legacy_job(legacy, "register-usdt")
    runtime.ensure(job)
    claim = runtime.claim_next()
    assert claim is not None
    runtime.start(claim)

    registered = runtime.complete(
        claim,
        {
            "outputs": ["raw_usdt_history"],
            "output_manifest_id": "manifest-usdt-v1",
            "drive_finalize": {"ok": True},
            "registry_promotion": [{"dataset_id": "raw_usdt_history"}],
            "registration_evidence": {
                "dataset_id": "raw_usdt_history",
                "registry_id": "raw_usdt_history",
                "manifest_id": "manifest-usdt-v1",
                "vault_path": "gdrive:archive/usdt",
                "archive_verified": True,
                "registry_readback": True,
                "readiness": "query_ready",
            },
        },
    )

    assert registered["status"] == "registered"
    assert runtime.store.asset("raw_usdt_history")["analysis_readiness"] == "query_ready"


def test_runtime_does_not_register_partial_or_unverified_evidence(tmp_path: Path) -> None:
    database = tmp_path / "jobs.sqlite3"
    legacy = YzuJobStore(database)
    runtime = ClusterRuntimeAdapter(database, {"controller": {"hostname": "optiplex"}})
    job = _legacy_job(legacy, "partial-usdt")
    runtime.ensure(job)
    claim = runtime.claim_next()
    assert claim is not None
    runtime.start(claim)

    completed = runtime.complete(
        claim,
        {
            "outputs": ["raw_usdt_history"],
            "registration_evidence": {
                "dataset_id": "raw_usdt_history",
                "registry_id": "raw_usdt_history",
                "manifest_id": "manifest-usdt-v1",
                "vault_path": "gdrive:archive/usdt",
                "archive_verified": False,
                "registry_readback": True,
            },
        },
    )

    assert completed["status"] == "completed"


def test_expired_lease_retries_and_fences_the_old_attempt(tmp_path: Path) -> None:
    database = tmp_path / "jobs.sqlite3"
    legacy = YzuJobStore(database)
    runtime = ClusterRuntimeAdapter(database, {"controller": {"hostname": "optiplex"}})
    job = _legacy_job(legacy, "retry-usdt")
    runtime.ensure(job)
    first = runtime.claim_next(lease_seconds=1)
    assert first is not None
    runtime.start(first)

    runtime.store.reap_expired(at="2099-01-01T00:00:00Z")
    assert runtime.snapshot(job["id"])["status"] == "retrying"
    second = runtime.claim_next()
    assert second is not None
    assert second.attempt == first.attempt + 1

    with pytest.raises(PermissionError, match="stale execution attempt"):
        runtime.heartbeat(job["id"], first.worker_id, attempt=first.attempt)


def test_controller_refreshes_before_claiming_after_stale_interval(tmp_path: Path) -> None:
    database = tmp_path / "jobs.sqlite3"
    legacy = YzuJobStore(database)
    runtime = ClusterRuntimeAdapter(
        database,
        {
            "controller": {"hostname": "optiplex"},
            "runtime": {"worker_stale_after_seconds": 1, "controller_heartbeat_seconds": 0},
        },
    )
    job = _legacy_job(legacy, "fresh-controller")
    runtime.ensure(job)
    controller = runtime.store.worker("optiplex")
    runtime.store.upsert_worker(
        "optiplex",
        pool=controller["pool"],
        capabilities=controller["capabilities"],
        capacity=controller["capacity"],
        heartbeat_at="2000-01-01T00:00:00Z",
    )

    claim = runtime.claim_next()

    assert claim is not None
    assert runtime.store.worker("optiplex")["freshness"]["state"] == "fresh"
    runtime.close()


def test_lease_renewer_keeps_long_running_attempt_claimed(tmp_path: Path) -> None:
    database = tmp_path / "jobs.sqlite3"
    legacy = YzuJobStore(database)
    runtime = ClusterRuntimeAdapter(
        database,
        {
            "controller": {"hostname": "optiplex"},
            "runtime": {"controller_heartbeat_seconds": 0, "lease_seconds": 1, "lease_heartbeat_seconds": 0.05},
        },
    )
    job = _legacy_job(legacy, "long-running")
    runtime.ensure(job)
    claim = runtime.claim_next(lease_seconds=1)
    assert claim is not None
    runtime.start(claim, lease_seconds=1)
    renewer = runtime.lease_renewer(claim, lease_seconds=1, interval_seconds=0.05).start()
    try:
        time.sleep(1.15)
        assert runtime.store.reap_expired() == []
        assert runtime.snapshot(job["id"])["status"] == "running"
        renewer.raise_if_lost()
    finally:
        renewer.stop()
        runtime.close()


def test_project_exposes_registered_runtime_shape_at_top_level(tmp_path: Path) -> None:
    database = tmp_path / "jobs.sqlite3"
    legacy = YzuJobStore(database)
    runtime = ClusterRuntimeAdapter(
        database,
        {"controller": {"hostname": "optiplex"}, "runtime": {"controller_heartbeat_seconds": 0}},
    )
    job = _legacy_job(legacy, "projected-registered")
    runtime.ensure(job)
    claim = runtime.claim_next()
    assert claim is not None
    runtime.start(claim)
    runtime.complete(
        claim,
        {
            "outputs": ["raw_usdt_history"],
            "drive_finalize": {"ok": True},
            "registry_promotion": [{"dataset_id": "raw_usdt_history"}],
            "registration_evidence": {
                "dataset_id": "raw_usdt_history",
                "registry_id": "raw_usdt_history",
                "manifest_id": "manifest-usdt-v1",
                "vault_path": "gdrive:archive/usdt",
                "archive_verified": True,
                "registry_readback": True,
                "readiness": "query_ready",
            },
        },
    )

    projected = runtime.project(legacy.get(job["id"]))

    assert projected["status"] == "queued"
    assert projected["lifecycle"]["stage"] == "registered"
    assert projected["execution"]["stage"] == "registered"
    assert projected["archive_verified"] is True
    assert projected["registration_id"] == "raw_usdt_history"
    assert projected["outputs"] == ["raw_usdt_history"]
    runtime.close()


def _synthesis_plan(*, launchable: bool = False) -> dict:
    return {
        "job_type": "synthesis_execute",
        "launchable": launchable,
        "execution_spec": {
            "input_dataset_id": "google_trends_stablecoin_weekly",
            "output_dataset_id": "synthesis_runtime_hardening_out",
            "group_by": ["week"],
            "metrics": [{"function": "count", "as": "row_count"}],
            "transforms": [],
        },
    }


def _cluster_config(*, optiplex_caps: list[str] | None = None) -> dict:
    return {
        "controller": {"hostname": "optiplex"},
        "runtime": {"controller_heartbeat_seconds": 0},
        "operations": {"disable_local_http_collect": False},
        "worker_pools": {
            "optiplex": {
                "kind": "local_linux",
                "enabled": True,
                "capabilities": optiplex_caps
                or ["controller_ui", "cluster_orchestration", "python", "pipeline", "archive"],
            },
            "windows_lab": {
                "enabled": True,
                "capabilities": ["browser", "http"],
            },
        },
    }


def test_synthesis_execute_claims_on_optiplex_python_worker(tmp_path: Path) -> None:
    database = tmp_path / "jobs.sqlite3"
    legacy = YzuJobStore(database)
    runtime = ClusterRuntimeAdapter(database, _cluster_config())
    job = legacy.create(
        "Synthesis execute",
        {},
        _synthesis_plan(),
        status="queued",
        job_id="synthesis-live",
    )
    runtime.ensure(job)

    claim = runtime.claim_next()

    assert claim is not None
    assert claim.job_type == "synthesis_execute"
    assert claim.worker_id == "optiplex"
    assert "python" in claim.required_capabilities
    runtime.close()


def test_synthesis_execute_rejects_capability_mismatched_worker(tmp_path: Path) -> None:
    database = tmp_path / "jobs.sqlite3"
    legacy = YzuJobStore(database)
    runtime = ClusterRuntimeAdapter(database, _cluster_config())
    runtime.store.upsert_worker(
        "browser-only",
        pool="windows_lab",
        capabilities=["browser", "http"],
    )
    job = legacy.create(
        "Synthesis execute",
        {},
        _synthesis_plan(),
        status="queued",
        job_id="synthesis-mismatch",
    )
    runtime.ensure(job)

    assert runtime.claim_job(job["id"], worker_id="browser-only") is None
    assert runtime.snapshot(job["id"])["status"] == "queued"
    runtime.close()


def test_synthesis_execute_requires_configured_python_pool(tmp_path: Path) -> None:
    database = tmp_path / "jobs.sqlite3"
    runtime = ClusterRuntimeAdapter(
        database,
        _cluster_config(optiplex_caps=["controller_ui", "cluster_orchestration"]),
    )
    plan = _synthesis_plan()

    assert runtime.has_configured_worker_for(plan) is False
    assert "python" not in runtime.configured_worker_capabilities()
    runtime.close()


def _synthesis_orchestrator(tmp_path: Path, *, worker_pools: dict) -> tuple:
    import json

    from scripts.yzu_cluster.orchestrator import YzuOrchestrator

    (tmp_path / "config").mkdir()
    (tmp_path / "config/yzu_cluster.json").write_text(
        json.dumps(
            {
                "controller": {
                    "hostname": "optiplex",
                    "jobs_root": "data/jobs",
                    "status_root": "data/status",
                },
                "operations": {"disable_local_http_collect": False},
                "agent": {"allowed_job_types": ["synthesis_execute"]},
                "worker_pools": worker_pools,
                "storage": {},
                "runtime": {"controller_heartbeat_seconds": 0},
            }
        ),
        encoding="utf-8",
    )
    orchestrator = YzuOrchestrator(tmp_path)
    return orchestrator, orchestrator.runtime


def test_synthesis_execute_validation_accepts_configured_python_worker(tmp_path: Path) -> None:
    orchestrator, runtime = _synthesis_orchestrator(
        tmp_path,
        worker_pools={
            "optiplex": {
                "enabled": True,
                "capabilities": ["controller_ui", "cluster_orchestration", "python", "pipeline"],
            }
        },
    )
    validated = orchestrator.validate_plan(_synthesis_plan(launchable=True))
    assert validated.get("launchable") is True
    assert "validation_error" not in validated
    assert runtime.eligible_workers(["python"])
    runtime.close()


def test_synthesis_execute_validation_rejects_without_configured_python_pool(tmp_path: Path) -> None:
    orchestrator, runtime = _synthesis_orchestrator(
        tmp_path,
        worker_pools={
            "optiplex": {
                "enabled": True,
                "capabilities": ["controller_ui", "cluster_orchestration"],
            }
        },
    )
    validated = orchestrator.validate_plan(_synthesis_plan(launchable=True))
    assert validated.get("launchable") is False
    assert "required capabilities" in str(validated.get("validation_error") or "")
    runtime.close()


def test_synthesis_execute_scheduler_rejects_capability_mismatch(tmp_path: Path) -> None:
    orchestrator, runtime = _synthesis_orchestrator(
        tmp_path,
        worker_pools={
            "optiplex": {
                "enabled": True,
                "capabilities": ["controller_ui", "cluster_orchestration", "python"],
            },
            "windows_lab": {
                "enabled": True,
                "capabilities": ["browser", "http"],
            },
        },
    )
    legacy = orchestrator.store
    job = legacy.create(
        "Synthesis execute",
        {},
        _synthesis_plan(),
        status="queued",
        job_id="synthesis-live",
    )
    runtime.ensure(job)

    runtime.store.upsert_worker(
        "browser-only",
        pool="windows_lab",
        capabilities=["browser"],
        heartbeat_at="2099-01-01T00:00:00Z",
    )
    assert runtime.claim_next(worker_id="browser-only") is None
    assert runtime.snapshot(job["id"])["status"] == "queued"

    claim = runtime.claim_next(worker_id="optiplex")
    assert claim is not None
    assert claim.job_id == "synthesis-live"
    assert "python" in claim.required_capabilities
    runtime.close()
