from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path

import pytest

from scripts.yzu_cluster.orchestrator import YzuOrchestrator
from scripts.yzu_cluster.worker_control import WorkerControlPlane


def _orchestrator(tmp_path: Path) -> YzuOrchestrator:
    (tmp_path / "config").mkdir()
    (tmp_path / "config/yzu_cluster.json").write_text(
        json.dumps(
            {
                "controller": {
                    "hostname": "optiplex-test",
                    "jobs_root": "data/jobs",
                    "status_root": "data/status",
                },
                "runtime": {
                    "controller_heartbeat_seconds": 0,
                    "lease_seconds": 30,
                },
                "operations": {"disable_local_http_collect": False},
                "agent": {"allowed_job_types": ["http_manifest"]},
                "worker_pools": {},
                "storage": {},
            }
        ),
        encoding="utf-8",
    )
    return YzuOrchestrator(tmp_path)


def test_worker_control_requires_constant_time_token(tmp_path: Path) -> None:
    control = WorkerControlPlane(_orchestrator(tmp_path), token="secret-token")

    control.authorize("secret-token")
    with pytest.raises(PermissionError, match="invalid worker control token"):
        control.authorize("wrong-token")
    with pytest.raises(PermissionError, match="invalid worker control token"):
        control.authorize("")


def test_remote_worker_join_claim_heartbeat_usage_and_complete(tmp_path: Path) -> None:
    orchestrator = _orchestrator(tmp_path)
    control = WorkerControlPlane(orchestrator, token="secret-token")
    submitted = orchestrator.submit(
        "Remote HTTP collection",
        {
            "job_type": "http_manifest",
            "url": "https://8.8.8.8/data.csv",
            "outputs": ["remote-dataset"],
            "resource_requirements": {"cpu_cores": 1, "memory_mb": 256},
        },
        {"idempotency_key": "remote-http-1"},
        auto_approve=True,
    )

    worker = control.join(
        {
            "worker_id": "windows-01",
            "pool": "windows_lab",
            "capabilities": ["http_collect", "python"],
            "capacity": {"cpu_cores": 4, "memory_mb": 4096, "disk_mb": 20480},
        }
    )
    claim = control.claim({"worker_id": "windows-01", "lease_seconds": 30})

    assert worker["id"] == "windows-01"
    assert claim is not None
    assert claim["job_id"] == submitted["id"]
    assert claim["attempt"] == 1
    assert claim["plan"]["job_type"] == "http_manifest"

    running = control.heartbeat(
        submitted["id"],
        {
            "worker_id": "windows-01",
            "attempt": 1,
            "stage": "running",
            "progress": {"current": 1, "total": 2},
        },
    )
    usage = control.usage(
        submitted["id"],
        {
            "worker_id": "windows-01",
            "attempt": 1,
            "cpu_seconds": 3.5,
            "memory_peak_mb": 512,
            "network_bytes": 2048,
        },
    )
    completed = control.complete(
        submitted["id"],
        {
            "worker_id": "windows-01",
            "attempt": 1,
            "result": {"outputs": ["remote-dataset"]},
        },
    )

    assert running["status"] == "running"
    assert usage["cpu_seconds"] == 3.5
    assert usage["memory_peak_mb"] == 512
    assert completed["status"] == "completed"
    assert completed["lifecycle"]["stage"] == "completed"
    assert completed["assigned_worker"]["id"] == "windows-01"

    with pytest.raises((PermissionError, ValueError), match="stale execution attempt|not writable"):
        control.heartbeat(
            submitted["id"],
            {"worker_id": "windows-01", "attempt": 1, "stage": "running"},
        )


def test_uploaded_artifact_materializes_on_controller(tmp_path: Path) -> None:
    orchestrator = _orchestrator(tmp_path)
    control = WorkerControlPlane(orchestrator, token="secret-token", max_artifact_bytes=1024 * 1024)
    job = orchestrator.submit(
        "Remote artifact collection",
        {
            "job_type": "http_manifest",
            "dataset_id": "remote_uploaded_dataset",
            "url": "https://8.8.8.8/upload.csv",
            "validation": {"min_files": 1, "min_total_bytes": 1},
        },
        {"idempotency_key": "remote-upload-1"},
        auto_approve=True,
    )
    control.join(
        {
            "worker_id": "windows-01",
            "pool": "windows_lab",
            "capabilities": ["http"],
            "capacity": {"cpu_cores": 2, "memory_mb": 2048},
        }
    )
    claim = control.claim({"worker_id": "windows-01"})
    assert claim is not None
    control.heartbeat(job["id"], {"worker_id": "windows-01", "attempt": 1, "stage": "running"})

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("raw/upload.csv", "timestamp,value\n2026-01-01,1\n")
    content = buffer.getvalue()
    digest = hashlib.sha256(content).hexdigest()
    uploaded = control.upload_artifact(
        job["id"],
        worker_id="windows-01",
        attempt=1,
        name="worker-output.zip",
        content=content,
        expected_sha256=digest,
    )

    completed = control.complete(
        job["id"],
        {
            "worker_id": "windows-01",
            "attempt": 1,
            "result": {
                "artifacts": [{"artifact": uploaded["artifact"], "bytes": uploaded["bytes"]}],
                "collect_mode": "remote_control",
            },
        },
    )

    materialized = completed["result"]["materialized"]
    manifest = tmp_path / materialized["manifest_path"]
    assert uploaded["sha256"] == digest
    assert materialized["dataset_id"] == "remote_uploaded_dataset"
    assert manifest.is_file()
    assert completed["lifecycle"]["stage"] == "completed"
    assert completed["manifest_id"] == materialized["manifest_id"]

    with pytest.raises((PermissionError, ValueError), match="not writable|stale execution attempt"):
        control.upload_artifact(
            job["id"],
            worker_id="windows-01",
            attempt=1,
            name="late.zip",
            content=content,
        )


