from __future__ import annotations

import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from fastapi.testclient import TestClient

from scripts.yzu_cluster.orchestrator import YzuOrchestrator
from scripts.yzu_cluster.remote_worker import ControlClient
from scripts.yzu_cluster.worker_control import MAX_ARTIFACT_ENV, WorkerControlPlane, create_app


def _orchestrator(root: Path) -> YzuOrchestrator:
    (root / "config").mkdir()
    (root / "config/yzu_cluster.json").write_text(
        json.dumps(
            {
                "controller": {"hostname": "optiplex-test", "jobs_root": "data/jobs", "status_root": "data/status"},
                "runtime": {"controller_heartbeat_seconds": 0, "lease_seconds": 30},
                "operations": {"disable_local_http_collect": False},
                "agent": {"allowed_job_types": ["http_manifest"]},
                "worker_pools": {},
                "storage": {},
            }
        ),
        encoding="utf-8",
    )
    return YzuOrchestrator(root)


def _claimed(orchestrator: YzuOrchestrator) -> tuple[str, dict]:
    job = orchestrator.submit(
        "Stream artifact",
        {"job_type": "http_manifest", "url": "https://8.8.8.8/data.csv"},
        {"_ops_internal": True, "idempotency_key": "stream-artifact"},
        auto_approve=True,
    )
    control = WorkerControlPlane(orchestrator, token="secret-token")
    control.join(
        {"worker_id": "windows-01", "pool": "windows_lab", "capabilities": ["http"], "capacity": {"cpu_cores": 2}}
    )
    claim = control.claim({"worker_id": "windows-01", "lease_seconds": 30})
    assert claim is not None
    return job["id"], {"worker_id": "windows-01", "attempt": claim["attempt"]}


def test_worker_control_streams_chunked_artifact_without_request_buffering(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv(MAX_ARTIFACT_ENV, "64")
    orchestrator = _orchestrator(tmp_path)
    job_id, owner = _claimed(orchestrator)
    client = TestClient(create_app(orchestrator=orchestrator, token="secret-token"))
    content = [b"first-", b"second-", b"third"]
    digest = hashlib.sha256(b"".join(content)).hexdigest()

    response = client.put(
        f"/v1/jobs/{job_id}/artifacts/output.zip",
        headers={
            "Authorization": "Bearer secret-token",
            "X-YZU-Worker-Id": owner["worker_id"],
            "X-YZU-Attempt": str(owner["attempt"]),
            "X-Content-Sha256": digest,
        },
        content=iter(content),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["bytes"] == len(b"".join(content))
    assert payload["sha256"] == digest
    assert (tmp_path / payload["artifact"]).read_bytes() == b"".join(content)


def test_worker_control_rejects_chunked_artifact_over_limit_and_cleans_part(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv(MAX_ARTIFACT_ENV, "8")
    orchestrator = _orchestrator(tmp_path)
    job_id, owner = _claimed(orchestrator)
    client = TestClient(create_app(orchestrator=orchestrator, token="secret-token"))

    response = client.put(
        f"/v1/jobs/{job_id}/artifacts/too-large.zip",
        headers={
            "Authorization": "Bearer secret-token",
            "X-YZU-Worker-Id": owner["worker_id"],
            "X-YZU-Attempt": str(owner["attempt"]),
        },
        content=iter([b"12345", b"6789"]),
    )

    assert response.status_code == 413
    artifact_dir = orchestrator.jobs_root / job_id / "remote_artifacts"
    assert not list(artifact_dir.iterdir())


def test_control_client_streams_file_without_path_read_bytes(tmp_path: Path, monkeypatch) -> None:
    payload = b"a" * (2 * 1024 * 1024 + 17)
    artifact = tmp_path / "artifact.zip"
    artifact.write_bytes(payload)
    captured: dict[str, object] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_PUT(self):
            length = int(self.headers["Content-Length"])
            captured["length"] = length
            captured["body"] = self.rfile.read(length)
            captured["digest"] = self.headers["X-Content-Sha256"]
            response = json.dumps({"artifact": "stored/artifact.zip", "bytes": length, "sha256": captured["digest"]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)

        def log_message(self, *_args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setattr(Path, "read_bytes", lambda _self: (_ for _ in ()).throw(AssertionError("read_bytes used")))
    try:
        client = ControlClient(f"http://127.0.0.1:{server.server_port}", "secret-token")
        result = client.upload("job-stream", worker_id="windows-01", attempt=1, path=artifact)
    finally:
        server.shutdown()
        thread.join(timeout=2)

    assert result["bytes"] == len(payload)
    assert captured["length"] == len(payload)
    assert captured["body"] == payload
    assert captured["digest"] == hashlib.sha256(payload).hexdigest()
