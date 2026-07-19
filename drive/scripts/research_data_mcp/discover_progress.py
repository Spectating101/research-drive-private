"""Discover subscription / run progress contract for Faculty FE.

Stable fields only — job lifecycle, not byte meters. FE should render
``progress.phase`` + ``progress.label`` and optionally timestamps.
"""

from __future__ import annotations

from typing import Any


def build_subscription_progress(
    sub: dict[str, Any],
    *,
    job: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Normalize a subscription (+ optional latest job) into FE progress."""
    status = str(sub.get("status") or "").lower()
    mode = str(sub.get("execution_mode") or "non_executing")
    last_run = str(sub.get("last_run_status") or "").lower()
    job_status = str((job or {}).get("status") or "").lower() if job else ""
    effective = job_status or last_run

    if status == "stopped":
        phase, label = "stopped", "Stopped — no further automatic runs"
    elif status == "paused":
        phase, label = "paused", "Paused — next run cleared"
    elif effective in {"queued", "approved"}:
        phase, label = "queued", "Refresh job queued"
    elif effective == "running":
        phase, label = "running", "Refresh job running"
    elif effective == "completed":
        phase, label = "completed", "Last refresh completed"
    elif effective == "failed":
        phase, label = "failed", "Last refresh failed"
    elif effective == "cancelled":
        phase, label = "cancelled", "Last refresh cancelled"
    elif mode == "scheduled" and sub.get("next_run_at"):
        phase, label = "scheduled", f"Next run {sub.get('next_run_at')}"
    elif mode == "scheduled":
        phase, label = "scheduled", "Scheduled — waiting for next run"
    else:
        phase, label = "manual", "Manual cadence — run collect when needed"

    return {
        "phase": phase,
        "label": label,
        "execution_mode": mode,
        "auto_refresh": bool(sub.get("auto_refresh")),
        "subscription_status": status or None,
        "next_run_at": sub.get("next_run_at") or None,
        "last_run_at": sub.get("last_run_at") or None,
        "last_job_id": sub.get("last_job_id") or (job or {}).get("id") or None,
        "last_run_status": sub.get("last_run_status") or (job_status or None),
        "last_run_plan": sub.get("last_run_plan") or None,
        "last_run_error": sub.get("last_run_error") or None,
        "cadence": sub.get("cadence") or None,
        "schedule_cron": ((sub.get("schedule_spec") or {}) if isinstance(sub.get("schedule_spec"), dict) else {}).get("cron")
        or None,
        "timezone": ((sub.get("schedule_spec") or {}) if isinstance(sub.get("schedule_spec"), dict) else {}).get("timezone")
        or None,
    }


def attach_subscription_progress(
    sub: dict[str, Any],
    *,
    job: dict[str, Any] | None = None,
) -> dict[str, Any]:
    out = dict(sub)
    out["progress"] = build_subscription_progress(out, job=job)
    return out