def test_remote_completion_preserves_registration_proof(tmp_path: Path) -> None:
    orchestrator = _orchestrator(tmp_path)
    control = WorkerControlPlane(orchestrator, token="secret-token", max_artifact_bytes=1024 * 1024)
    job = orchestrator.submit(
        "Remote registered collection",
        {
            "job_type": "http_manifest",
            "dataset_id": "remote_registered_dataset",
            "connector_id": "public_source",
            "url": "https://8.8.8.8/registered.json",
            "validation": {"min_files": 1, "min_total_bytes": 1},
        },
        {"idempotency_key": "remote-registered-1"},
        auto_approve=True,
    )
    control.join(
        {
            "worker_id": "windows-01",
            "pool": "windows_lab",
            "capabilities": ["http"],
            "capacity": {"cpu_cores": 2, "memory_mb": 2048},
        }
    )
    claim = control.claim({"worker_id": "windows-01"})
    assert claim is not None

    def core(_job_id: str, _plan: dict, result: dict) -> list[dict]:
        result["drive_finalize"] = {
            "ok": True,
            "archives": [
                {
                    "ok": True,
                    "dataset_id": "remote_registered_dataset",
                    "remote_path": "gdrive:archive/remote_registered_dataset",
                }
            ],
        }
        result["registration_evidence"] = {
            "dataset_id": "remote_registered_dataset",
            "registry_id": "registry_remote_registered_dataset",
            "manifest_id": result["materialized"]["manifest_id"],
            "vault_path": "gdrive:archive/remote_registered_dataset",
            "archive_verified": True,
            "registry_readback": True,
            "readiness": "query_ready",
        }
        return [{"dataset_id": "remote_registered_dataset"}]

    orchestrator.set_on_job_completed(core)
    control.heartbeat(job["id"], {"worker_id": "windows-01", "attempt": 1, "stage": "running"})
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("raw/registered.json", '{"ok": true}\n')
    content = buffer.getvalue()
    digest = hashlib.sha256(content).hexdigest()
    uploaded = control.upload_artifact(
        job["id"],
        worker_id="windows-01",
        attempt=1,
        name="registered-output.zip",
        content=content,
        expected_sha256=digest,
    )

    completed = control.complete(
        job["id"],
        {
            "worker_id": "windows-01",
            "attempt": 1,
            "result": {
                "artifacts": [{"artifact": uploaded["artifact"], "bytes": uploaded["bytes"]}],
                "collect_mode": "remote_control",
            },
        },
    )

    assert completed["result"]["materialized"]["dataset_id"] == "remote_registered_dataset"
    assert completed["result"]["registration_evidence"]["registry_readback"] is True
    assert completed["runtime"]["status"] == "registered"
    assert completed["lifecycle"]["stage"] == "registered"


def test_remote_failure_requeues_and_fences_old_attempt(tmp_path: Path) -> None:
    orchestrator = _orchestrator(tmp_path)
    control = WorkerControlPlane(orchestrator, token="secret-token")
    job = orchestrator.submit(
        "Retry remote collection",
        {"job_type": "http_manifest", "url": "https://8.8.8.8/retry.csv", "max_attempts": 2},
        {"idempotency_key": "remote-retry-1"},
        auto_approve=True,
    )
    control.join(
        {
            "worker_id": "windows-01",
            "pool": "windows_lab",
            "capabilities": ["http"],
            "capacity": {"cpu_cores": 2, "memory_mb": 2048},
        }
    )
    first = control.claim({"worker_id": "windows-01"})
    assert first is not None
    control.heartbeat(job["id"], {"worker_id": "windows-01", "attempt": 1, "stage": "running"})

    retrying = control.fail(
        job["id"],
        {
            "worker_id": "windows-01",
            "attempt": 1,
            "error": "temporary network failure",
            "retryable": True,
        },
    )
    second = control.claim({"worker_id": "windows-01"})

    assert retrying["status"] == "queued"
    assert retrying["runtime"]["status"] == "retrying"
    assert second is not None
    assert second["attempt"] == 2
    with pytest.raises(PermissionError, match="stale execution attempt"):
        control.usage(
            job["id"],
            {"worker_id": "windows-01", "attempt": 1, "cpu_seconds": 1},
        )
