from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from scripts.yzu_cluster.orchestrator import YzuOrchestrator
from scripts.yzu_cluster.worker_control import WorkerControlPlane


def test_remote_completion_renews_lease_during_controller_finalization(tmp_path: Path) -> None:
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
                    "lease_seconds": 1,
                    "lease_heartbeat_seconds": 0.05,
                },
                "operations": {"disable_local_http_collect": False},
                "agent": {"allowed_job_types": ["http_manifest"]},
                "worker_pools": {},
                "storage": {},
            }
        ),
        encoding="utf-8",
    )
    orchestrator = YzuOrchestrator(tmp_path)
    control = WorkerControlPlane(orchestrator, token="secret-token")
    job = orchestrator.submit(
        "Remote finalization",
        {"job_type": "http_manifest", "url": "https://8.8.8.8", "outputs": ["remote-output"]},
        {"_ops_internal": True, "idempotency_key": "remote-finalization"},
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
    claim = control.claim({"worker_id": "windows-01", "lease_seconds": 1})
    assert claim is not None
    control.heartbeat(
        job["id"],
        {"worker_id": "windows-01", "attempt": 1, "stage": "running", "lease_seconds": 1},
    )

    def slow_finalize(_job_id, _plan, _result):
        time.sleep(1.3)
        return []

    orchestrator.set_on_job_completed(slow_finalize)
    reaped: list[dict] = []

    def reap_after_initial_lease() -> None:
        time.sleep(1.05)
        reaped.extend(orchestrator.runtime.reap_expired())

    reaper = threading.Thread(target=reap_after_initial_lease, daemon=True)
    reaper.start()
    completed = control.complete(
        job["id"],
        {
            "worker_id": "windows-01",
            "attempt": 1,
            "result": {"outputs": ["remote-output"]},
        },
    )
    reaper.join(timeout=2)

    assert reaped == []
    assert completed["lifecycle"]["stage"] == "completed"
    assert completed["runtime"]["attempt"] == 1
