#!/usr/bin/env python3
"""Queue GDrive archive_upload jobs after successful collection jobs."""

from __future__ import annotations

import json
from glob import glob
from pathlib import Path
from typing import Any


def _rel(repo_root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(repo_root))
    except ValueError:
        return str(path)


def resolve_archive_target(repo_root: Path, local_path: str) -> Path | None:
    """Map registry output_hint / local_path (may contain globs) to an on-disk file or directory."""
    pattern = str(local_path or "").strip().replace("YYYY-MM-DD", "*")
    if not pattern:
        return None
    if "*" in pattern:
        matches = [Path(p) for p in glob(str(repo_root / pattern)) if Path(p).exists()]
        if matches:
            first = matches[0]
            return first.parent if first.is_file() else first
        parent = pattern.split("*", 1)[0].rstrip("/")
        candidate = repo_root / parent
        return candidate if candidate.exists() else None
    target = repo_root / pattern
    if target.is_file() or target.is_dir():
        return target
    return None


def remote_suffix_for_job(plan: dict[str, Any], dataset_id: str, *, repo_root: Path | None = None) -> str:
    if repo_root is not None:
        from scripts.research_data_mcp.partition_wiring import archive_remote_suffix

        suffix = archive_remote_suffix(repo_root, plan, dataset_id)
        if suffix:
            return suffix
    job_type = str(plan.get("job_type") or "")
    if job_type == "registered_pipeline":
        pid = str(plan.get("pipeline_id") or dataset_id)
        return f"collection/ops/pipelines/{pid}"
    if job_type in {"collection_queue_task", "collection_queue_batch"}:
        tid = str(plan.get("task_id") or dataset_id)
        return f"collection/ops/collection-queue/{tid}"
    if job_type == "scraper_run":
        return f"collection/ops/scrapes/{dataset_id}"
    return f"collection/acquired/procured/{dataset_id}"


def archive_targets_from_promoted(promoted: list[dict[str, Any]], registry_path: Path) -> list[tuple[str, str]]:
    """Return (local_path_pattern, dataset_id) pairs from promotion results."""
    if not promoted:
        return []
    doc = json.loads(registry_path.read_text(encoding="utf-8"))
    by_id = {str(row.get("dataset_id")): row for row in doc.get("datasets") or []}
    out: list[tuple[str, str]] = []
    for row in promoted:
        did = str(row.get("dataset_id") or "")
        spec = by_id.get(did) or {}
        local_path = str(spec.get("local_path") or "")
        if did and local_path:
            out.append((local_path, did))
    return out


def queue_auto_archives(
    *,
    repo_root: Path,
    jobs: Any,
    job_id: str,
    plan: dict[str, Any],
    promoted: list[dict[str, Any]],
    registry_path: Path,
    storage: dict[str, Any],
    campaign_id: str = "",
) -> list[dict[str, Any]]:
    """Submit archive_upload jobs for completed work when auto_archive_procured is enabled."""
    if not storage.get("auto_archive_procured"):
        return []

    queued: list[dict[str, Any]] = []
    seen: set[str] = set()

    # http_manifest path (materialized procured dir)
    materialized_dir = ""  # filled by caller via result if needed

    targets = archive_targets_from_promoted(promoted, registry_path)
    for local_pattern, dataset_id in targets:
        target = resolve_archive_target(repo_root, local_pattern)
        if not target:
            continue
        rel = _rel(repo_root, target)
        if rel in seen:
            continue
        seen.add(rel)
        suffix = remote_suffix_for_job(plan, dataset_id, repo_root=repo_root)
        archive_plan = jobs.archive_plan(rel, remote_suffix=suffix, verify=True)
        submitted = jobs.submit(
            f"Archive {dataset_id} to GDrive",
            archive_plan,
            {
                "parent_job_id": job_id,
                "campaign_id": campaign_id,
                "dataset_id": dataset_id,
                "_ops_internal": True,
            },
            auto_approve=True,
        )
        queued.append({"local_path": rel, "dataset_id": dataset_id, "remote_suffix": suffix, "archive_job": submitted})

    return queued


def queue_archive_materialized(
    *,
    repo_root: Path,
    jobs: Any,
    job_id: str,
    materialized: dict[str, Any],
    storage: dict[str, Any],
    campaign_id: str = "",
    plan: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Archive procured http_manifest canonical_dir (legacy bootstrap path)."""
    if not storage.get("auto_archive_procured"):
        return None
    canonical = str(materialized.get("canonical_dir") or "").strip()
    if not canonical:
        return None
    target = resolve_archive_target(repo_root, canonical)
    if not target:
        return None
    rel = _rel(repo_root, target)
    dataset_id = str(materialized.get("dataset_id") or job_id)
    plan_ctx = dict(plan or {})
    plan_ctx.setdefault("partition_id", plan_ctx.get("partition_id") or "")
    suffix = remote_suffix_for_job(plan_ctx, dataset_id, repo_root=repo_root)
    if not suffix:
        suffix = f"collection/acquired/procured/{dataset_id}"
    archive_plan = jobs.archive_plan(rel, remote_suffix=suffix, verify=True)
    return jobs.submit(
        f"Archive procured {dataset_id} to GDrive",
        archive_plan,
        {"parent_job_id": job_id, "campaign_id": campaign_id, "_ops_internal": True},
        auto_approve=True,
    )
