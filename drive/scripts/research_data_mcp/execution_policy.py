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

_INTERNAL_OPS_CAPABILITY = object()
_INTERNAL_SYNTHESIS_CAPABILITY = object()
_INTERNAL_CAPABILITY_KEYS = frozenset(
    {"_ops_internal", "_execution_internal_capability", "_synthesis_execution_capability"}
)


def internal_ops_request(request: dict[str, Any] | None = None) -> dict[str, Any]:
    """Mark a request created by trusted local scheduler/controller code."""
    out = dict(request or {})
    out["_ops_internal"] = True
    out["_execution_internal_capability"] = _INTERNAL_OPS_CAPABILITY
    return out


def internal_synthesis_execution_request(request: dict[str, Any] | None = None) -> dict[str, Any]:
    """Mark the bounded gateway path without granting auto-approval.

    This protects HTTP/MCP client payloads. In-process Python modules share the
    same trusted control-plane boundary and are intentionally not treated as a
    sandbox.
    """
    out = dict(request or {})
    out["_synthesis_execution_capability"] = _INTERNAL_SYNTHESIS_CAPABILITY
    return out


def sanitize_execution_request(request: dict[str, Any] | None = None) -> dict[str, Any]:
    """Remove non-serializable privilege capabilities before job persistence."""
    return {key: value for key, value in dict(request or {}).items() if key not in _INTERNAL_CAPABILITY_KEYS}


def enforce_execution_submit(
    plan: dict[str, Any] | None,
    request: dict[str, Any] | None = None,
    *,
    auto_approve: bool = False,
) -> tuple[dict[str, Any], bool]:
    """Return ``(sanitized_plan, auto_approve)`` or raise ``ValueError``."""
    request = dict(request or {})
    plan = dict(plan) if isinstance(plan, dict) else {}
    internal_ops = request.pop("_execution_internal_capability", None) is _INTERNAL_OPS_CAPABILITY
    synthesis_execution = request.pop("_synthesis_execution_capability", None) is _INTERNAL_SYNTHESIS_CAPABILITY
    request.pop("_ops_internal", None)
    # Never trust client/model privilege bits.
    plan.pop("ops_privileged", None)
    request.pop("ops_privileged", None)
    if internal_ops:
        plan["ops_privileged"] = True
    job_type = str(plan.get("job_type") or "").strip()
    if job_type == "synthesis_execute" and not synthesis_execution:
        raise ValueError("execution policy: synthesis_execute requires the dedicated synthesis capability")
    if synthesis_execution:
        if job_type != "synthesis_execute":
            raise ValueError("execution policy: synthesis capability only permits synthesis_execute")
        plan = enforce_submit_doctrine(plan, scope="ops")
        scope = "synthesis"
        auto_approve = False
    else:
        scope = "ops" if plan.get("ops_privileged") else "faculty"
        plan = enforce_submit_doctrine(plan, scope=scope)
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
