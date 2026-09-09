#!/usr/bin/env python3
"""Public job identity fields for Discover lifecycle linkage (D0b).

Honesty rules:
- Expose candidate_key / connector_id only when stored or derivable from
  structured ids (dataset_id, DOI, URL) — never from title matching.
- registered_dataset_id is set only after RegistryPromoter writes a mapping
  onto the job result (registry_promotion[*].dataset_id).
- output_manifest_id is exposed only from explicit result, materialisation, or
  registration evidence. Jobs without recorded manifest proof remain null.
"""

from __future__ import annotations

from typing import Any

from scripts.research_data_mcp.candidate_key import candidate_key


def _trim(value: Any) -> str:
    return str(value or "").strip()


def _structured_candidate_key(request: dict[str, Any], plan: dict[str, Any]) -> str:
    """Derive key from structured request/plan fields only (no title fallback)."""
    row = {
        "candidate_key": request.get("candidate_key") or plan.get("candidate_key"),
        "dataset_id": request.get("dataset_id") or plan.get("dataset_id"),
        "doi": request.get("doi") or plan.get("doi") or plan.get("datacite_doi"),
        "url": request.get("url")
        or request.get("source_url")
        or plan.get("url")
        or plan.get("source_url"),
        "resolved_url": request.get("resolved_url") or plan.get("resolved_url"),
        "external_id": request.get("external_id") or plan.get("external_id"),
        "source_id": request.get("source_id") or plan.get("source_id"),
        "provider": request.get("provider") or plan.get("provider"),
        "source": request.get("source_identity") or request.get("source") or plan.get("source"),
        "kind": request.get("kind") or plan.get("kind"),
        "handle": request.get("handle") or plan.get("handle"),
        "hf_id": request.get("hf_id") or plan.get("hf_dataset_id"),
        "id": request.get("hf_id") or plan.get("hf_dataset_id"),
    }
    # Prefer non-title tiers: if only title would match, return empty.
    key = candidate_key({k: v for k, v in row.items() if v})
    if key.startswith("title:"):
        return ""
    return key


def registered_dataset_id_from_result(result: dict[str, Any] | None) -> str | None:
    """Return registry dataset_id only when promotion established it."""
    if not isinstance(result, dict):
        return None
    promo = result.get("registry_promotion")
    if isinstance(promo, list):
        for entry in promo:
            if isinstance(entry, dict):
                did = _trim(entry.get("dataset_id"))
                if did:
                    return did
    elif isinstance(promo, dict):
        did = _trim(promo.get("dataset_id"))
        if did:
            return did
        datasets = promo.get("datasets")
        if isinstance(datasets, list):
            for entry in datasets:
                if isinstance(entry, dict):
                    did = _trim(entry.get("dataset_id"))
                    if did:
                        return did
    return None


def output_manifest_id_from_result(result: dict[str, Any] | None) -> str | None:
    """Return an explicit manifest id from persisted execution/registration proof."""
    if not isinstance(result, dict):
        return None
    for key in ("output_manifest_id", "manifest_id"):
        mid = _trim(result.get(key))
        if mid:
            return mid
    mat = result.get("materialized")
    if isinstance(mat, dict):
        for key in ("output_manifest_id", "manifest_id"):
            mid = _trim(mat.get(key))
            if mid:
                return mid
    evidence = result.get("registration_evidence")
    if isinstance(evidence, dict):
        for key in ("output_manifest_id", "manifest_id"):
            mid = _trim(evidence.get(key))
            if mid:
                return mid
    return None


def enrich_job_identity(job: dict[str, Any] | None) -> dict[str, Any] | None:
    """Attach top-level identity fields for API consumers. Mutates a shallow copy."""
    if not isinstance(job, dict):
        return job
    out = dict(job)
    request = out.get("request") if isinstance(out.get("request"), dict) else {}
    plan = out.get("plan") if isinstance(out.get("plan"), dict) else {}
    result = out.get("result") if isinstance(out.get("result"), dict) else {}

    ck = _trim(out.get("candidate_key")) or _structured_candidate_key(request, plan) or None
    connector = (
        _trim(out.get("connector_id"))
        or _trim(request.get("connector_id"))
        or _trim(plan.get("connector_id"))
        or None
    )

    out["candidate_key"] = ck
    out["connector_id"] = connector
    out["registered_dataset_id"] = registered_dataset_id_from_result(result)
    out["output_manifest_id"] = output_manifest_id_from_result(result)
    return out


def enrich_jobs_payload(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return payload
    out = dict(payload)
    jobs = out.get("jobs")
    if isinstance(jobs, list):
        out["jobs"] = [enrich_job_identity(j) if isinstance(j, dict) else j for j in jobs]
    return out
