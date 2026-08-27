"""Compile generic Discover acquisition plans into cluster execution contracts.

The model may identify a source and choose a generic acquisition primitive, but it
must not bind a concrete worker.  This module turns that semantic plan into the
bounded contract consumed by the YZU runtime: capabilities, resource reservations,
parallelism hints, retry policy, and lifecycle ownership.

Placement remains runtime authority.  A compiled plan can say what it needs; only
fresh worker/capacity state may decide where it runs.
"""

from __future__ import annotations

import hashlib
import json
import math
from copy import deepcopy
from typing import Any, Mapping

from scripts.yzu_cluster._interop_common import normalize_capabilities


GENERIC_ACQUISITION_TYPES = frozenset({"source_probe", "http_manifest", "scraper_run"})

_JOB_CAPABILITIES: dict[str, tuple[str, ...]] = {
    "source_probe": ("http",),
    "http_manifest": ("http",),
    "scraper_run": ("browser",),
}

# These are intentionally modest hard minima.  Unknown transfer volume is kept as
# an estimate, not converted into a fake disk/network reservation.
_BASELINE_RESOURCES: dict[str, dict[str, float]] = {
    "source_probe": {"cpu_cores": 0.25, "memory_mb": 128.0},
    "http_manifest": {"cpu_cores": 0.5, "memory_mb": 256.0},
    "scraper_run": {"cpu_cores": 1.0, "memory_mb": 1024.0, "disk_mb": 256.0},
}

_DEFAULT_ATTEMPTS = {
    "source_probe": 2,
    "http_manifest": 3,
    "scraper_run": 2,
}

_RESOURCE_KEYS = ("cpu_cores", "memory_mb", "disk_mb", "network_mb", "gpu_count")
_PLACEMENT_KEYS = ("worker_id", "assigned_worker", "runtime_worker", "fixed_worker")


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def _known_transfer_bytes(plan: Mapping[str, Any]) -> int | None:
    """Return only a declared/observed transfer estimate; never invent one."""

    direct = _number(plan.get("estimated_bytes") or plan.get("expected_bytes"))
    if direct is not None and direct > 0:
        return int(direct)

    total = 0.0
    observed = False
    for item in plan.get("items") or []:
        if not isinstance(item, Mapping):
            continue
        value = _number(
            item.get("estimated_bytes")
            or item.get("expected_bytes")
            or item.get("content_length")
            or item.get("bytes")
        )
        if value is None or value <= 0:
            continue
        total += value
        observed = True
    return int(total) if observed else None


def _merge_resource_requirements(job_type: str, plan: Mapping[str, Any]) -> tuple[dict[str, float], dict[str, Any]]:
    explicit = plan.get("resource_requirements") or plan.get("resources") or {}
    explicit = explicit if isinstance(explicit, Mapping) else {}
    hard = {key: 0.0 for key in _RESOURCE_KEYS}

    for key, value in _BASELINE_RESOURCES[job_type].items():
        hard[key] = float(value)
    for key in _RESOURCE_KEYS:
        value = _number(explicit.get(key))
        if value is not None:
            hard[key] = max(hard[key], float(value))

    transfer_bytes = _known_transfer_bytes(plan)
    estimate: dict[str, Any] = {
        "status": "baseline_only",
        "transfer_bytes": transfer_bytes,
        "source": "declared_or_observed" if transfer_bytes is not None else "unmeasured",
    }
    if transfer_bytes is not None:
        transfer_mb = transfer_bytes / (1024 * 1024)
        # Reserve enough local workspace for the payload plus modest manifest/
        # archive overhead.  Network and disk are hard only because the transfer
        # itself supplied a concrete bound.
        hard["network_mb"] = max(hard["network_mb"], math.ceil(transfer_mb * 1.05))
        hard["disk_mb"] = max(hard["disk_mb"], math.ceil(transfer_mb * 1.25 + 64))
        estimate.update({
            "status": "bounded",
            "transfer_mb": round(transfer_mb, 2),
            "workspace_disk_mb": hard["disk_mb"],
            "network_mb": hard["network_mb"],
        })

    # Keep the payload compact and deterministic.
    hard = {key: value for key, value in hard.items() if value > 0}
    return hard, estimate


