#!/usr/bin/env python3
"""YZU Cluster orchestrator — unified job queue + execution across pools."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from .executor import ALLOWED_JOB_TYPES, YzuExecutor
from .jobs import YzuJobStore
from .queue_catalog import list_tasks
from .scheduler import YzuScheduler
from sharpe_kernel.paths import repo_root_from_file


class YzuOrchestrator:
    def __init__(
        self,
        repo_root: Path | None = None,
        engine: Any | None = None,
        *,
        on_job_completed: Any | None = None,
    ):
        self.repo_root = (repo_root or repo_root_from_file(__file__)).resolve()
        self.engine = engine
        self._on_job_completed = on_job_completed
        self._on_job_failed: Any | None = None
        self.cfg = json.loads((self.repo_root / "config/yzu_cluster.json").read_text(encoding="utf-8"))
        jobs_root = self.repo_root / self.cfg["controller"]["jobs_root"]
        jobs_root.mkdir(parents=True, exist_ok=True)
        self.jobs_root = jobs_root
        self.store = YzuJobStore(jobs_root / "jobs.sqlite3")
        self.executor = YzuExecutor(self.repo_root, self.cfg, jobs_root, event_cb=self.store.event)
        self.scheduler = YzuScheduler(self.repo_root, self.cfg)
        self._lock = threading.Lock()
        self._running_job: str | None = None

    def set_on_job_completed(self, callback: Any | None) -> None:
        self._on_job_completed = callback

    def set_on_job_failed(self, callback: Any | None) -> None:
        self._on_job_failed = callback

    def allowed_job_types(self) -> list[str]:
        agent = self.cfg.get("agent", {})
        allowed = set(agent.get("allowed_job_types", [])) | set(agent.get("future_job_types", []))
        return sorted(allowed & ALLOWED_JOB_TYPES)

    def submit(self, title: str, plan: dict[str, Any], request: dict | None = None, *, auto_approve: bool = False) -> dict:
        plan = self.validate_plan(plan)
        status = "queued" if auto_approve and plan.get("launchable", True) else "pending_approval"
        job = self.store.create(title, request or {}, plan, status=status)
        if status == "queued":
            self.store.event(job["id"], "info", "Auto-approved and queued")
        return job

    def approve(self, job_id: str) -> dict:
        job = self.store.get(job_id)
        if job["status"] != "pending_approval":
            raise ValueError(f"job is {job['status']}, not pending_approval")
        self.store.update(job_id, "queued")
        self.store.event(job_id, "info", "Approved — waiting for worker")
        return self.store.get(job_id)

    def cancel(self, job_id: str) -> dict:
        job = self.store.get(job_id)
        if job["status"] not in {"pending_approval", "queued"}:
            raise ValueError("only pending or queued jobs can be cancelled")
        self.store.event(job_id, "warning", "Job cancelled by user")
        return self.store.update(job_id, "cancelled")

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
        return self.scheduler.schedules()

    def run_schedule(self, schedule_id: str) -> dict:
        for item in self.cfg.get("schedules", []):
            if item.get("id") == schedule_id:
                plan = dict(item.get("plan") or {})
                plan.setdefault("launchable", True)
                return self.submit(plan.get("title") or schedule_id, plan, {"schedule_id": schedule_id}, auto_approve=True)
        raise KeyError(schedule_id)

    def scheduler_tick(self) -> dict[str, Any] | None:
        return self.scheduler.tick(self)

    def execute_job(self, job_id: str) -> dict:
        with self._lock:
            if self._running_job and self._running_job != job_id:
                raise RuntimeError(f"worker busy with job {self._running_job}")
            self._running_job = job_id
        try:
            job = self.store.get(job_id)
            if job["status"] == "cancelled":
                return job
            self.store.update(job_id, "running")
            self.store.event(job_id, "info", "Execution started")
            result = self.executor.execute(job_id, job["plan"])
            self.store.event(job_id, "info", "Execution completed")
            if self._on_job_completed:
                promo = self._on_job_completed(job_id, job["plan"], result)
                if promo:
                    result = dict(result or {})
                    result["registry_promotion"] = promo
            return self.store.update(job_id, "completed", result=result)
        except Exception as exc:
            self.store.event(job_id, "error", str(exc))
            if self._on_job_failed:
                self._on_job_failed(job_id, job.get("plan") or {}, str(exc))
            return self.store.update(job_id, "failed", error=str(exc))
        finally:
            with self._lock:
                if self._running_job == job_id:
                    self._running_job = None

    def worker_tick(self) -> dict | None:
        if self._running_job:
            return None
        self.scheduler_tick()
        job_id = self.store.next_queued()
        if not job_id:
            return None
        return self.execute_job(job_id)

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
        return self.store.status_counts()

    def components(self) -> dict[str, Any]:
        return {
            "controller": self.cfg["controller"]["hostname"],
            "storage": self.cfg.get("storage", {}),
            "worker_pools": list(self.cfg.get("worker_pools", {}).keys()),
            "pipelines": list(self.executor.pipelines().keys()),
            "allowed_job_types": self.allowed_job_types(),
            "jobs_db": str(self.store.path.relative_to(self.repo_root)),
            "schedules": self.schedules(),
            "queue_tasks_runnable": len(self.queue_tasks(runnable_only=True)),
        }
