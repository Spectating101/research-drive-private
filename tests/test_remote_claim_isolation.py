from __future__ import annotations

import json
from pathlib import Path

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
                "operations": {
                    "disable_local_http_collect": False,
                    "remote_worker": {
                        "allowed_job_types": ["http_manifest"],
                        "deny_job_id_prefixes": ["probe-no-promotion-", "missing-manifest-"],
                    },
                },
                "agent": {"allowed_job_types": ["http_manifest", "source_probe"]},
                "worker_pools": {},
                "storage": {},
            }
        ),
        encoding="utf-8",
    )
    return YzuOrchestrator(tmp_path)


def test_remote_claim_skips_unsupported_and_fixture_jobs(tmp_path: Path) -> None:
    orchestrator = _orchestrator(tmp_path)
    control = WorkerControlPlane(orchestrator, token="secret-token")
    control.join(
        {
            "worker_id": "windows-01",
            "pool": "windows_lab",
            "capabilities": ["http", "python"],
            "capacity": {"cpu_cores": 2, "memory_mb": 2048},
        }
    )

    orchestrator.submit(
        "Fixture synthesis",
        {"job_type": "source_probe", "url": "https://8.8.8.8/probe.json", "launchable": True},
        {"idempotency_key": "fixture-source-probe-1"},
        auto_approve=True,
    )
    orchestrator.submit(
        "Fixture probe",
        {"job_type": "http_manifest", "url": "https://8.8.8.8/a.csv", "launchable": True},
        {"idempotency_key": "probe-no-promotion-deadbeef"},
        auto_approve=True,
    )
    wanted = orchestrator.submit(
        "Production collect",
        {"job_type": "http_manifest", "url": "https://8.8.8.8/b.csv", "launchable": True},
        {"idempotency_key": "prod-http-1"},
        auto_approve=True,
    )

    claim = control.claim({"worker_id": "windows-01", "lease_seconds": 30})
    report = control.queue_contamination_report()

    assert claim is not None
    assert claim["job_id"] == wanted["id"]
    assert claim["job_type"] == "http_manifest"
    assert report["denied_job_type_count"] >= 1
    assert report["denied_fixture_prefix_count"] >= 1
    # Fixture http_manifest remains queued and unclaimed.
    remaining = {job["id"] for job in orchestrator.store.list(limit=20, status="queued")}
    assert "probe-no-promotion-deadbeef" in remaining
    assert "fixture-source-probe-1" in remaining
