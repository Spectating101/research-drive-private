"""Authenticated control plane for bounded remote YZU workers.

Remote workers may advertise capacity, claim compatible jobs, heartbeat, report
usage, upload attempt-fenced artifacts, and submit terminal results. The
controller remains authoritative for materialisation, archive verification,
registry promotion, registration, and legacy compatibility state.
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
DEFAULT_REMOTE_JOB_TYPES = ("http_manifest",)
DEFAULT_FIXTURE_ID_PREFIXES = (
    "probe-no-promotion-",
    "missing-manifest-",
    "archive-before-promote-",
)


def _bearer_token(authorization: str | None, explicit: str | None = None) -> str:
    if explicit:
        return explicit.strip()
    value = str(authorization or "").strip()
    return value[7:].strip() if value.lower().startswith("bearer ") else value


def build_live_identity(orchestrator: Any, *, dataset_id: str | None = None, job_id: str | None = None) -> dict[str, Any]:
    """Return the sanitized cross-surface identity for a registered asset or job."""

    dataset_id = str(dataset_id or "").strip() or None
    job_id = str(job_id or "").strip() or None
    if not dataset_id and not job_id:
        raise ValueError("dataset_id or job_id is required")

    job: dict[str, Any] | None = None
    if job_id:
        job = orchestrator.get_job(job_id)
    elif dataset_id:
        for candidate in orchestrator.store.list(limit=500):
            result = candidate.get("result") if isinstance(candidate.get("result"), Mapping) else {}
            evidence = result.get("registration_evidence") if isinstance(result.get("registration_evidence"), Mapping) else {}
            outputs = list((candidate.get("lifecycle") or {}).get("outputs") or result.get("outputs") or [])
            materialized = result.get("materialized") if isinstance(result.get("materialized"), Mapping) else {}
            matches = {
                str(evidence.get("dataset_id") or ""),
                str(materialized.get("dataset_id") or ""),
                str(result.get("dataset_id") or ""),
                *[str(item) for item in outputs],
            }
            if dataset_id in matches:
                job = candidate
                break
        if job is None:
            raise KeyError(dataset_id)

    assert job is not None
    resolved_job_id = str(job.get("id") or job_id or "")
    result = job.get("result") if isinstance(job.get("result"), Mapping) else {}
    evidence = result.get("registration_evidence") if isinstance(result.get("registration_evidence"), Mapping) else {}
    materialized = result.get("materialized") if isinstance(result.get("materialized"), Mapping) else {}
    snap = orchestrator.runtime.snapshot(resolved_job_id)
    worker = snap.get("assigned_worker") if isinstance(snap.get("assigned_worker"), Mapping) else {}
    vault = str(evidence.get("vault_path") or "")
    vault_suffix = vault.split("Sharpe-Renaissance-data/", 1)[-1] if "Sharpe-Renaissance-data/" in vault else vault
    resolved_dataset = str(
        dataset_id
        or evidence.get("dataset_id")
        or materialized.get("dataset_id")
        or result.get("dataset_id")
        or (snap.get("outputs") or [None])[0]
        or ""
    )
    readiness = str(evidence.get("readiness") or snap.get("status") or job.get("status") or "unknown")
    return {
        "dataset_id": resolved_dataset,
        "registry_id": str(evidence.get("registry_id") or snap.get("registration_id") or resolved_dataset),
        "manifest_id": str(
            evidence.get("manifest_id")
            or materialized.get("manifest_id")
            or snap.get("manifest_id")
            or ""
        ),
        "job_id": resolved_job_id,
        "run_id": str(snap.get("run_id") or ""),
        "attempt": int(snap.get("attempt") or 0),
        "worker_id": str(worker.get("id") or snap.get("worker_id") or ""),
        "readiness": readiness,
        "archive_verified": bool(
            evidence.get("archive_verified") if "archive_verified" in evidence else snap.get("drive_verified")
        ),
        "registry_readback": bool(evidence.get("registry_readback", False)),
        "lifecycle": str(snap.get("status") or readiness),
        "legacy_status": str(job.get("status") or ""),
        "vault_suffix": vault_suffix,
        "synthesis_expectation": {
            "badge": "Query ready"
            if readiness == "query_ready"
            else ("Registered" if readiness == "registered" else readiness),
            "not_badge": "Query ready" if readiness == "registered" else None,
            "openable_in_library": readiness in {"registered", "query_ready"},
        },
    }


class WorkerControlPlane:
    def __init__(self, orchestrator: Any, *, token: str, max_artifact_bytes: int | None = None) -> None:
        token = str(token or "").strip()
        if not token:
            raise RuntimeError(f"{TOKEN_ENV} is required for the worker control plane")
        self.orchestrator = orchestrator
        self.token = token
        configured = max_artifact_bytes or int(os.environ.get(MAX_ARTIFACT_ENV, 512 * 1024 * 1024))
        self.max_artifact_bytes = max(1, int(configured))
        remote = ((getattr(orchestrator, "cfg", None) or {}).get("operations") or {}).get("remote_worker") or {}
        types = remote.get("allowed_job_types")
        if types is None:
            types = DEFAULT_REMOTE_JOB_TYPES
        self.allowed_job_types = tuple(str(item).strip() for item in types if str(item).strip())
        prefixes = remote.get("deny_job_id_prefixes")
        if prefixes is None:
            prefixes = DEFAULT_FIXTURE_ID_PREFIXES
        self.deny_job_id_prefixes = tuple(str(item) for item in prefixes if str(item))

    def queue_contamination_report(self) -> dict[str, Any]:
        """Count queued jobs that production remote workers will refuse to claim."""

        queued = list(self.orchestrator.store.list(limit=500, status="queued"))
        denied_type: list[str] = []
        denied_prefix: list[str] = []
        for job in queued:
            job_id = str(job.get("id") or "")
            job_type = str((job.get("plan") or {}).get("job_type") or "")
            if self.allowed_job_types and job_type and job_type not in self.allowed_job_types:
                denied_type.append(job_id)
            elif any(job_id.startswith(prefix) for prefix in self.deny_job_id_prefixes):
                denied_prefix.append(job_id)
        return {
            "queued": len(queued),
            "denied_job_type_count": len(denied_type),
            "denied_fixture_prefix_count": len(denied_prefix),
            "allowed_job_types": list(self.allowed_job_types),
            "deny_job_id_prefixes": list(self.deny_job_id_prefixes),
        }

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
        assigned = snapshot.get("assigned_worker")
        if isinstance(assigned, Mapping):
            assigned_worker = str(assigned.get("id") or assigned.get("worker_id") or "")
        else:
            assigned_worker = str(assigned or snapshot.get("worker_id") or "")
        state = str(snapshot.get("status") or snapshot.get("stage") or "")
        if current_attempt != int(attempt):
            raise PermissionError(f"stale execution attempt: expected {attempt}, current {current_attempt}")
        if assigned_worker != worker_id:
            raise PermissionError("worker does not own this execution attempt")
        if state not in ACTIVE_ATTEMPT_STAGES:
            raise ValueError(f"runtime job is {state}, not writable by a worker")

        job = self.orchestrator.store.get(job_id)
        plan = job.get("plan") or {}
        requirements = snapshot.get("resource_requirements") or snapshot.get("requirements") or {}
        return Claim(
            run_id=str(snapshot["run_id"]),
            job_id=job_id,
            job_type=str(snapshot.get("type") or snapshot.get("job_type") or plan.get("job_type") or "legacy_job"),
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
            allowed_job_types=self.allowed_job_types,
            deny_job_id_prefixes=self.deny_job_id_prefixes,
        )
        return self._claim_payload(claim, self.orchestrator.store.get(claim.job_id)) if claim else None

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

    def prepare_artifact_upload(
        self,
        job_id: str,
        *,
        worker_id: str,
        attempt: int,
        name: str,
    ) -> tuple[Path, Path, str]:
        self._claim_for_attempt(job_id, worker_id, attempt)
        safe_name = Path(str(name or "")).name
        if not safe_name or safe_name != name or safe_name in {".", ".."}:
            raise ValueError("artifact name must be a plain filename")
        destination = self.orchestrator.jobs_root / job_id / "remote_artifacts" / safe_name
        try:
            destination.relative_to(self.orchestrator.repo_root)
        except ValueError as exc:
            raise ValueError("artifact destination is outside the repository") from exc
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(f".{safe_name}.{worker_id}.{attempt}.part")
        return destination, temporary, safe_name

    def commit_artifact_upload(
        self,
        job_id: str,
        *,
        worker_id: str,
        attempt: int,
        name: str,
        temporary: Path,
        size: int,
        digest: str,
        expected_sha256: str | None = None,
    ) -> dict[str, Any]:
        destination, expected_temporary, safe_name = self.prepare_artifact_upload(
            job_id,
            worker_id=worker_id,
            attempt=attempt,
            name=name,
        )
        if temporary.resolve() != expected_temporary.resolve():
            raise ValueError("artifact temporary path does not match the execution attempt")
        if size > self.max_artifact_bytes:
            raise ValueError(f"artifact exceeds {self.max_artifact_bytes} byte limit")
        expected = str(expected_sha256 or "").strip().lower()
        if expected and not hmac.compare_digest(expected, digest):
            raise ValueError("artifact sha256 does not match request proof")
        if not temporary.is_file() or temporary.stat().st_size != size:
            raise ValueError("artifact upload is incomplete")
        os.replace(temporary, destination)
        relative = destination.relative_to(self.orchestrator.repo_root)
        return {
            "artifact": str(relative),
            "name": safe_name,
            "bytes": size,
            "sha256": digest,
            "worker_id": worker_id,
            "attempt": attempt,
        }

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
        _, temporary, _ = self.prepare_artifact_upload(
            job_id,
            worker_id=worker_id,
            attempt=attempt,
            name=name,
        )
        if len(content) > self.max_artifact_bytes:
            raise ValueError(f"artifact exceeds {self.max_artifact_bytes} byte limit")
        digest = hashlib.sha256(content).hexdigest()
        try:
            with temporary.open("wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            return self.commit_artifact_upload(
                job_id,
                worker_id=worker_id,
                attempt=attempt,
                name=name,
                temporary=temporary,
                size=len(content),
                digest=digest,
                expected_sha256=expected_sha256,
            )
        finally:
            temporary.unlink(missing_ok=True)

    def complete(self, job_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        worker_id = str(payload.get("worker_id") or "").strip()
        attempt = int(payload.get("attempt") or 0)
        if not worker_id or attempt < 1:
            raise ValueError("worker_id and positive attempt are required")
        claim = self._claim_for_attempt(job_id, worker_id, attempt)
        job = self.orchestrator.store.get(job_id)
        plan = job.get("plan") or {}
        result = dict(payload.get("result") if isinstance(payload.get("result"), Mapping) else {})

        # Materialisation, GDrive copy/check, promotion, and registry read-back may
        # take longer than the worker's initial lease. The controller renews the
        # same fenced attempt until it is ready to record the terminal state.
        renewal = self.orchestrator.runtime.lease_renewer(claim).start()
        try:
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
        finally:
            renewal.stop()
        renewal.raise_if_lost()

        runtime_state = self.orchestrator.runtime.complete(claim, result)
        self.orchestrator.store.update(job_id, "completed", result=result)
        if self.orchestrator._on_job_post_completed:
            try:
                self.orchestrator._on_job_post_completed(job_id, plan, result, runtime_state)
            except Exception as exc:  # noqa: BLE001
                self.orchestrator.store.event(job_id, "warning", f"Post-registration follow-up failed: {exc}")
        return self.orchestrator.get_job(job_id)

    def fail(self, job_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        worker_id = str(payload.get("worker_id") or "").strip()
        attempt = int(payload.get("attempt") or 0)
        error = str(payload.get("error") or "remote worker failed").strip()
        retryable = payload.get("retryable") is not False
        if not worker_id or attempt < 1:
            raise ValueError("worker_id and positive attempt are required")
        claim = self._claim_for_attempt(job_id, worker_id, attempt)
        runtime_state = self.orchestrator.runtime.fail(claim, error, retryable=retryable)
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

    def live_identity(
        self,
        *,
        dataset_id: str | None = None,
        job_id: str | None = None,
    ) -> dict[str, Any]:
        """Return the sanitized cross-surface identity for a registered asset or job."""

        return build_live_identity(self.orchestrator, dataset_id=dataset_id, job_id=job_id)


def create_app(
    repo_root: str | Path | None = None,
    *,
    token: str | None = None,
    orchestrator: Any | None = None,
):
    """Build a Tailscale/private-interface FastAPI worker-control service."""
    from fastapi import Depends, FastAPI, Header, HTTPException, Request as FastAPIRequest

    # Annotations are postponed in this module. Expose the lazily imported
    # request type in module globals so FastAPI injects the ASGI Request object
    # instead of interpreting `request` as a required body field.
    globals()["Request"] = FastAPIRequest

    if orchestrator is None:
        from scripts.research_data_mcp.bootstrap import create_stack

        orchestrator = create_stack(repo_root=repo_root).orchestrator
    control = WorkerControlPlane(orchestrator, token=token or os.environ.get(TOKEN_ENV, ""))
    app = FastAPI(title="YZU Worker Control", version="1")

    def authorize(
        authorization: str | None = Header(default=None),
        x_yzu_worker_token: str | None = Header(default=None),
    ) -> None:
        try:
            control.authorize(_bearer_token(authorization, x_yzu_worker_token))
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
        report = control.queue_contamination_report()
        return {
            "status": "ok",
            "token_required": True,
            "queue": {
                "queued": report["queued"],
                "denied_job_type_count": report["denied_job_type_count"],
                "denied_fixture_prefix_count": report["denied_fixture_prefix_count"],
            },
        }

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
        raw_length = request.headers.get("content-length")
        if raw_length:
            try:
                if int(raw_length) > control.max_artifact_bytes:
                    raise HTTPException(status_code=413, detail="artifact exceeds configured byte limit")
            except ValueError as exc:
                raise HTTPException(status_code=400, detail="invalid content-length") from exc
        _, temporary, _ = invoke(
            control.prepare_artifact_upload,
            job_id,
            worker_id=x_yzu_worker_id,
            attempt=x_yzu_attempt,
            name=name,
        )
        total = 0
        digest_builder = hashlib.sha256()
        try:
            with temporary.open("wb") as handle:
                async for chunk in request.stream():
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > control.max_artifact_bytes:
                        raise HTTPException(status_code=413, detail="artifact exceeds configured byte limit")
                    digest_builder.update(chunk)
                    handle.write(chunk)
                handle.flush()
                os.fsync(handle.fileno())
            return invoke(
                control.commit_artifact_upload,
                job_id,
                worker_id=x_yzu_worker_id,
                attempt=x_yzu_attempt,
                name=name,
                temporary=temporary,
                size=total,
                digest=digest_builder.hexdigest(),
                expected_sha256=x_content_sha256,
            )
        finally:
            temporary.unlink(missing_ok=True)

    @app.post("/v1/jobs/{job_id}/complete", dependencies=[Depends(authorize)])
    def complete(job_id: str, payload: dict[str, Any]):
        return invoke(control.complete, job_id, payload)

    @app.post("/v1/jobs/{job_id}/fail", dependencies=[Depends(authorize)])
    def fail(job_id: str, payload: dict[str, Any]):
        return invoke(control.fail, job_id, payload)

    @app.get("/v1/jobs/{job_id}", dependencies=[Depends(authorize)])
    def job(job_id: str):
        return invoke(control.job, job_id)

    @app.get("/v1/identity", dependencies=[Depends(authorize)])
    def identity(dataset_id: str | None = None, job_id: str | None = None):
        return invoke(control.live_identity, dataset_id=dataset_id, job_id=job_id)

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
