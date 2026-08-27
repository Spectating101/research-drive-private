#!/usr/bin/env python3
"""Canonical job operations — one path for submit/approve/list."""

from __future__ import annotations

from typing import Any

from scripts.research_data_mcp.job_identity import enrich_job_identity, enrich_jobs_payload
from scripts.research_data_mcp.desk_ownership import can_access_owner, owner_id_for_create, require_owner
from scripts.yzu_cluster.orchestrator import YzuOrchestrator


class JobService:
    def __init__(self, orchestrator: YzuOrchestrator, *, campaign_runner: Any | None = None) -> None:
        self.orchestrator = orchestrator
        self.campaign_runner = campaign_runner

    def set_campaign_runner(self, runner: Any) -> None:
        self.campaign_runner = runner

    def validate(self, plan: dict[str, Any]) -> dict[str, Any]:
        return self.orchestrator.validate_plan(plan)

    @staticmethod
    def _discover_submit_key(request: dict[str, Any] | None) -> str:
        """Return the server-owned durable job id for one Discover intent.

        A Discover intent is a one-collection decision record. Route changes,
        browser tabs and direct retries therefore must not be able to manufacture
        a second job. The underlying orchestrator already gives an idempotency key
        SQLite uniqueness and replay semantics; this layer only chooses the key.
        """
        body = request if isinstance(request, dict) else {}
        if str(body.get("source") or "").strip() != "discover_intent":
            return ""
        intent_id = str(body.get("discover_intent_id") or "").strip()
        if not intent_id:
            return ""
        return f"discover-submit:{intent_id}"

    def _discover_replay(
        self,
        discover_key: str,
        request: dict[str, Any],
        plan: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Return the durable winning Discover job when it already exists.

        This is intentionally intent-scoped rather than payload-scoped. Once one
        tab wins the durable insert, another tab for the same intent must recover
        that winner even if its route/title changed concurrently. The first job is
        immutable execution authority; retries may not mutate it in place.
        """
        if not discover_key:
            return None
        try:
            existing = self.orchestrator.get_job(discover_key)
        except KeyError:
            return None
        if not existing:
            return None
        existing_request = existing.get("request") or {}
        require_owner(existing_request.get("owner_id"), discover_key)
        if (
            str(existing_request.get("source") or "") != "discover_intent"
            or str(existing_request.get("discover_intent_id") or "")
            != str(request.get("discover_intent_id") or "")
        ):
            raise ValueError("Discover idempotency key is already bound to another submission")
        return {
            "job": enrich_job_identity(existing),
            "plan": existing.get("plan") or plan,
            "idempotent_replay": True,
        }

    def submit(
        self,
        title: str,
        plan: dict[str, Any],
        request: dict[str, Any] | None = None,
        *,
        auto_approve: bool = False,
    ) -> dict[str, Any]:
        from scripts.research_data_mcp.execution_policy import enforce_execution_submit

        # Keep original request for orchestrator (single source of truth for _ops_internal).
        request = dict(request or {})
        owner_id = owner_id_for_create()
        if owner_id:
            request.setdefault("owner_id", owner_id)

        discover_key = self._discover_submit_key(request)
        if discover_key:
            # Client-supplied idempotency cannot choose Discover authority. The
            # intent id is durable and server-owned, and one intent may create at
            # most one collection job irrespective of route/tab/retry timing.
            request["idempotency_key"] = discover_key
            replay = self._discover_replay(discover_key, request, plan)
            if replay is not None:
                return replay

        plan, auto_approve = enforce_execution_submit(plan, dict(request), auto_approve=auto_approve)
        validated = self.validate(plan)
        if not validated.get("launchable", True):
            return {
                "job": None,
                "plan": validated,
                "error": validated.get("validation_error", "plan not launchable"),
            }
        # YzuOrchestrator.submit uses request.idempotency_key as the durable job
        # id and resolves the cross-process SQLite uniqueness race atomically.
        try:
            job = self.orchestrator.submit(title, validated, request, auto_approve=auto_approve)
        except ValueError as exc:
            # Two simultaneous tabs can both miss the pre-read. If their routes
            # differ, the orchestrator correctly rejects the losing payload as a
            # same-key/different-request collision. For Discover, the intent is
            # the authority boundary: recover the already-created winner instead
            # of surfacing a retry error or allowing a second job identity.
            if discover_key and "idempotency key already exists with a different request" in str(exc):
                replay = self._discover_replay(discover_key, request, validated)
                if replay is not None:
                    return replay
            raise
        return {"job": enrich_job_identity(job), "plan": validated}

    def approve(self, job_id: str) -> dict[str, Any]:
        return enrich_job_identity(self.orchestrator.approve(job_id)) or {}

    def cancel(self, job_id: str) -> dict[str, Any]:
        return enrich_job_identity(self.orchestrator.cancel(job_id)) or {}

    def get(self, job_id: str) -> dict[str, Any]:
        job = self.orchestrator.get_job(job_id)
        if not job:
            return {}
        require_owner((job.get("request") or {}).get("owner_id"), job_id)
        return enrich_job_identity(job) or {}

    def list(self, limit: int = 30, status: str = "") -> dict[str, Any]:
        requested = min(max(limit, 1), 200)
        # Filter after a bounded superset so another member's newer jobs cannot
        # crowd the caller's own History out of a small page.
        jobs = self.orchestrator.list_jobs(200, status=status)
        jobs = [
            job for job in jobs
            if can_access_owner((job.get("request") or {}).get("owner_id"))
        ][:requested]
        payload = {"jobs": jobs}
        return enrich_jobs_payload(payload) or payload

    def run_schedule(self, schedule_id: str, *, dry_run: bool = False) -> dict[str, Any]:
        return self.orchestrator.run_schedule(schedule_id, dry_run=dry_run)

    def tick(self) -> dict[str, Any] | None:
        # Cadence first — must not wait behind a long-running job execution.
        gateway = getattr(self, "gateway", None) or getattr(self.campaign_runner, "gateway", None)
        if gateway is not None and hasattr(gateway, "discover_refresh_tick"):
            try:
                gateway.discover_refresh_tick(limit=5, auto_approve_safe=False)
            except Exception:  # noqa: BLE001
                pass
        job = self.orchestrator.worker_tick()
        if self.campaign_runner:
            self.campaign_runner.tick()
        return job


    def archive_plan(
        self,
        local_path: str,
        *,
        remote_suffix: str = "",
        verify: bool = True,
    ) -> dict[str, Any]:
        plan: dict[str, Any] = {
            "job_type": "archive_upload",
            "local_path": local_path,
            "launchable": True,
            "verify": verify,
        }
        if remote_suffix:
            plan["remote_suffix"] = remote_suffix
        return plan