def _semantic_acceptance(plan: Mapping[str, Any]) -> dict[str, Any]:
    need = str(plan.get("research_need") or "").strip()
    return {
        "research_need": need[:800],
        "gap_closure": "not_proven_by_collection",
        "proof_required": True,
        "note": (
            "Materialisation/archive/query smoke prove a reusable asset, not that it satisfies the research requirement. "
            "Discover must reassess the acquired asset before treating the evidence gap as closed."
        ),
    }


def _stages(job_type: str) -> list[dict[str, str]]:
    if job_type == "source_probe":
        return [
            {
                "id": "probe",
                "authority": "runtime_worker",
                "completion": "bounded source classification result",
            }
        ]
    return [
        {
            "id": "collect",
            "authority": "runtime_worker",
            "completion": "attempt-fenced artifact or scrape output",
        },
        {
            "id": "materialize_validate",
            "authority": "controller",
            "completion": "immutable revision + structural staging validation",
        },
        {
            "id": "archive_verify",
            "authority": "controller",
            "completion": "vault copy/read-back when drive-first policy applies",
        },
        {
            "id": "register_query_smoke",
            "authority": "controller",
            "completion": "registry read-back; query_ready only after successful query smoke",
        },
    ]


def _hash_contract(contract: Mapping[str, Any]) -> str:
    payload = json.dumps(contract, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()[:24]


def compile_procurement_execution_plan(plan: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return a generic acquisition plan enriched for safe cluster execution.

    The compiler is deterministic.  It does not discover sources, choose evidence,
    approve work, or assign a worker.
    """

    if not isinstance(plan, Mapping):
        raise ValueError("plan must be an object")
    out = deepcopy(dict(plan))
    job_type = str(out.get("job_type") or "").strip()
    if job_type not in GENERIC_ACQUISITION_TYPES:
        raise ValueError(
            f"cluster procurement compiler accepts only {sorted(GENERIC_ACQUISITION_TYPES)}; got {job_type!r}"
        )

    for key in _PLACEMENT_KEYS:
        if str(out.get(key) or "").strip():
            raise ValueError(f"crafted procurement cannot bind {key}; cluster runtime owns worker placement")
    if str(out.get("pool") or "").strip():
        raise ValueError("crafted procurement cannot bind pool; express capabilities/resources instead")

    capabilities = normalize_capabilities([
        *_JOB_CAPABILITIES[job_type],
        *(out.get("required_capabilities") or []),
    ])
    resources, estimate = _merge_resource_requirements(job_type, out)

    item_count = len([item for item in (out.get("items") or []) if isinstance(item, Mapping)])
    parallelism = 1
    if job_type == "http_manifest" and item_count > 1:
        # Executor may fan a manifest across the Windows fleet.  This is a bounded
        # concurrency hint, never a worker count promise.
        parallelism = min(item_count, 4)
        out.setdefault("shards", parallelism)
        out.setdefault("per_node_workers", 2)

    out["required_capabilities"] = capabilities
    out["resource_requirements"] = resources
    out.setdefault("max_attempts", _DEFAULT_ATTEMPTS[job_type])
    out.setdefault("retryable", True)

    contract: dict[str, Any] = {
        "version": 1,
        "placement": {
            "authority": "cluster_runtime",
            "worker_bound": False,
            "required_capabilities": capabilities,
            "resource_requirements": resources,
        },
        "parallelism": {
            "mode": "manifest_shards" if job_type == "http_manifest" and item_count > 1 else "single_claim",
            "hint": parallelism,
            "item_count": item_count,
            "binding": "runtime_only",
        },
        "retry": {
            "retryable": bool(out.get("retryable")),
            "max_attempts": int(out.get("max_attempts") or _DEFAULT_ATTEMPTS[job_type]),
            "lease_fenced": True,
        },
        "resource_estimate": estimate,
        "stages": _stages(job_type),
        "evidence_acceptance": _semantic_acceptance(out),
    }
    contract["contract_hash"] = _hash_contract(contract)
    out["cluster_execution"] = contract
    out["planner_revision"] = f"cluster-contract-v1:{contract['contract_hash']}"
    return out
