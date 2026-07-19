#!/usr/bin/env python3
"""GDrive-first storage: collect/scrape completes only after partition archive + verify."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from scripts.research_data_mcp.storage_tiers import canonical_drive_root, load_storage_tiers


def is_drive_first(repo_root: Path) -> bool:
    cfg = load_storage_tiers(repo_root)
    rules = cfg.get("rules") or {}
    if rules.get("drive_first"):
        return True
    yzu = repo_root / "config/yzu_cluster.json"
    if yzu.is_file():
        storage = json.loads(yzu.read_text(encoding="utf-8")).get("storage") or {}
        return bool(storage.get("drive_first"))
    return False


def compact_local_after_archive(repo_root: Path) -> bool:
    cfg = load_storage_tiers(repo_root)
    rules = cfg.get("rules") or {}
    yzu = repo_root / "config/yzu_cluster.json"
    if yzu.is_file():
        storage = json.loads(yzu.read_text(encoding="utf-8")).get("storage") or {}
        if storage.get("compact_local_after_archive") is False:
            return False
    return bool(rules.get("compact_ephemeral_after_drive_verify", True))


def should_keep_local_staging(plan: dict[str, Any]) -> bool:
    """Research merges (e.g. stablecoin unified panel) need local scrape dirs after archive."""
    if plan.get("keep_local_staging"):
        return True
    meta = plan.get("metadata") or {}
    if meta.get("skynet_slug") or meta.get("ethereum_address"):
        return True
    title = str(plan.get("title") or "")
    return "Etherscan token backfill" in title


def _should_compact_local(plan: dict[str, Any], repo_root: Path) -> bool:
    if not compact_local_after_archive(repo_root):
        return False
    return not should_keep_local_staging(plan)


def _rclone_flags(repo_root: Path) -> list[str]:
    cfg = load_storage_tiers(repo_root)
    canonical = (cfg.get("tiers") or {}).get("canonical") or {}
    flags = list(canonical.get("rclone_extra_flags") or ["--drive-acknowledge-abuse"])
    return flags


def archive_local_to_remote(
    repo_root: Path,
    local_rel: str,
    remote_suffix: str,
    *,
    verify: bool = True,
    excludes: list[str] | None = None,
) -> dict[str, Any]:
    """rclone copy + optional check from repo-relative local path to vault suffix."""
    local = (repo_root / local_rel).resolve()
    if not local.exists():
        return {"ok": False, "error": "local_missing", "local_path": local_rel}
    drive_root = canonical_drive_root(repo_root).rstrip("/")
    if not drive_root:
        return {"ok": False, "error": "drive_root_unset"}
    suffix = remote_suffix.lstrip("/")
    remote = f"{drive_root}/{suffix}"
    flags = _rclone_flags(repo_root)
    cmd = [
        "rclone",
        "copy",
        str(local),
        remote,
        "--transfers",
        "2",
        "--checkers",
        "4",
        "--retries",
        "5",
        "--low-level-retries",
        "10",
        *flags,
    ]
    for glob in excludes or []:
        cmd.extend(["--exclude", glob])
    copy = subprocess.run(cmd, cwd=repo_root, capture_output=True, text=True, timeout=7200, check=False)
    if copy.returncode != 0:
        return {
            "ok": False,
            "stage": "copy",
            "local_path": local_rel,
            "remote_path": remote,
            "stderr": (copy.stderr or copy.stdout or "")[:500],
        }
    verified = True
    if verify:
        check_cmd = [
            "rclone",
            "check",
            str(local),
            remote,
            "--one-way",
            *flags,
        ]
        for glob in excludes or []:
            check_cmd.extend(["--exclude", glob])
        check = subprocess.run(check_cmd, cwd=repo_root, capture_output=True, text=True, timeout=1800, check=False)
        verified = check.returncode == 0
        if not verified:
            return {
                "ok": False,
                "stage": "verify",
                "local_path": local_rel,
                "remote_path": remote,
                "stderr": (check.stderr or check.stdout or "")[:500],
            }
    return {
        "ok": True,
        "verified": verified,
        "local_path": local_rel,
        "remote_path": remote,
        "remote_suffix": suffix,
    }


def compact_ephemeral_path(repo_root: Path, local_rel: str) -> dict[str, Any]:
    path = (repo_root / local_rel).resolve()
    if not path.exists():
        return {"removed": False, "reason": "missing", "path": local_rel}
    try:
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
    except OSError as exc:
        return {"removed": False, "error": str(exc), "path": local_rel}
    return {"removed": True, "path": local_rel}


def remote_suffix_for_collect(
    repo_root: Path,
    plan: dict[str, Any],
    *,
    dataset_id: str,
    job_id: str,
) -> str:
    from scripts.research_data_mcp.archive_after_job import remote_suffix_for_job

    suffix = remote_suffix_for_job(plan, dataset_id, repo_root=repo_root)
    if suffix:
        return suffix
    return f"collection/acquired/procured/{dataset_id or job_id}"


def finalize_job_to_drive(
    repo_root: Path,
    *,
    job_id: str,
    plan: dict[str, Any],
    result: dict[str, Any] | None,
    promoted: list[dict[str, Any]] | None = None,
    materialized: dict[str, Any] | None = None,
    search_goal: str = "",
    compact: bool = True,
) -> dict[str, Any]:
    """Synchronous partition archive — job is not done until GDrive verify passes."""
    from scripts.research_data_mcp.partition_wiring import attach_partition_to_plan, infer_partition_id

    result = result or {}
    plan = dict(plan or {})
    if not plan.get("partition_id"):
        plan = attach_partition_to_plan(
            plan,
            search_goal or str(plan.get("title") or ""),
            repo_root=repo_root,
        )
    if not plan.get("partition_id"):
        ds = str(plan.get("dataset_id") or plan.get("registry_dataset_id") or "").strip()
        plan["partition_id"] = infer_partition_id(
            search_goal,
            url=str(plan.get("url") or ""),
            dataset_id=ds,
            repo_root=repo_root,
        )
    archives: list[dict[str, Any]] = []
    compacted: list[dict[str, Any]] = []
    registry_updates: list[dict[str, Any]] = []

    def _archive(local_rel: str, remote_suffix: str, *, dataset_id: str = "") -> dict[str, Any]:
        row = archive_local_to_remote(repo_root, local_rel, remote_suffix)
        row["dataset_id"] = dataset_id or job_id
        archives.append(row)
        if row.get("ok") and compact and _should_compact_local(plan, repo_root):
            compacted.append(compact_ephemeral_path(repo_root, local_rel))
        if row.get("ok") and dataset_id:
            registry_updates.append(
                {
                    "dataset_id": dataset_id,
                    "canonical_remote": row.get("remote_path"),
                    "partition_remote_suffix": row.get("remote_suffix"),
                }
            )
        return row

    mat = materialized or result.get("materialized") or {}
    if mat.get("canonical_dir"):
        ds_id = str(mat.get("dataset_id") or job_id)
        suffix = remote_suffix_for_collect(repo_root, plan, dataset_id=ds_id, job_id=job_id)
        row = _archive(str(mat["canonical_dir"]), suffix, dataset_id=ds_id)
        if not row.get("ok"):
            return {"ok": False, "error": "materialized_archive_failed", "archives": archives, "failed": row}

    if str(plan.get("job_type") or "") == "scraper_run":
        catalog_dir = str(result.get("catalog_dir") or f"data_lake/spectator_engine/scrapes/{job_id}")
        ds_id = f"scrape_{job_id}"
        suffix = remote_suffix_for_collect(repo_root, plan, dataset_id=ds_id, job_id=job_id)
        row = _archive(catalog_dir, suffix, dataset_id=ds_id)
        if not row.get("ok"):
            return {"ok": False, "error": "scrape_archive_failed", "archives": archives, "failed": row}

    if not mat.get("canonical_dir") and str(plan.get("job_type") or "") != "scraper_run" and promoted:
        from scripts.research_data_mcp.archive_after_job import archive_targets_from_promoted, resolve_archive_target

        registry_path = repo_root / "config/research_query_registry.json"
        for local_pattern, dataset_id in archive_targets_from_promoted(promoted, registry_path):
            target = resolve_archive_target(repo_root, local_pattern)
            if not target:
                continue
            try:
                local_rel = str(target.relative_to(repo_root))
            except ValueError:
                local_rel = str(target)
            suffix = remote_suffix_for_collect(repo_root, plan, dataset_id=dataset_id, job_id=job_id)
            row = _archive(local_rel, suffix, dataset_id=dataset_id)
            if not row.get("ok"):
                return {"ok": False, "error": "promoted_archive_failed", "archives": archives, "failed": row}

    if registry_updates:
        _stamp_registry_drive_paths(repo_root, registry_updates, plan=plan)

    if not archives:
        return {"ok": True, "skipped": True, "reason": "no_archive_targets"}

    return {"ok": True, "archives": archives, "compacted": compacted, "registry_updates": registry_updates}


def _stamp_registry_drive_paths(
    repo_root: Path,
    updates: list[dict[str, Any]],
    *,
    plan: dict[str, Any],
) -> None:
    reg_path = repo_root / "config/research_query_registry.json"
    if not reg_path.is_file():
        return
    doc = json.loads(reg_path.read_text(encoding="utf-8"))
    by_id = {str(r.get("dataset_id")): r for r in doc.get("datasets") or []}
    pid = str(plan.get("partition_id") or "")
    for row in updates:
        did = str(row.get("dataset_id") or "")
        spec = by_id.get(did)
        if not spec:
            continue
        spec["canonical_remote"] = row.get("canonical_remote")
        spec["source_of_truth"] = "gdrive"
        if pid:
            spec["partition_id"] = pid
        spec.setdefault("lineage", {})
        if isinstance(spec["lineage"], dict):
            spec["lineage"]["canonical_remote"] = row.get("canonical_remote")
            if pid:
                spec["lineage"]["partition_id"] = pid
    reg_path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
