#!/usr/bin/env python3
"""YZU Cluster orchestrator — unified job queue + execution across pools."""

from __future__ import annotations

import json
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any

from .executor import ALLOWED_JOB_TYPES, YzuExecutor
from .jobs import YzuJobStore
from .queue_catalog import list_tasks
from .runtime_adapter import ClusterRuntimeAdapter
from .scheduler import YzuScheduler
from sharpe_kernel.paths import repo_root_from_file


class YzuOrchestrator:
    def __init__(
        self,
        repo_root: Path | None = None,
        engine: Any | None = None,
        *,
        on_job_completed: Any | None = None,
        on_job_post_completed: Any | None = None,
    ):
        self.repo_root = (repo_root or repo_root_from_file(__file__)).resolve()
        self.engine = engine
        self._on_job_completed = on_job_completed
        self._on_job_post_completed = on_job_post_completed
        self._on_job_failed: Any | None = None
        self.cfg = json.loads((self.repo_root / "config/yzu_cluster.json").read_text(encoding="utf-8"))
        jobs_root = self.repo_root / self.cfg["controller"]["jobs_root"]
        jobs_root.mkdir(parents=True, exist_ok=True)
        self.jobs_root = jobs_root
        self.store = YzuJobStore(jobs_root / "jobs.sqlite3")
        self.runtime = ClusterRuntimeAdapter(self.store.path, self.cfg)
        self.executor = YzuExecutor(self.repo_root, self.cfg, jobs_root, event_cb=self.store.event)
        self.scheduler = YzuScheduler(self.repo_root, self.cfg)
        self._lock = threading.Lock()
        self._running_job: str | None = None

    def set_on_job_completed(self, callback: Any | None) -> None:
        self._on_job_completed = callback

    def set_on_job_post_completed(self, callback: Any | None) -> None:
        self._on_job_post_completed = callback

    def set_on_job_failed(self, callback: Any | None) -> None:
        self._on_job_failed = callback

    def allowed_job_types(self) -> list[str]:
        agent = self.cfg.get("agent", {})
        allowed = set(agent.get("allowed_job_types", [])) | set(agent.get("future_job_types", []))
        return sorted(allowed & ALLOWED_JOB_TYPES)

    @staticmethod
    def _canonical(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    @staticmethod
    def _idempotency_job_id(request: dict[str, Any], plan: dict[str, Any]) -> str | None:
        raw = request.get("job_id") or request.get("idempotency_key") or plan.get("job_id")
        if raw in (None, ""):
            return None
        job_id = str(raw).strip()
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,119}", job_id):
            raise ValueError("idempotency key must use letters, digits, ., _, :, or -")
        return job_id

    def _same_submission(self, job: dict[str, Any], *, title: str, request: dict[str, Any], plan: dict[str, Any]) -> bool:
        return (
            job.get("title") == title
            and self._canonical(job.get("request") or {}) == self._canonical(request)
            and self._canonical(job.get("plan") or {}) == self._canonical(plan)
        )

    def project_job(self, job: dict[str, Any]) -> dict[str, Any]:
        return self.runtime.project(job)

    def get_job(self, job_id: str) -> dict[str, Any]:
        self.reconcile_runtime()
        return self.project_job(self.store.get(job_id))

    def list_jobs(self, limit: int = 30, status: str = "") -> list[dict[str, Any]]:
        self.reconcile_runtime()
        return [self.project_job(job) for job in self.store.list(limit=limit, status=status)]

    def submit(self, title: str, plan: dict[str, Any], request: dict | None = None, *, auto_approve: bool = False) -> dict:
        plan = self.validate_plan(plan)
        request = dict(request or {})
        status = "queued" if auto_approve and plan.get("launchable", True) else "pending_approval"
        idempotency_key = self._idempotency_job_id(request, plan)
        if idempotency_key:
            try:
                existing = self.store.get(idempotency_key)
            except KeyError:
                existing = None
            if existing is not None:
                if not self._same_submission(existing, title=title, request=request, plan=plan):
                    raise ValueError("idempotency key already exists with a different request")
                return self.project_job(existing)
        try:
            job = self.store.create(title, request, plan, status=status, job_id=idempotency_key)
        except sqlite3.IntegrityError:
            if not idempotency_key:
                raise
            existing = self.store.get(idempotency_key)
            if not self._same_submission(existing, title=title, request=request, plan=plan):
                raise ValueError("idempotency key already exists with a different request") from None
            return self.project_job(existing)
        self.runtime.ensure(job)
        if status == "queued":
            self.store.event(job["id"], "info", "Auto-approved and queued")
        return self.get_job(job["id"])

    def approve(self, job_id: str) -> dict:
        job = self.store.get(job_id)
        if job["status"] != "pending_approval":
            raise ValueError(f"job is {job['status']}, not pending_approval")
        plan = self.validate_plan(dict(job.get("plan") or {}))
        if plan.get("launchable") is False:
            detail = str(plan.get("validation_error") or "plan is not launchable").strip()
            raise ValueError(f"cannot approve non-launchable plan: {detail}")
        self.store.set_plan(job_id, plan)
        job = self.store.get(job_id)
        self.runtime.ensure(job)
        self.runtime.approve(job_id)
        self.store.update(job_id, "queued")
        self.store.event(job_id, "info", "Approved — waiting for worker")
        return self.get_job(job_id)

    def cancel(self, job_id: str) -> dict:
        job = self.store.get(job_id)
        if job["status"] not in {"pending_approval", "queued", "running"}:
            raise ValueError("only pending, queued, or running jobs can be cancelled")
        self.runtime.ensure(job)
        self.runtime.cancel(job_id)
        self.store.event(job_id, "warning", "Job cancelled by user")
        self.store.update(job_id, "cancelled")
        return self.get_job(job_id)

    def validate_plan(self, plan: dict[str, Any]) -> dict[str, Any]:
        if not plan:
            return plan
        job_type = plan.get("job_type")
        if job_type and job_type not in self.allowed_job_types():
            plan["launchable"] = False
            plan["validation_error"] = "job type is not allowed"
            return plan
        if job_type and job_type not in ALLOWED_JOB_TYPES:
            plan["launchable"] = False
            plan["validation_error"] = "job type is not allowed"
            return plan
        if job_type == "http_manifest":
            from scripts.research_data_mcp.domain_packs import load_domain_packs
            from scripts.yzu_cluster.acquisitions import enrich_http_manifest_plan
            from scripts.cluster_agent.network_policy import validate_public_http_url

            plan = enrich_http_manifest_plan(
                dict(plan),
                self.executor.procurement,
                domain_packs=load_domain_packs(self.repo_root),
            )
            if not plan.get("items"):
                plan["launchable"] = False
                plan["validation_error"] = "http_manifest requires a URL or downloadable items"
            else:
                # Fail closed on Optiplex before queue/Windows dispatch (SSRF gate).
                for idx, item in enumerate(plan.get("items") or []):
                    if not isinstance(item, dict):
                        continue
                    url = str(item.get("url") or "").strip()
                    if not url:
                        continue
                    evidence = validate_public_http_url(url)
                    item["network_evidence"] = evidence
        if job_type == "registered_pipeline":
            if plan.get("pipeline_id") not in self.executor.pipelines():
                plan["launchable"] = False
                plan["validation_error"] = "pipeline is not registered"
        elif job_type == "collection_queue_task":
            if not plan.get("task_id"):
                plan["launchable"] = False
                plan["validation_error"] = "task_id is required"
        elif job_type == "harvest_shard":
            if not plan.get("shard"):
                plan["launchable"] = False
                plan["validation_error"] = "shard is required"
        elif job_type == "archive_upload":
            if not plan.get("local_path"):
                plan["launchable"] = False
                plan["validation_error"] = "local_path is required"
        elif job_type == "collection_hydrate":
            if not plan.get("remote_path") or not plan.get("local_path"):
                plan["launchable"] = False
                plan["validation_error"] = "remote_path and local_path are required"
        elif job_type == "scraper_run":
            if not plan.get("script_key") and not plan.get("script"):
                plan["launchable"] = False
                plan["validation_error"] = "script_key or script is required"
            elif str(plan.get("script_key") or "") == "generic_url_scrape":
                if not str(plan.get("url") or "").startswith("http"):
                    plan["launchable"] = False
                    plan["validation_error"] = "url is required for generic_url_scrape"
        elif job_type == "bigquery_query":
            if not plan.get("sql") and not plan.get("sql_file"):
                plan["launchable"] = False
                plan["validation_error"] = "sql or sql_file is required"
            elif plan.get("execute") and str(plan.get("confirm") or "") != "EXECUTE_READ_ONLY":
                plan["launchable"] = False
                plan["validation_error"] = "execute requires confirm=EXECUTE_READ_ONLY"
        elif job_type == "synthesis_execute":
            from scripts.research_data_mcp.synthesis_executor import validate_execution_spec
            try:
                plan["execution_spec"] = validate_execution_spec(plan.get("execution_spec") or {})
            except ValueError as exc:
                plan["launchable"] = False
                plan["validation_error"] = str(exc)
        plan["requires_approval"] = True
        return plan

    def queue_tasks(self, *, runnable_only: bool = True) -> list[dict[str, Any]]:
        return list_tasks(self.repo_root, runnable_only=runnable_only)

    def schedules(self) -> list[dict[str, Any]]:
        def current_status(job_id: str) -> str | None:
            try:
                job = self.get_job(job_id)
            except (KeyError, FileNotFoundError):
                return None
            lifecycle = job.get("lifecycle") if isinstance(job, dict) else None
            execution = job.get("execution") if isinstance(job, dict) else None
            if isinstance(lifecycle, dict) and lifecycle.get("stage"):
                return str(lifecycle["stage"])
            if isinstance(execution, dict) and execution.get("stage"):
                return str(execution["stage"])
            status = job.get("status") if isinstance(job, dict) else None
            return str(status) if status else None

        return self.scheduler.schedules(status_lookup=current_status)

    def run_schedule(self, schedule_id: str, *, dry_run: bool = False) -> dict:
        return self.scheduler.emit(self, schedule_id, dry_run=dry_run, force=True)

    def scheduler_tick(self) -> dict[str, Any] | None:
        return self.scheduler.tick(self)

    def execute_job(self, job_id: str, *, claim: Any | None = None) -> dict:
        with self._lock:
            if self._running_job and self._running_job != job_id:
                raise RuntimeError(f"worker busy with job {self._running_job}")
            self._running_job = job_id
        job: dict[str, Any] = {}
        try:
            job = self.store.get(job_id)
            if job["status"] == "cancelled":
                return self.project_job(job)
            self.runtime.ensure(job)
            if claim is None:
                claim = self.runtime.claim_job(job_id)
            if claim is None:
                # A configured remote pool is not a live worker. Keep this job
                # queued until a fresh worker advertises the required capability.
                self.store.event(job_id, "info", "Waiting for a fresh compatible runtime worker")
                return self.get_job(job_id)
            if claim.job_id != job_id:
                raise RuntimeError("runtime claim does not match the requested legacy job")
            self.runtime.start(claim)
            self.store.update(job_id, "running")
            self.store.event(job_id, "info", f"Execution started (attempt {claim.attempt} on {claim.worker_id})")
            renewal = self.runtime.lease_renewer(claim).start()
            try:
                result = self.executor.execute(job_id, job["plan"])
                renewal.raise_if_lost()
                self.store.event(job_id, "info", "Execution completed")
                if self._on_job_completed:
                    promo = self._on_job_completed(job_id, job["plan"], result)
                    if promo:
                        result = dict(result or {})
                        result["registry_promotion"] = promo
                # Archive verification, promotion, and registry read-back are
                # part of the owned attempt. Keep renewing until authoritative
                # completion proof is ready to be recorded.
                renewal.raise_if_lost()
            finally:
                renewal.stop()
            renewal.raise_if_lost()
            runtime_state = self.runtime.complete(claim, result)
            self.store.update(job_id, "completed", result=result)
            if self._on_job_post_completed:
                try:
                    self._on_job_post_completed(job_id, job["plan"], result, runtime_state)
                except Exception as post_exc:  # noqa: BLE001
                    # Registration is already proven. Follow-up indexing or
                    # campaign work must be independently retryable, never turn
                    # a registered research asset into a failed execution.
                    self.store.event(job_id, "warning", f"Post-registration follow-up failed: {post_exc}")
            return self.get_job(job_id)
        except Exception as exc:
            self.store.event(job_id, "error", str(exc))
            runtime_state = None
            if claim is not None:
                try:
                    runtime_state = self.runtime.fail(
                        claim,
                        str(exc),
                        retryable=job.get("plan", {}).get("retryable") is not False,
                    )
                except Exception as runtime_exc:  # noqa: BLE001
                    self.store.event(job_id, "error", f"runtime failure recording failed: {runtime_exc}")
                    try:
                        runtime_state = self.runtime.snapshot(job_id)
                    except KeyError:
                        runtime_state = None
            if isinstance(runtime_state, dict) and runtime_state.get("status") == "retrying":
                self.reconcile_runtime()
                return self.get_job(job_id)
            if self._on_job_failed:
                self._on_job_failed(job_id, job.get("plan") or {}, str(exc))
            self.store.update(job_id, "failed", error=str(exc))
            return self.get_job(job_id)
        finally:
            with self._lock:
                if self._running_job == job_id:
                    self._running_job = None

    def worker_tick(self) -> dict | None:
        if self._running_job:
            return None
        self.scheduler_tick()
        self.runtime.reap_expired()
        self.reconcile_runtime()
        for job in self.store.list(limit=200, status="queued"):
            self.runtime.ensure(job)
        # The controller is the disaster-recovery worker for HTTP procurement.
        # Once a fresh Windows HTTP worker is joined, leave only HTTP runs for
        # that pool instead of letting an approval-triggered local tick steal
        # them. Other controller-owned work may still run normally.
        allowed_job_types = None
        if self._windows_http_worker_available():
            allowed_job_types = [
                str((job.get("plan") or {}).get("job_type") or "legacy_job")
                for job in self.store.list(limit=200, status="queued")
                if str((job.get("plan") or {}).get("job_type") or "legacy_job") != "http_manifest"
            ]
            if not allowed_job_types:
                return None
        claim = self.runtime.claim_next(reap_expired=False, allowed_job_types=allowed_job_types)
        if not claim:
            return None
        return self.execute_job(claim.job_id, claim=claim)

    def _windows_http_worker_available(self) -> bool:
        """Return whether a fresh Windows worker can own an HTTP run."""
        try:
            workers = self.runtime.store.resources_rollup().get("workers") or []
        except Exception:
            return False
        for worker in workers:
            if str(worker.get("pool") or "") != "windows_lab":
                continue
            if str(worker.get("status") or "") not in {"online", "ready", "idle"}:
                continue
            freshness = worker.get("freshness") or {}
            if freshness.get("state") != "fresh":
                continue
            capabilities = set(worker.get("capabilities") or [])
            if "http" in capabilities:
                return True
        return False

    def run_worker(self, poll_seconds: float = 2.0, once: bool = False) -> None:
        import time

        while True:
            self.worker_tick()
            if once:
                return
            time.sleep(poll_seconds)

    def stats(self) -> dict[str, Any]:
        """Job counters for /health — SQL totals + actionable recent windows.

        Prefer ``actionable`` / ``failed_recent`` over lifetime ``failed``/
        ``cancelled`` when triaging live debt.
        """
        runtime = getattr(self, "runtime", None)
        if runtime is not None:
            runtime.reap_expired()
            self.reconcile_runtime()
        return self.store.status_counts()

    def reconcile_runtime(self) -> None:
        """Project authoritative runtime recovery states onto legacy jobs."""

        runtime_adapter = getattr(self, "runtime", None)
        if runtime_adapter is None:
            return

        legacy_status = {
            "pending_approval": "pending_approval",
            "queued": "queued",
            "retrying": "queued",
            "assigned": "queued",
            "running": "running",
            "validating": "running",
            "archiving": "running",
            "registering": "running",
            "completed": "completed",
            "registered": "completed",
            "blocked": "cancelled",
            "failed": "failed",
        }
        for job in self.store.list(limit=500):
            # Ops-noise quarantine is intentional desk hygiene — do not resurrect
            # cancelled canary/spam failures from stale runtime snapshots.
            if (
                str(job.get("status") or "") == "cancelled"
                and "quarantined_ops_noise" in str(job.get("error") or "")
            ):
                continue
            try:
                runtime = runtime_adapter.snapshot(str(job["id"]))
            except KeyError:
                continue
            projected = legacy_status.get(str(runtime.get("status") or ""))
            if projected and job.get("status") != projected:
                reconciled = self.store.update(
                    str(job["id"]),
                    projected,
                    result=job.get("result") or {},
                    error=str(runtime.get("error") or ""),
                    expected_status=str(job.get("status") or ""),
                )
                # Another process may have committed the terminal transition
                # after this snapshot was read. In that case the CAS update
                # affects no row and must not emit a misleading event.
                if reconciled.get("status") == projected:
                    self.store.event(str(job["id"]), "info", f"Runtime state reconciled: {runtime.get('status')}")

    def runtime_health(self) -> dict[str, Any]:
        return self.runtime.health()

    def components(self) -> dict[str, Any]:
        return {
            "controller": self.cfg["controller"]["hostname"],
            "storage": self.cfg.get("storage", {}),
            "worker_pools": list(self.cfg.get("worker_pools", {}).keys()),
            "pipelines": list(self.executor.pipelines().keys()),
            "allowed_job_types": self.allowed_job_types(),
            "jobs_db": str(self.store.path.relative_to(self.repo_root)),
            "runtime": self.runtime_health(),
            "schedules": self.schedules(),
            "queue_tasks_runnable": len(self.queue_tasks(runnable_only=True)),
        }
