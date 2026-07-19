"""Pull-based authenticated worker for the YZU control plane.

The first production lane is intentionally narrow: ``http_manifest`` only. The
worker downloads source items into a ZIP, uploads that artifact to the controller,
and lets the controller own materialisation, GDrive verification, registry
promotion, and Library registration.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from .worker_control import TOKEN_ENV


class ControlClient:
    def __init__(self, base_url: str, token: str, *, timeout: int = 60) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def _request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        content: bytes | None = None,
        headers: dict[str, str] | None = None,
        timeout: int | None = None,
    ) -> Any:
        body = content
        request_headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
            **(headers or {}),
        }
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            request_headers["Content-Type"] = "application/json"
        request = Request(
            f"{self.base_url}{path}",
            data=body,
            headers=request_headers,
            method=method,
        )
        try:
            with urlopen(request, timeout=timeout or self.timeout) as response:
                raw = response.read()
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"control plane HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise RuntimeError(f"control plane unavailable: {exc.reason}") from exc
        if not raw:
            return None
        return json.loads(raw.decode("utf-8"))

    def join(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/v1/workers/join", payload=payload)

    def claim(self, worker_id: str, *, lease_seconds: int) -> dict[str, Any] | None:
        response = self._request(
            "POST",
            "/v1/workers/claim",
            payload={"worker_id": worker_id, "lease_seconds": lease_seconds},
        )
        return response.get("claim") if isinstance(response, dict) else None

    def heartbeat(
        self,
        job_id: str,
        *,
        worker_id: str,
        attempt: int,
        lease_seconds: int,
        stage: str = "running",
        progress: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/v1/jobs/{quote(job_id, safe='')}/heartbeat",
            payload={
                "worker_id": worker_id,
                "attempt": attempt,
                "lease_seconds": lease_seconds,
                "stage": stage,
                "progress": progress or {},
            },
        )

    def usage(self, job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/v1/jobs/{quote(job_id, safe='')}/usage",
            payload=payload,
        )

    def upload(
        self,
        job_id: str,
        *,
        worker_id: str,
        attempt: int,
        path: Path,
    ) -> dict[str, Any]:
        content = path.read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        return self._request(
            "PUT",
            f"/v1/jobs/{quote(job_id, safe='')}/artifacts/{quote(path.name, safe='')}",
            content=content,
            headers={
                "Content-Type": "application/octet-stream",
                "X-YZU-Worker-Id": worker_id,
                "X-YZU-Attempt": str(attempt),
                "X-Content-Sha256": digest,
            },
            timeout=max(self.timeout, 1800),
        )

    def complete(self, job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/v1/jobs/{quote(job_id, safe='')}/complete",
            payload=payload,
            timeout=max(self.timeout, 7200),
        )

    def fail(self, job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/v1/jobs/{quote(job_id, safe='')}/fail",
            payload=payload,
        )


def _memory_mb() -> float | None:
    if os.name == "nt":
        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("length", ctypes.c_ulong),
                ("memory_load", ctypes.c_ulong),
                ("total_phys", ctypes.c_ulonglong),
                ("avail_phys", ctypes.c_ulonglong),
                ("total_page_file", ctypes.c_ulonglong),
                ("avail_page_file", ctypes.c_ulonglong),
                ("total_virtual", ctypes.c_ulonglong),
                ("avail_virtual", ctypes.c_ulonglong),
                ("avail_extended_virtual", ctypes.c_ulonglong),
            ]

        status = MemoryStatus()
        status.length = ctypes.sizeof(MemoryStatus)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return round(float(status.avail_phys) / (1024 * 1024), 2)
        return None
    try:
        return round(float(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_AVPHYS_PAGES")) / (1024 * 1024), 2)
    except (AttributeError, OSError, ValueError):
        return None


def measured_capacity(spool: Path) -> dict[str, float]:
    capacity: dict[str, float] = {"gpu_count": 0.0}
    if os.cpu_count() is not None:
        capacity["cpu_cores"] = float(os.cpu_count() or 0)
    memory = _memory_mb()
    if memory is not None:
        capacity["memory_mb"] = memory
    try:
        capacity["disk_mb"] = round(float(shutil.disk_usage(spool).free) / (1024 * 1024), 2)
    except OSError:
        pass
    return capacity


class HeartbeatLoop:
    def __init__(
        self,
        client: ControlClient,
        claim: dict[str, Any],
        *,
        lease_seconds: int,
        interval_seconds: float,
    ) -> None:
        self.client = client
        self.claim = claim
        self.lease_seconds = lease_seconds
        self.interval_seconds = max(1.0, interval_seconds)
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.error: Exception | None = None

    def start(self) -> "HeartbeatLoop":
        self.client.heartbeat(
            self.claim["job_id"],
            worker_id=self.claim["worker_id"],
            attempt=int(self.claim["attempt"]),
            lease_seconds=self.lease_seconds,
            stage="running",
        )
        self.thread = threading.Thread(target=self._run, daemon=True, name=f"yzu-heartbeat:{self.claim['job_id']}")
        self.thread.start()
        return self

    def _run(self) -> None:
        while not self.stop_event.wait(self.interval_seconds):
            try:
                self.client.heartbeat(
                    self.claim["job_id"],
                    worker_id=self.claim["worker_id"],
                    attempt=int(self.claim["attempt"]),
                    lease_seconds=self.lease_seconds,
                    stage="running",
                )
            except Exception as exc:  # noqa: BLE001
                self.error = exc
                self.stop_event.set()

    def stop(self) -> None:
        self.stop_event.set()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=self.interval_seconds + 2)

    def raise_if_lost(self) -> None:
        if self.error:
            raise RuntimeError(f"worker heartbeat failed: {self.error}") from self.error


def execute_http_manifest(
    client: ControlClient,
    claim: dict[str, Any],
    *,
    repo_root: Path,
    spool: Path,
    lease_seconds: int,
    heartbeat_seconds: float,
) -> dict[str, Any]:
    plan = claim.get("plan") or {}
    items = list(plan.get("items") or [])
    if not items:
        raise ValueError("http_manifest claim contains no downloadable items")
    job_id = str(claim["job_id"])
    attempt = int(claim["attempt"])
    work = spool / job_id / f"attempt-{attempt}"
    work.mkdir(parents=True, exist_ok=True)
    manifest_path = work / "manifest.json"
    artifact_path = work / "artifact.zip"
    manifest_path.write_text(
        json.dumps({"job_id": job_id, "shard": 0, "items": items}, indent=2),
        encoding="utf-8",
    )
    script = repo_root / "scripts/cluster_agent/remote_collect.py"
    if not script.is_file():
        raise FileNotFoundError(f"remote collector not found: {script}")
    command = [
        sys.executable,
        str(script),
        "--manifest",
        str(manifest_path),
        "--artifact",
        str(artifact_path),
        "--workers",
        str(min(int(plan.get("per_node_workers", 2)), 4)),
        "--timeout",
        str(min(int(plan.get("request_timeout", 90)), 300)),
        "--retries",
        str(min(int(plan.get("retries", 3)), 5)),
        "--delay",
        str(max(float(plan.get("delay_seconds", 0.25)), 0.1)),
    ]
    heartbeat = HeartbeatLoop(
        client,
        claim,
        lease_seconds=lease_seconds,
        interval_seconds=heartbeat_seconds,
    ).start()
    started = time.monotonic()
    try:
        process = subprocess.run(
            command,
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=int(plan.get("timeout_seconds", 7200)),
            check=False,
        )
    finally:
        heartbeat.stop()
    heartbeat.raise_if_lost()
    if process.returncode not in {0, 2}:
        raise RuntimeError(
            f"remote_collect exited {process.returncode}: {(process.stderr or process.stdout)[-1000:]}"
        )
    if not artifact_path.is_file() or artifact_path.stat().st_size < 32:
        raise RuntimeError("remote collector produced no usable artifact ZIP")

    uploaded = client.upload(
        job_id,
        worker_id=claim["worker_id"],
        attempt=attempt,
        path=artifact_path,
    )
    elapsed = max(0.0, time.monotonic() - started)
    client.usage(
        job_id,
        {
            "worker_id": claim["worker_id"],
            "attempt": attempt,
            "disk_written_mb": round(artifact_path.stat().st_size / (1024 * 1024), 6),
            "network_bytes": artifact_path.stat().st_size,
            "api_calls": len(items),
        },
    )
    return client.complete(
        job_id,
        {
            "worker_id": claim["worker_id"],
            "attempt": attempt,
            "result": {
                "artifacts": [
                    {
                        "artifact": uploaded["artifact"],
                        "bytes": uploaded["bytes"],
                        "sha256": uploaded["sha256"],
                        "worker": claim["worker_id"],
                        "worker_exit": process.returncode,
                    }
                ],
                "collect_mode": "remote_control",
                "worker_elapsed_seconds": elapsed,
                "collect_report": (process.stdout or "")[-1000:],
            },
        },
    )


def run_worker(
    *,
    controller: str,
    token: str,
    worker_id: str,
    pool: str,
    capabilities: list[str],
    repo_root: Path,
    spool: Path,
    poll_seconds: float,
    lease_seconds: int,
    heartbeat_seconds: float,
    once: bool,
    keep_artifacts: bool,
) -> None:
    client = ControlClient(controller, token)
    spool.mkdir(parents=True, exist_ok=True)
    while True:
        client.join(
            {
                "worker_id": worker_id,
                "pool": pool,
                "status": "online",
                "capabilities": capabilities,
                "capacity": measured_capacity(spool),
            }
        )
        claim = client.claim(worker_id, lease_seconds=lease_seconds)
        if claim is None:
            if once:
                return
            time.sleep(poll_seconds)
            continue
        try:
            if claim.get("job_type") != "http_manifest":
                raise ValueError(f"unsupported remote job type: {claim.get('job_type')}")
            execute_http_manifest(
                client,
                claim,
                repo_root=repo_root,
                spool=spool,
                lease_seconds=lease_seconds,
                heartbeat_seconds=heartbeat_seconds,
            )
            if not keep_artifacts:
                shutil.rmtree(spool / claim["job_id"], ignore_errors=True)
        except Exception as exc:  # noqa: BLE001
            try:
                client.fail(
                    claim["job_id"],
                    {
                        "worker_id": worker_id,
                        "attempt": claim["attempt"],
                        "error": f"{type(exc).__name__}: {exc}",
                        "retryable": not isinstance(exc, (ValueError, FileNotFoundError)),
                    },
                )
            except Exception:
                pass
            if once:
                raise
        if once:
            return


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a bounded YZU HTTP collection worker")
    parser.add_argument("--controller", required=True, help="Worker control base URL, preferably over Tailscale")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--worker-id", default=socket.gethostname())
    parser.add_argument("--pool", default="windows_lab")
    parser.add_argument("--capabilities", default="http,python")
    parser.add_argument("--spool", default=".yzu-worker-spool")
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    parser.add_argument("--lease-seconds", type=int, default=120)
    parser.add_argument("--heartbeat-seconds", type=float, default=30.0)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--keep-artifacts", action="store_true")
    args = parser.parse_args()
    token = os.environ.get(TOKEN_ENV, "").strip()
    if not token:
        raise SystemExit(f"{TOKEN_ENV} is required")
    repo_root = Path(args.repo_root).resolve()
    spool = Path(args.spool)
    if not spool.is_absolute():
        spool = (repo_root / spool).resolve()
    capabilities = [item.strip() for item in args.capabilities.split(",") if item.strip()]
    run_worker(
        controller=args.controller,
        token=token,
        worker_id=args.worker_id,
        pool=args.pool,
        capabilities=capabilities,
        repo_root=repo_root,
        spool=spool,
        poll_seconds=max(1.0, args.poll_seconds),
        lease_seconds=max(10, args.lease_seconds),
        heartbeat_seconds=max(1.0, min(args.heartbeat_seconds, args.lease_seconds / 2)),
        once=args.once,
        keep_artifacts=args.keep_artifacts,
    )


if __name__ == "__main__":
    main()
