"""Authenticated HTTP control plane for remote YZU workers.

The controller remains authoritative for lifecycle, archive, registry, and legacy
compatibility state. Remote workers only join, claim, heartbeat, report usage,
upload attempt-fenced artifacts, and submit results through this surface.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import os
from pathlib import Path
from typing import Any, Mapping

from ._interop_common import Claim

TOKEN_ENV = "YZU_WORKER_CONTROL_TOKEN"
MAX_ARTIFACT_ENV = "YZU_WORKER_MAX_ARTIFACT_BYTES"
ACTIVE_ATTEMPT_STAGES = {"assigned", "running", "validating", "archiving", "registering"}


def _bearer_token(authorization: str | None, explicit: str | None = None) -> str:
    if explicit:
        return explicit.strip()
    value = str(authorization or "").strip()
    if value.lower().startswith("bearer "):
        return value[7:].strip()
    return value


class WorkerControlPlane:
    """Pure service layer used by both FastAPI and focused contract tests."""

    def __init__(self, orchestrator: Any, *, token: str, max_artifact_bytes: int | None = None) -> None:
        token = str(token or "").strip()
        if not token:
            raise RuntimeError(f"{TOKEN_ENV} is required for the worker control plane")
        self.orchestrator = orchestrator
        self.token = token
        configured_limit = max_artifact_bytes or int(os.environ.get(MAX_ARTIFACT_ENV, 512 * 1024 * 1024))
        self.max_artifact_bytes = max(1, int(configured_limit))

    def authorize(self, candidate: str | None) -> None:
        supplied = str(candidate or "").strip()
        if not supplied or not hmac.compare_digest(supplied, self.token):
            raise PermissionError("invalid worker control token")

    @staticmethod
    def _claim_payload(claim: Claim, job: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "run_id": claim.run_id,
            "job_id": claim.job_id,
            "job_type": claim.job_type,
            "attempt": claim.attempt,
            "worker_id": claim.worker_id,
            "required_capabilities": list(claim.required_capabilities),
            "inputs": list(claim.inputs),
            "outputs": list(claim.outputs),
            "resource_requirements": dict(claim.resource_requirements),
            "lease_expires_at": claim.lease_expires_at,
            "title": job.get("title"),
            "plan": job.get("plan") or {},
            "request": job.get("request") or {},
        }

    def _claim_for_attempt(self, job_id: str, worker_id: str, attempt: int) -> Claim:
        snapshot = self.orchestrator.runtime.snapshot(job_id)
        current_attempt = int(snapshot.get("attempt") or 0)
        assigned_worker = str(snapshot.get("assigned_worker") or snapshot.get("worker_id") or "")
        stage = str(snapshot.get("status") or snapshot.get("stage") or "")
        if current_attempt != int(attempt):
            raise PermissionError(
                f"stale execution attempt: expected {attempt}, current {current_attempt}"
            )
        if assigned_worker != worker_id:
            raise PermissionError("worker does not own this execution attempt")
        if stage not in ACTIVE_ATTEMPT_STAGES:
            raise ValueError(f"runtime job is {stage}, not writable by a worker")
        requirements = snapshot.get("resource_requirements") or snapshot.get("requirements") or {}
        job = self.orchestrator.store.get(job_id)
        plan = job.get("plan") or {}
        return Claim(
            run_id=str(snapshot["run_id"]),
            job_id=job_id,
            job_type=str(snapshot.get("job_type") or plan.get("job_type") or "legacy_job"),
            attempt=current_attempt,
            worker_id=worker_id,
            required_capabilities=tuple(snapshot.get("required_capabilities") or ()),
            inputs=tuple(snapshot.get("inputs") or ()),
            outputs=tuple(snapshot.get("outputs") or ()),
            resource_requirements=tuple(
                sorted(
                    (str(key), float(value))
                    for key, value in dict(requirements).items()
                    if key != "priority" and isinstance(value, (int, float))
                )
            ),
            lease_expires_at=str(snapshot.get("lease_expires_at") or ""),
        )

    def join(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self.orchestrator.runtime.join_worker(payload)

    def claim(self, payload: Mapping[str, Any]) -> dict[str, Any] | None:
        worker_id = str(payload.get("worker_id") or "").strip()
        if not worker_id:
            raise ValueError("worker_id is required")
        self.orchestrator.runtime.reap_expired()
        self.orchestrator.reconcile_runtime()
        for job in self.orchestrator.store.list(limit=500, status="queued"):
            self.orchestrator.runtime.ensure(job)
        claim = self.orchestrator.runtime.claim_next(
            worker_id,
            lease_seconds=int(payload.get("lease_seconds") or self.orchestrator.runtime.lease_seconds),
            reap_expired=False,
        )
        if claim is None:
            return None
        job = self.orchestrator.store.get(claim.job_id)
        return self._claim_payload(claim, job)

    def heartbeat(self, job_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        worker_id = str(payload.get("worker_id") or "").strip()
        attempt = int(payload.get("attempt") or 0)
        if not worker_id or attempt < 1:
            raise ValueError("worker_id and positive attempt are required")
        self._claim_for_attempt(job_id, worker_id, attempt)
        return self.orchestrator.runtime.heartbeat(
            job_id,
            worker_id,
            attempt=attempt,
            progress=payload.get("progress") if isinstance(payload.get("progress"), Mapping) else {},
            stage=str(payload.get("stage") or "") or None,
            lease_seconds=int(payload.get("lease_seconds") or self.orchestrator.runtime.lease_seconds),
        )

    def usage(self, job_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        worker_id = str(payload.get("worker_id") or "").strip()
        attempt = int(payload.get("attempt") or 0)
        if not worker_id or attempt < 1:
            raise ValueError("worker_id and positive attempt are required")
        claim = self._claim_for_attempt(job_id, worker_id, attempt)
        values = {
            key: payload.get(key)
            for key in (
                "cpu_seconds",
                "memory_peak_mb",
                "disk_written_mb",
                "network_bytes",
                "api_calls",
                "storage_bytes",
            )
            if payload.get(key) is not None
        }
        with self.orchestrator.runtime._lock:
            return self.orchestrator.runtime.store.record_usage(
                claim.run_id,
                worker_id=worker_id,
                expected_attempt=attempt,
                **values,
            )

    def upload_artifact(
        self,
        job_id: str,
        *,
        worker_id: str,
        attempt: int,
        name: str,
        content: bytes,
        expected_sha256: str | None = None,
    ) -> dict[str, Any]:
        self._claim_for_attempt(job_id, worker_id, attempt)
        safe_name = Path(str(name or "")).name
        if not safe_name or safe_name != name or safe_name in {".", ".."}:
            raise ValueError("artifact name must be a plain filename")
        if len(content) > self.max_artifact_bytes:
            raise ValueError(f"artifact exceeds {self.max_artifact_bytes} byte limit")
        digest = hashlib.sha256(content).hexdigest()
        expected = str(expected_sha256 or "").strip().lower()
        if expected and not hmac.compare_digest(expected, digest):
            raise ValueError("artifact sha256 does not match request proof")

        destination = self.orchestrator.jobs_root / job_id / "remote_artifacts" / safe_name
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".part")
        temporary.write_bytes(content)
        temporary.replace(destination)
        try:
            relative = destination.relative_to(self.orchestrator.repo_root)
        except ValueError as exc:
            destination.unlink(missing_ok=True)
            raise ValueError("artifact destination is outside the repository") from exc
        return {
            "artifact": str(relative),
            "name": safe_name,
            "bytes": len(content),
            "sha256": digest,
            "worker_id": worker_id,
            "attempt": attempt,
        }

    def complete(self, job_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        worker_id = str(payload.get("worker_id") or "").strip()
        attempt = int(payload.get("attempt") or 0)
        result = payload.get("result") if isinstance(payload.get("result"), Mapping) else {}
        if not worker_id or attempt < 1:
            raise ValueError("worker_id and positive attempt are required")
        claim = self._claim_for_attempt(job_id, worker_id, attempt)
        job = self.orchestrator.store.get(job_id)
        plan = job.get("plan") or {}
        result = dict(result)
        if (
            str(plan.get("job_type") or "") == "http_manifest"
            and result.get("artifacts")
            and not isinstance(result.get("materialized"), Mapping)
        ):
            from scripts.yzu_cluster.acquisitions import materialize_job

            result = materialize_job(
                self.orchestrator.repo_root,
                job_id,
                plan,
                result,
                cfg=self.orchestrator.cfg,
            )
        if self.orchestrator._on_job_completed:
            promoted = self.orchestrator._on_job_completed(job_id, plan, result)
            if promoted:
                result["registry_promotion"] = promoted
        runtime_state = self.orchestrator.runtime.complete(claim, result)
        self.orchestrator.store.update(job_id, "completed", result=result)
        if self.orchestrator._on_job_post_completed:
            try:
                self.orchestrator._on_job_post_completed(
                    job_id,
                    plan,
                    result,
                    runtime_state,
                )
            except Exception as exc:  # noqa: BLE001
                self.orchestrator.store.event(
                    job_id,
                    "warning",
                    f"Post-registration follow-up failed: {exc}",
                )
        return self.orchestrator.get_job(job_id)

    def fail(self, job_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        worker_id = str(payload.get("worker_id") or "").strip()
        attempt = int(payload.get("attempt") or 0)
        error = str(payload.get("error") or "remote worker failed").strip()
        retryable = payload.get("retryable") is not False
        if not worker_id or attempt < 1:
            raise ValueError("worker_id and positive attempt are required")
        claim = self._claim_for_attempt(job_id, worker_id, attempt)
        runtime_state = self.orchestrator.runtime.fail(
            claim,
            error,
            retryable=retryable,
        )
        if (
            retryable
            and runtime_state.get("retryable") is not False
            and int(runtime_state.get("attempt") or attempt) < int(runtime_state.get("max_attempts") or attempt)
        ):
            with self.orchestrator.runtime._lock:
                runtime_state = self.orchestrator.runtime.store.retry(claim.run_id)
        self.orchestrator.reconcile_runtime()
        if runtime_state.get("status") != "retrying":
            job = self.orchestrator.store.get(job_id)
            if self.orchestrator._on_job_failed:
                self.orchestrator._on_job_failed(job_id, job.get("plan") or {}, error)
            self.orchestrator.store.update(job_id, "failed", error=error)
        return self.orchestrator.get_job(job_id)

    def job(self, job_id: str) -> dict[str, Any]:
        return self.orchestrator.get_job(job_id)


def create_app(
    repo_root: str | Path | None = None,
    *,
    token: str | None = None,
    orchestrator: Any | None = None,
):
    """Build a small FastAPI app suitable for a Tailscale-only controller port."""

    from fastapi import Depends, FastAPI, Header, HTTPException, Request

    if orchestrator is None:
        from scripts.research_data_mcp.bootstrap import create_stack

        orchestrator = create_stack(repo_root=repo_root).orchestrator
    expected = token or os.environ.get(TOKEN_ENV, "")
    control = WorkerControlPlane(orchestrator, token=expected)
    app = FastAPI(title="YZU Worker Control", version="1")

    def authorize(
        authorization: str | None = Header(default=None),
        x_yzu_worker_token: str | None = Header(default=None),
    ) -> None:
        candidate = _bearer_token(authorization, x_yzu_worker_token)
        try:
            control.authorize(candidate)
        except PermissionError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc

    def invoke(method, *args, **kwargs):
        try:
            return method(*args, **kwargs)
        except PermissionError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/health")
    def health():
        return {"status": "ok", "token_required": True}

    @app.post("/v1/workers/join", dependencies=[Depends(authorize)])
    def join(payload: dict[str, Any]):
        return invoke(control.join, payload)

    @app.post("/v1/workers/claim", dependencies=[Depends(authorize)])
    def claim(payload: dict[str, Any]):
        return {"claim": invoke(control.claim, payload)}

    @app.post("/v1/jobs/{job_id}/heartbeat", dependencies=[Depends(authorize)])
    def heartbeat(job_id: str, payload: dict[str, Any]):
        return invoke(control.heartbeat, job_id, payload)

    @app.post("/v1/jobs/{job_id}/usage", dependencies=[Depends(authorize)])
    def usage(job_id: str, payload: dict[str, Any]):
        return invoke(control.usage, job_id, payload)

    @app.put("/v1/jobs/{job_id}/artifacts/{name}", dependencies=[Depends(authorize)])
    async def upload_artifact(
        job_id: str,
        name: str,
        request: Request,
        x_yzu_worker_id: str = Header(),
        x_yzu_attempt: int = Header(),
        x_content_sha256: str | None = Header(default=None),
    ):
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > control.max_artifact_bytes:
            raise HTTPException(status_code=413, detail="artifact exceeds configured byte limit")
        content = await request.body()
        return invoke(
            control.upload_artifact,
            job_id,
            worker_id=x_yzu_worker_id,
            attempt=x_yzu_attempt,
            name=name,
            content=content,
            expected_sha256=x_content_sha256,
        )

    @app.post("/v1/jobs/{job_id}/complete", dependencies=[Depends(authorize)])
    def complete(job_id: str, payload: dict[str, Any]):
        return invoke(control.complete, job_id, payload)

    @app.post("/v1/jobs/{job_id}/fail", dependencies=[Depends(authorize)])
    def fail(job_id: str, payload: dict[str, Any]):
        return invoke(control.fail, job_id, payload)

    @app.get("/v1/jobs/{job_id}", dependencies=[Depends(authorize)])
    def job(job_id: str):
        return invoke(control.job, job_id)

    app.state.worker_control = control
    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the authenticated YZU worker control plane")
    parser.add_argument("--repo-root", default=None)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8780)
    args = parser.parse_args()
    import uvicorn

    uvicorn.run(create_app(args.repo_root), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
