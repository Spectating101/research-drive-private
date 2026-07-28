#!/usr/bin/env python3
"""Lowest-level execution submit policy — path-independent.

Every caller that reaches ``YzuOrchestrator.submit`` must pass this gate.
Faculty/Composer cannot escalate privilege or silent-auto-approve acquires.
"""

from __future__ import annotations

from typing import Any

from scripts.research_data_mcp.craft_collect import (
    GENERIC_JOB_TYPES,
    OPS_JOB_TYPES,
    enforce_submit_doctrine,
    is_forbidden_product_id,
)


def enforce_execution_submit(
    plan: dict[str, Any] | None,
    request: dict[str, Any] | None = None,
    *,
    auto_approve: bool = False,
) -> tuple[dict[str, Any], bool]:
    """Return ``(sanitized_plan, auto_approve)`` or raise ``ValueError``."""
    request = dict(request or {})
    plan = dict(plan) if isinstance(plan, dict) else {}
    internal_ops = bool(request.pop("_ops_internal", False))
    # Never trust client/model privilege bits.
    plan.pop("ops_privileged", None)
    request.pop("ops_privileged", None)
    if internal_ops:
        plan["ops_privileged"] = True
    scope = "ops" if plan.get("ops_privileged") else "faculty"
    plan = enforce_submit_doctrine(plan, scope=scope)

    job_type = str(plan.get("job_type") or "").strip()
    if scope == "faculty":
        # Probes may auto-run (cheap, no land); acquires never silent-auto.
        if job_type != "source_probe":
            auto_approve = False
        if job_type not in GENERIC_JOB_TYPES:
            raise ValueError(
                f"execution policy: faculty may only submit {sorted(GENERIC_JOB_TYPES)}; got {job_type!r}"
            )
    elif job_type and job_type not in GENERIC_JOB_TYPES and job_type not in OPS_JOB_TYPES:
        raise ValueError(f"execution policy: unknown job_type={job_type!r}")

    for key in ("pipeline_id", "script_key", "queue_task_id", "source_task_id", "task_id", "job_type"):
        raw = str(plan.get(key) or "").strip()
        if raw and is_forbidden_product_id(raw):
            raise ValueError(f"execution policy refuses named vendor id in {key}={raw!r}")

    plan["execution_policy"] = {
        "scope": scope,
        "auto_approve_allowed": bool(auto_approve),
        "internal_ops": internal_ops,
    }
    return plan, bool(auto_approve)
