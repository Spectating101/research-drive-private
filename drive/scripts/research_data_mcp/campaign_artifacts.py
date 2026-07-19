#!/usr/bin/env python3
"""Campaign delivery — list procured files and resolve safe local download paths."""

from __future__ import annotations

import hashlib
import json
import mimetypes
from pathlib import Path
from typing import Any, Callable

_ALLOWED_PREFIXES = (
    "data_lake/procured/",
    "data_lake/yzu_cluster/acquisitions/",
    "data_lake/yzu_cluster/jobs/",
)


def _artifact_id(rel_path: str) -> str:
    return hashlib.sha256(rel_path.encode()).hexdigest()[:16]


def _safe_rel_path(repo_root: Path, rel_path: str) -> str:
    root = repo_root.resolve()
    target = (root / rel_path).resolve()
    if not str(target).startswith(str(root)):
        raise ValueError("path escapes repo root")
    rel = str(target.relative_to(root)).replace("\\", "/")
    if not any(rel.startswith(prefix) for prefix in _ALLOWED_PREFIXES):
        raise ValueError(f"path not in delivery allowlist: {rel}")
    if not target.is_file():
        raise FileNotFoundError(rel)
    return rel


def _row_from_file(repo_root: Path, rel_path: str, *, source: str, job_id: str = "") -> dict[str, Any]:
    rel = rel_path.replace("\\", "/").lstrip("/")
    path = (repo_root / rel).resolve()
    if not path.is_file():
        return {}
    return {
        "id": _artifact_id(rel),
        "name": path.name,
        "path": rel,
        "bytes": path.stat().st_size,
        "content_type": mimetypes.guess_type(path.name)[0] or "application/octet-stream",
        "source": source,
        "job_id": job_id,
    }


def _files_from_materialized(repo_root: Path, materialized: dict[str, Any], *, job_id: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for entry in materialized.get("files") or []:
        rel = str(entry.get("path") or "")
        if rel.startswith(str(repo_root)):
            rel = str(Path(rel).resolve().relative_to(repo_root.resolve())).replace("\\", "/")
        elif not rel:
            rel = str(entry.get("name") or "")
            canonical = materialized.get("canonical_dir") or materialized.get("staging_dir")
            if canonical and rel:
                rel = f"{canonical}/{rel}".replace("\\", "/")
        row = _row_from_file(repo_root, rel, source="materialized", job_id=job_id)
        if row:
            rows.append(row)
    return rows


def _registry_datasets_for_campaign(repo_root: Path, registry_path: Path, campaign_id: str) -> list[dict[str, Any]]:
    if not registry_path.exists():
        return []
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    out: list[dict[str, Any]] = []
    for row in payload.get("datasets") or []:
        lineage = row.get("lineage") or {}
        if str(lineage.get("campaign_id") or "") != campaign_id:
            continue
        local_path = str(row.get("local_path") or "")
        if not local_path:
            continue
        out.append(
            {
                "dataset_id": row.get("id"),
                "name": row.get("name") or row.get("id"),
                "local_path": local_path,
                "backend": row.get("backend"),
            }
        )
    return out


def list_campaign_artifacts(
    repo_root: Path,
    campaign: dict[str, Any],
    *,
    job_get: Callable[[str], dict[str, Any]],
    registry_path: Path | None = None,
) -> dict[str, Any]:
    """Enumerate downloadable files linked to a procurement campaign."""
    repo_root = repo_root.resolve()
    campaign_id = str(campaign.get("id") or "")
    payload = campaign.get("payload") or {}
    job_ids: list[str] = []
    for key in ("probe_job_ids", "collect_job_ids"):
        job_ids.extend(str(j) for j in (payload.get(key) or []) if j)
    last_job = payload.get("last_collect_job") or {}
    if last_job.get("id"):
        job_ids.append(str(last_job["id"]))

    seen: set[str] = set()
    artifacts: list[dict[str, Any]] = []

    def add(row: dict[str, Any]) -> None:
        rel = row.get("path") or ""
        if not rel or rel in seen:
            return
        seen.add(rel)
        row = dict(row)
        row["download_path"] = f"/library/campaigns/{campaign_id}/download?path={rel}"
        artifacts.append(row)

    for job_id in dict.fromkeys(job_ids):
        try:
            job = job_get(job_id)
        except Exception:
            continue
        materialized = (job.get("result") or {}).get("materialized") or {}
        for row in _files_from_materialized(repo_root, materialized, job_id=job_id):
            add(row)
        for entry in (job.get("result") or {}).get("artifacts") or []:
            rel = str(entry.get("artifact") or "")
            row = _row_from_file(repo_root, rel, source="job_artifact", job_id=job_id)
            if row:
                add(row)

    registry_path = registry_path or (repo_root / "config/research_query_registry.json")
    promoted = _registry_datasets_for_campaign(repo_root, registry_path, campaign_id)
    for entry in promoted:
        local_path = str(entry.get("local_path") or "")
        if "*" in local_path:
            for path in sorted(repo_root.glob(local_path)):
                if path.is_file():
                    rel = str(path.relative_to(repo_root)).replace("\\", "/")
                    row = _row_from_file(repo_root, rel, source="registry", job_id="")
                    if row:
                        row["dataset_id"] = entry.get("dataset_id")
                        add(row)
        else:
            row = _row_from_file(repo_root, local_path, source="registry", job_id="")
            if row:
                row["dataset_id"] = entry.get("dataset_id")
                add(row)

    return {
        "campaign_id": campaign_id,
        "phase": campaign.get("phase"),
        "status": campaign.get("status"),
        "delivery_mode": "local",
        "artifact_count": len(artifacts),
        "artifacts": artifacts,
        "registry_datasets": promoted,
        "note": "Local staging delivery only. GDrive remains cold archive until object-store URLs are wired.",
    }


def resolve_campaign_download(repo_root: Path, campaign_id: str, rel_path: str) -> dict[str, Any]:
    rel = _safe_rel_path(repo_root, rel_path)
    path = (repo_root / rel).resolve()
    return {
        "campaign_id": campaign_id,
        "path": rel,
        "file": path,
        "content_type": mimetypes.guess_type(path.name)[0] or "application/octet-stream",
        "bytes": path.stat().st_size,
    }
