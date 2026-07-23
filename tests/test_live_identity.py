from __future__ import annotations

import json
from pathlib import Path

from scripts.yzu_cluster.orchestrator import YzuOrchestrator
from scripts.yzu_cluster.worker_control import WorkerControlPlane, build_live_identity


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
                "runtime": {"controller_heartbeat_seconds": 0, "lease_seconds": 30},
                "operations": {"disable_local_http_collect": False},
                "agent": {"allowed_job_types": ["http_manifest"]},
                "worker_pools": {},
                "storage": {},
            }
        ),
        encoding="utf-8",
    )
    return YzuOrchestrator(tmp_path)


def test_live_identity_from_registered_job(tmp_path: Path) -> None:
    orchestrator = _orchestrator(tmp_path)
    control = WorkerControlPlane(orchestrator, token="secret-token")
    job = orchestrator.submit(
        "Identity collect",
        {
            "job_type": "http_manifest",
            "dataset_id": "identity_dataset",
            "url": "https://8.8.8.8/data.csv",
            "outputs": ["identity_dataset"],
        },
        {"_ops_internal": True, "idempotency_key": "identity-job-1"},
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
    control.complete(
        job["id"],
        {
            "worker_id": "windows-01",
            "attempt": 1,
            "result": {
                "outputs": ["identity_dataset"],
                "materialized": {
                    "dataset_id": "identity_dataset",
                    "manifest_id": "collection_manifest_identity-job-1",
                },
                "registration_evidence": {
                    "dataset_id": "identity_dataset",
                    "registry_id": "identity_dataset",
                    "manifest_id": "collection_manifest_identity-job-1",
                    "vault_path": "gdrive:Machine_Archive/molina_workbench/Sharpe-Renaissance-data/collection/acquired/procured/identity_dataset",
                    "archive_verified": True,
                    "registry_readback": True,
                    "readiness": "registered",
                },
            },
        },
    )

    by_job = build_live_identity(orchestrator, job_id=job["id"])
    by_dataset = build_live_identity(orchestrator, dataset_id="identity_dataset")

    assert by_job["dataset_id"] == "identity_dataset"
    assert by_job["manifest_id"] == "collection_manifest_identity-job-1"
    assert by_job["readiness"] == "registered"
    assert by_job["synthesis_expectation"]["badge"] == "Registered"
    assert by_job["synthesis_expectation"]["not_badge"] == "Query ready"
    assert by_job["vault_suffix"].endswith("identity_dataset")
    assert by_dataset["job_id"] == job["id"]
    assert by_dataset["worker_id"] == "windows-01"
