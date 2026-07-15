"""Tick Discover refresh subscriptions that are due.

Fires a Discover-linked collection job via resolve_discover_collect_plan, then
arms the next next_run_at. Safe plans may auto-approve; others stay pending.
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime
from typing import Any

_TICK_LOCK = threading.Lock()



def reconcile_discover_refresh_jobs(gateway: Any, *, limit: int = 40) -> dict[str, Any]:
    """Sync subscription last_run_status from terminal job outcomes."""
    store = gateway._discover_refresh_store()
    updated: list[dict[str, Any]] = []
    for sub in store.list(limit=limit):
        jid = str(sub.get("last_job_id") or "").strip()
        if not jid:
            continue
        status = str(sub.get("last_run_status") or "")
        if status in {"completed", "failed", "cancelled"}:
            continue
        try:
            job = gateway.jobs.get(jid)
        except Exception:  # noqa: BLE001
            continue
        jstatus = str((job or {}).get("status") or "")
        if jstatus not in {"completed", "failed", "cancelled"}:
            continue
        err = ""
        if jstatus == "failed":
            res = job.get("result") if isinstance(job.get("result"), dict) else {}
            err = str(job.get("error") or res.get("error") or res.get("message") or jstatus)[:400]
        row = store.mark_run_outcome(str(sub["id"]), job_id=jid, run_status=jstatus, run_error=err)
        updated.append({"subscription_id": row["id"], "last_run_status": jstatus, "job_id": jid})
    return {"reconciled": updated, "count": len(updated)}


def tick_discover_refresh(
    gateway: Any,
    *,
    limit: int = 10,
    force_subscription_id: str = "",
    force: bool = False,
    auto_approve_safe: bool = True,
) -> dict[str, Any]:
    if not _TICK_LOCK.acquire(blocking=False):
        return {"ok": True, "checked": 0, "fired": [], "skipped": [{"reason": "tick_in_progress"}], "errors": [], "busy": True}
    try:
        return _tick_discover_refresh_locked(
            gateway, limit=limit, force_subscription_id=force_subscription_id, force=force, auto_approve_safe=auto_approve_safe,
        )
    finally:
        _TICK_LOCK.release()


def _tick_discover_refresh_locked(
    gateway: Any,
    *,
    limit: int = 10,
    force_subscription_id: str = "",
    force: bool = False,
    auto_approve_safe: bool = True,
) -> dict[str, Any]:
    store = gateway._discover_refresh_store()
    reconcile = reconcile_discover_refresh_jobs(gateway, limit=40)
    force_id = str(force_subscription_id or "").strip()
    fired: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    rearmed = 0

    # Migrate legacy active cron rows that were stored as non_executing pre-runner.
    for row in store.list(limit=200, status="active"):
        if not row.get("enabled"):
            continue
        cron = str((row.get("schedule_spec") or {}).get("cron") or "").strip()
        if not cron or row.get("cadence") == "manual":
            continue
        if row.get("execution_mode") == "scheduled" and row.get("next_run_at"):
            continue
        try:
            store.rearm(str(row["id"]))
            rearmed += 1
        except Exception:  # noqa: BLE001
            pass

    if force_id:
        try:
            candidates = [store.get(force_id)]
        except KeyError:
            return {
                "ok": False,
                "error": f"subscription not found: {force_id}",
                "fired": [],
                "skipped": [],
                "errors": [],
            }
    elif force:
        candidates = [
            row
            for row in store.list(limit=min(max(limit, 1), 50), status="active")
            if row.get("enabled") and row.get("execution_mode") == "scheduled"
        ][:limit]
    else:
        candidates = store.list_due(limit=limit)

    from scripts.research_data_mcp.discover_collect_plan import resolve_discover_collect_plan
    from scripts.research_data_mcp.procurement_auto_approve import should_auto_approve_plan

    now = datetime.now(UTC)
    for sub in candidates:
        sid = str(sub.get("id") or "")
        if sub.get("status") != "active" or not sub.get("enabled"):
            skipped.append({"subscription_id": sid, "reason": "not_active"})
            continue
        if not force and not force_id:
            next_at = str(sub.get("next_run_at") or "")
            if not next_at:
                skipped.append({"subscription_id": sid, "reason": "no_next_run"})
                continue

        try:
            plan = dict(
                resolve_discover_collect_plan(
                    gateway.procurement,
                    gateway.repo_root,
                    connector_id=str(sub.get("connector_id") or ""),
                    source_id=str(sub.get("source_id") or ""),
                    limit=25,
                    title=f"Discover refresh {sub.get('source_id') or sub.get('connector_id') or sid[:8]}",
                    url="",
                    candidate_key=str(sub.get("candidate_key") or ""),
                )
            )
        except Exception as exc:  # noqa: BLE001
            errors.append({"subscription_id": sid, "error": f"plan: {exc}"})
            continue

        plan["discover_subscription_id"] = sid
        plan["refresh_cadence"] = sub.get("cadence") or ""
        request = {
            "source": "discover_refresh",
            "discover_subscription_id": sid,
            "source_id": sub.get("source_id") or "",
            "connector_id": sub.get("connector_id") or "",
            "candidate_key": sub.get("candidate_key") or "",
            "schedule_spec": sub.get("schedule_spec") or {},
        }
        approve = False
        if auto_approve_safe:
            try:
                approve = bool(
                    should_auto_approve_plan(plan, gateway.repo_root, orchestrator=gateway.orchestrator)
                )
            except Exception:  # noqa: BLE001
                approve = False

        submitted = gateway.jobs.submit(
            plan.get("title") or f"Discover refresh {sid[:8]}",
            plan,
            request,
            auto_approve=approve,
        )
        job = submitted.get("job") if isinstance(submitted, dict) else None
        if not isinstance(job, dict) or not job.get("id"):
            errors.append(
                {
                    "subscription_id": sid,
                    "error": submitted.get("error") if isinstance(submitted, dict) else "submit failed",
                    "plan": plan.get("job_type") or plan.get("collect_resolution"),
                }
            )
            continue

        jid = str(job.get("id"))
        updated = store.mark_run(
            sid,
            job_id=jid,
            fired_at=now,
            run_status=str(job.get("status") or "submitted"),
            run_plan=str(plan.get("job_type") or plan.get("collect_resolution") or ""),
        )
        fired.append(
            {
                "subscription_id": sid,
                "job_id": jid,
                "job_status": job.get("status"),
                "auto_approved": approve,
                "next_run_at": updated.get("next_run_at"),
                "last_run_at": updated.get("last_run_at"),
                "plan": plan.get("job_type") or plan.get("collect_resolution"),
            }
        )

    return {
        "ok": not errors or bool(fired),
        "checked": len(candidates),
        "fired": fired,
        "skipped": skipped,
        "errors": errors,
        "rearmed": rearmed,
        "reconciled": reconcile.get("count", 0),
        "forced": bool(force or force_id),
        "ticked_at": now.replace(microsecond=0).isoformat(),
    }
