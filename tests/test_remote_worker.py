from __future__ import annotations

import json
import zipfile
from pathlib import Path

from scripts.yzu_cluster.remote_worker import execute_http_manifest, spool_job_path


class FakeControlClient:
    def __init__(self) -> None:
        self.heartbeats: list[dict] = []
        self.uploads: list[Path] = []
        self.usage_reports: list[dict] = []
        self.completions: list[dict] = []

    def heartbeat(self, job_id: str, **payload):
        self.heartbeats.append({"job_id": job_id, **payload})
        return {"status": "running"}

    def upload(self, job_id: str, *, worker_id: str, attempt: int, path: Path):
        self.uploads.append(path)
        return {
            "artifact": f"data/jobs/{job_id}/remote_artifacts/{path.name}",
            "bytes": path.stat().st_size,
            "sha256": "proof",
            "worker_id": worker_id,
            "attempt": attempt,
        }

    def usage(self, job_id: str, payload: dict):
        self.usage_reports.append({"job_id": job_id, **payload})
        return {"samples": 1}

    def complete(self, job_id: str, payload: dict):
        self.completions.append({"job_id": job_id, **payload})
        return {"status": "completed", "job_id": job_id}


def test_remote_http_worker_executes_uploads_and_completes(tmp_path: Path) -> None:
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
print('collected')
""".strip()
        + "\n",
        encoding="utf-8",
    )
    client = FakeControlClient()
    claim = {
        "job_id": "remote-worker-test",
        "job_type": "http_manifest",
        "attempt": 1,
        "worker_id": "windows-01",
        "plan": {
            "job_type": "http_manifest",
            "items": [{"url": "https://example.test/data.csv", "name": "data.csv"}],
            "timeout_seconds": 30,
        },
    }

    completed = execute_http_manifest(
        client,
        claim,
        repo_root=tmp_path,
        spool=tmp_path / "spool",
        lease_seconds=30,
        heartbeat_seconds=10,
    )

    assert completed == {"status": "completed", "job_id": "remote-worker-test"}
    assert client.heartbeats[0]["stage"] == "running"
    assert len(client.uploads) == 1
    with zipfile.ZipFile(client.uploads[0]) as archive:
        assert archive.read("raw/result.csv").startswith(b"timestamp,value")
    assert client.usage_reports[0]["worker_id"] == "windows-01"
    assert client.usage_reports[0]["network_bytes"] > 0
    result = client.completions[0]["result"]
    assert result["collect_mode"] == "remote_control"
    assert result["artifacts"][0]["artifact"].endswith("artifact.zip")
    assert result["artifacts"][0]["worker"] == "windows-01"


def test_spool_job_path_is_portable_and_collision_resistant(tmp_path: Path) -> None:
    spool = tmp_path / "spool"
    first = spool_job_path(spool, r"discover-submit:abc\attempt")
    second = spool_job_path(spool, "discover-submit_abc_attempt")

    assert first.parent == spool
    assert second.parent == spool
    assert first != second
    assert ":" not in first.name
    assert "\\" not in first.name
    assert "/" not in first.name
    assert first.name.startswith("discover-submit_abc_attempt-")


def test_remote_http_worker_accepts_windows_invalid_job_id(tmp_path: Path) -> None:
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
""".strip()
        + "\n",
        encoding="utf-8",
    )
    client = FakeControlClient()
    claim = {
        "job_id": r"discover-submit:abc\attempt",
        "job_type": "http_manifest",
        "attempt": 1,
        "worker_id": "windows-01",
        "plan": {
            "job_type": "http_manifest",
            "items": [{"url": "https://example.test/data.csv", "name": "data.csv"}],
            "timeout_seconds": 30,
        },
    }

    completed = execute_http_manifest(
        client,
        claim,
        repo_root=tmp_path,
        spool=tmp_path / "spool",
        lease_seconds=30,
        heartbeat_seconds=10,
    )

    assert completed["status"] == "completed"
    manifest = next((tmp_path / "spool").rglob("manifest.json"))
    assert json.loads(manifest.read_text(encoding="utf-8"))["job_id"] == claim["job_id"]
