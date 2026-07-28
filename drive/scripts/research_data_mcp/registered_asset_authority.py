#!/usr/bin/env python3
"""Read-only recovery authority for registered assets missing from the loaded catalog.

The canonical registry remains primary.  This module only exposes a durable
registration receipt when the completed job proves all of the following:

- a concrete dataset and manifest identity;
- archive verification;
- canonical registry read-back; and
- readiness of exactly ``registered`` or ``query_ready``.

It never promotes a merely completed job and never makes a receipt queryable.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from pathlib import Path
from typing import Any

_VERIFIED_READINESS = frozenset({"registered", "query_ready", "instant"})


def _json_object(raw: Any) -> dict[str, Any]:
    if isinstance(raw, Mapping):
        return dict(raw)
    try:
        value = json.loads(str(raw or "{}"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return dict(value) if isinstance(value, Mapping) else {}


def _jobs_db(repo_root: Path) -> Path | None:
    config_path = repo_root / "config/yzu_cluster.json"
    if not config_path.is_file():
        return None
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    jobs_root = str(((config.get("controller") or {}).get("jobs_root") or "")).strip()
    if not jobs_root:
        return None
    path = Path(jobs_root)
    if not path.is_absolute():
        path = repo_root / path
    db = path / "jobs.sqlite3"
    return db.resolve() if db.is_file() else None


def _receipt_from_job(job: Mapping[str, Any]) -> dict[str, Any] | None:
    result = _json_object(job.get("result") or job.get("result_json"))
    evidence = _json_object(result.get("registration_evidence"))
    dataset_id = str(evidence.get("dataset_id") or "").strip()
    registry_id = str(evidence.get("registry_id") or dataset_id).strip()
    manifest_id = str(evidence.get("manifest_id") or result.get("output_manifest_id") or "").strip()
    readiness = str(evidence.get("readiness") or "").strip()
    vault_path = str(evidence.get("vault_path") or "").strip()

    if not dataset_id or not registry_id or not manifest_id or not vault_path:
        return None
    if evidence.get("archive_verified") is not True or evidence.get("registry_readback") is not True:
        return None
    if readiness not in _VERIFIED_READINESS:
        return None

    plan = _json_object(job.get("plan") or job.get("plan_json"))
    request = _json_object(job.get("request") or job.get("request_json"))
    job_id = str(job.get("id") or "").strip()
    source = evidence.get("source") or request.get("source") or plan.get("source") or plan.get("job_type") or "registered_collection"
    if isinstance(source, Mapping):
        source = source.get("name") or source.get("id") or "registered_collection"

    receipt = {
        "dataset_id": dataset_id,
        "registry_id": registry_id,
        "manifest_id": manifest_id,
        "job_id": job_id,
        "name": evidence.get("title") or job.get("title") or dataset_id,
        "description": "Verified registered asset recovered from its durable registration receipt.",
        "source": str(source),
        "grain": evidence.get("grain") or plan.get("grain") or "",
        "coverage": evidence.get("coverage") or plan.get("coverage") or "",
        "analysis_readiness": readiness,
        "backend": "registered_asset_receipt",
        "access_shape": "registered_archive",
        "canonical_remote": vault_path,
        "vault_path": vault_path,
        "archive_verified": True,
        "registry_readback": True,
        "lifecycle": readiness,
        "legacy_status": str(job.get("status") or ""),
        "created_at": job.get("created_at"),
        "updated_at": job.get("updated_at") or job.get("created_at"),
        "recommended_use": "Inspect provenance and prepare a query adapter; registration alone is not query readiness.",
        "limitations": "The canonical registry row is not present in the currently loaded catalog. Query execution remains disabled until catalog reconciliation and a query-ready smoke pass.",
        "authority": {
            "source": "registration_receipt",
            "state": "verified",
            "archive_verified": True,
            "registry_readback": True,
            "catalog_state": "reconciliation_required",
        },
        "catalog_reconciliation": {
            "state": "receipt_only",
            "registry_row_loaded": False,
            "query_allowed": False,
        },
        "registration_receipt": {
            "dataset_id": dataset_id,
            "registry_id": registry_id,
            "manifest_id": manifest_id,
            "job_id": job_id,
            "archive_verified": True,
            "registry_readback": True,
            "readiness": readiness,
            "vault_path": vault_path,
        },
    }
    return receipt


def list_verified_registration_receipts(repo_root: str | Path, *, limit: int = 500) -> list[dict[str, Any]]:
    """Return latest verified receipt per dataset without mutating the job store."""

    root = Path(repo_root).resolve()
    db_path = _jobs_db(root)
    if db_path is None:
        return []
    rows: list[dict[str, Any]] = []
    try:
        connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
        connection.row_factory = sqlite3.Row
        try:
            fetched = connection.execute(
                """SELECT id, created_at, updated_at, status, title,
                          request_json, plan_json, result_json
                   FROM jobs
                   ORDER BY updated_at DESC
                   LIMIT ?""",
                (max(1, min(int(limit or 500), 5000)),),
            ).fetchall()
        finally:
            connection.close()
    except (OSError, sqlite3.Error):
        return []

    seen: set[str] = set()
    for row in fetched:
        receipt = _receipt_from_job(dict(row))
        if receipt is None:
            continue
        dataset_id = str(receipt["dataset_id"])
        if dataset_id in seen:
            continue
        seen.add(dataset_id)
        rows.append(receipt)
    return rows


def get_verified_registration_receipt(repo_root: str | Path, dataset_id: str) -> dict[str, Any] | None:
    wanted = str(dataset_id or "").strip()
    if not wanted:
        return None
    return next(
        (row for row in list_verified_registration_receipts(repo_root) if row.get("dataset_id") == wanted),
        None,
    )
