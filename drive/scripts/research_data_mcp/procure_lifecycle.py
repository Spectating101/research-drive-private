#!/usr/bin/env python3
"""Deterministic procure phases — independent of Composer prose.

Phases are derived from existing job + promotion fields so the desk can
answer "where is this collect?" without an LLM.
"""

from __future__ import annotations

from typing import Any

PHASES = (
    "crafted",
    "pending_approval",
    "queued",
    "running",
    "materialized",
    "smoked",
    "registered",
    "query_ready",
    "stopped",
    "failed",
    "blocked",
)


def procure_phase_from_job(job: dict[str, Any] | None) -> str:
    """Map a YZU/desk job record to a procure lifecycle phase."""
    job = job if isinstance(job, dict) else {}
    status = str(job.get("status") or "").strip().lower().replace("-", "_")
    if status in {"cancelled", "canceled"}:
        return "stopped"
    if status in {"failed", "error"}:
        return "failed"
    if status in {"blocked", "headroom_blocked"}:
        return "blocked"
    if status == "pending_approval":
        return "pending_approval"
    if status in {"queued", "approved"}:
        return "queued"
    if status in {"running", "executing", "collecting"}:
        return "running"
    if status != "completed":
        if status in {"crafted", "draft"}:
            return "crafted"
        return status or "crafted"

    result = job.get("result") if isinstance(job.get("result"), dict) else {}
    materialized = result.get("materialized") if isinstance(result.get("materialized"), dict) else {}
    promotion = result.get("promotion") if isinstance(result.get("promotion"), dict) else {}
    smoke = (
        (promotion.get("query_smoke") if isinstance(promotion.get("query_smoke"), dict) else None)
        or (materialized.get("query_smoke") if isinstance(materialized.get("query_smoke"), dict) else None)
        or (result.get("query_smoke") if isinstance(result.get("query_smoke"), dict) else None)
    )
    readiness = str(
        promotion.get("analysis_readiness")
        or (promotion.get("stored") or {}).get("analysis_readiness")
        or result.get("analysis_readiness")
        or ""
    ).strip()
    if smoke is not None:
        return "query_ready" if smoke.get("ok") else "registered"
    if readiness == "query_ready":
        return "query_ready"
    if materialized or result.get("canonical_dir") or result.get("revision_id"):
        return "materialized"
    return "registered"


def procure_phase_report(job: dict[str, Any] | None) -> dict[str, Any]:
    phase = procure_phase_from_job(job)
    try:
        idx = PHASES.index(phase)
    except ValueError:
        idx = -1
    return {
        "phase": phase,
        "phase_index": idx,
        "phases": list(PHASES),
        "job_id": str((job or {}).get("id") or ""),
        "job_status": str((job or {}).get("status") or ""),
        "composer_required": False,
        "note": "Procure lifecycle is job-derived — Composer is optional narrator only.",
    }
