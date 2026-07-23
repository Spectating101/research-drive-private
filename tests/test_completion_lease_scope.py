from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from scripts.yzu_cluster.orchestrator import YzuOrchestrator
from scripts.yzu_cluster.remote_worker import execute_http_manifest


def _write_runtime_config(root: Path) -> None:
    (root / "config").mkdir()
    (root / "config/yzu_cluster.json").write_text(
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


def test_local_completion_renews_lease_through_authoritative_finalization(tmp_path: Path) -> None:
    _write_runtime_config(tmp_path)
    orchestrator = YzuOrchestrator(tmp_path)
    orchestrator.executor.execute = lambda _job_id, _plan: {"outputs": ["local-output"]}
    job = orchestrator.submit(
        "Local finalization",
        {
            "job_type": "http_manifest",
            "items": [{"url": "https://8.8.8.8/data.csv"}],
            "outputs": ["local-output"],
        },
        {"idempotency_key": "local-finalization"},
        auto_approve=True,
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
    completed = orchestrator.execute_job(job["id"])
    reaper.join(timeout=2)

    assert reaped == []
    assert completed["lifecycle"]["stage"] == "completed"
    assert completed["runtime"]["attempt"] == 1


class SlowUploadClient:
    def __init__(self) -> None:
        self.heartbeats: list[float] = []
        self.completions: list[dict] = []

    def heartbeat(self, _job_id: str, **_payload):
        self.heartbeats.append(time.monotonic())
        return {"status": "running"}

    def upload(self, job_id: str, *, worker_id: str, attempt: int, path: Path):
        time.sleep(1.2)
        return {
            "artifact": f"data/jobs/{job_id}/remote_artifacts/{path.name}",
            "bytes": path.stat().st_size,
            "sha256": "proof",
            "worker_id": worker_id,
            "attempt": attempt,
        }

    def usage(self, _job_id: str, _payload: dict):
        return {"samples": 1}

    def complete(self, job_id: str, payload: dict):
        self.completions.append(payload)
        return {"status": "completed", "job_id": job_id}


def test_remote_worker_keeps_lease_alive_through_slow_artifact_upload(tmp_path: Path) -> None:
    script = tmp_path / "scripts/cluster_agent/remote_collect.py"
    script.parent.mkdir(parents=True)
    script.write_text(
        """
import argparse
import zipfile
parser = argparse.ArgumentParser()
parser.add_argument('--manifest')
parser.add_argument('--artifact')
parser.add_argument('--workers')
parser.add_argument('--timeout')
parser.add_argument('--retries')
parser.add_argument('--delay')
args = parser.parse_args()
with zipfile.ZipFile(args.artifact, 'w') as archive:
    archive.writestr('raw/result.csv', 'timestamp,value\\n2026-01-01,1\\n')
""".strip() + "\n",
        encoding="utf-8",
    )
    client = SlowUploadClient()
    claim = {
        "job_id": "slow-upload",
        "job_type": "http_manifest",
        "attempt": 1,
        "worker_id": "windows-01",
        "plan": {
            "job_type": "http_manifest",
            "items": [{"url": "https://8.8.8.8/data.csv", "name": "data.csv"}],
            "timeout_seconds": 30,
        },
    }

    completed = execute_http_manifest(
        client,
        claim,
        repo_root=tmp_path,
        spool=tmp_path / "spool",
        lease_seconds=3,
        heartbeat_seconds=1,
    )

    assert completed == {"status": "completed", "job_id": "slow-upload"}
    assert len(client.heartbeats) >= 2
    assert len(client.completions) == 1
