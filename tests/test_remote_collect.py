from __future__ import annotations

import json
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

import pytest

from scripts.cluster_agent import remote_collect
from scripts.cluster_agent.remote_collect import collect_manifest


@pytest.fixture
def http_origin(monkeypatch):
    """Local collector origin with an explicitly test-scoped network adapter.

    Production collection must reject loopback targets. These tests exercise the
    downloader, partial-artifact, and checksum contracts against a local fixture,
    so they replace only the module's network adapter for the fixture lifetime.
    """

    def validate_fixture_url(url: str) -> dict:
        parsed = urlsplit(str(url or ""))
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("item URL must use http or https")
        return {
            "url": parsed.geturl(),
            "scheme": parsed.scheme,
            "host": parsed.hostname,
            "resolved_addresses": ["127.0.0.1"],
        }

    def open_fixture_url(url: str, *, headers: dict[str, str], timeout: int):
        return urlopen(Request(url, headers=headers, method="GET"), timeout=timeout)

    monkeypatch.setattr(remote_collect, "_validate_url", validate_fixture_url)
    monkeypatch.setattr(remote_collect, "open_pinned_public_url", open_fixture_url)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            if self.path == "/data.csv":
                body = b"timestamp,value\n2026-07-20,1\n"
                self.send_response(200)
                self.send_header("Content-Type", "text/csv")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if self.path == "/metadata.json":
                body = b'{"source":"acceptance"}\n'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            self.send_response(404)
            self.end_headers()

        def log_message(self, _format, *_args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _write_manifest(path: Path, items: list[dict]) -> None:
    path.write_text(
        json.dumps({"job_id": "collector-contract", "shard": 0, "items": items}),
        encoding="utf-8",
    )


def test_collect_manifest_writes_proof_bearing_zip(tmp_path: Path, http_origin: str) -> None:
    manifest = tmp_path / "manifest.json"
    artifact = tmp_path / "artifact.zip"
    _write_manifest(
        manifest,
        [
            {"url": f"{http_origin}/data.csv", "name": "data.csv"},
            {"url": f"{http_origin}/metadata.json", "name": "metadata.json"},
        ],
    )

    code, report = collect_manifest(
        manifest,
        artifact,
        workers=2,
        timeout=5,
        retries=0,
        delay=0,
    )

    assert code == 0
    assert report["succeeded"] == 2
    assert report["failed"] == 0
    assert artifact.is_file()
    with zipfile.ZipFile(artifact) as archive:
        assert archive.read("raw/data.csv").startswith(b"timestamp,value")
        assert json.loads(archive.read("raw/metadata.json"))["source"] == "acceptance"
        archived_report = json.loads(archive.read("collect_report.json"))
        assert archived_report["succeeded"] == 2
        assert all(row["sha256"] and row["bytes"] > 0 for row in archived_report["items"])
        assert json.loads(archive.read("manifest.json"))["job_id"] == "collector-contract"


def test_collect_manifest_returns_partial_exit_with_usable_artifact(tmp_path: Path, http_origin: str) -> None:
    manifest = tmp_path / "manifest.json"
    artifact = tmp_path / "artifact.zip"
    _write_manifest(
        manifest,
        [
            {"url": f"{http_origin}/data.csv", "name": "result.csv"},
            {"url": f"{http_origin}/missing", "name": "missing.json"},
        ],
    )

    code, report = collect_manifest(
        manifest,
        artifact,
        workers=2,
        timeout=5,
        retries=0,
        delay=0,
    )

    assert code == 2
    assert report["succeeded"] == 1
    assert report["failed"] == 1
    assert artifact.is_file()
    with zipfile.ZipFile(artifact) as archive:
        assert "raw/result.csv" in archive.namelist()
        assert "raw/missing.json" not in archive.namelist()


def test_collect_manifest_rejects_unusable_or_unproven_inputs(tmp_path: Path, http_origin: str) -> None:
    manifest = tmp_path / "manifest.json"
    artifact = tmp_path / "artifact.zip"
    _write_manifest(
        manifest,
        [
            {"url": "file:///etc/passwd", "name": "forbidden.txt"},
            {
                "url": f"{http_origin}/data.csv",
                "name": "wrong-proof.csv",
                "sha256": "0" * 64,
            },
        ],
    )

    code, report = collect_manifest(
        manifest,
        artifact,
        workers=1,
        timeout=5,
        retries=0,
        delay=0,
    )

    assert code == 1
    assert report["succeeded"] == 0
    assert report["failed"] == 2
    assert not artifact.exists()
    assert any("http or https" in row["error"] for row in report["items"])
    assert any("sha256" in row["error"] for row in report["items"])
