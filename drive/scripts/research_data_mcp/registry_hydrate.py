#!/usr/bin/env python3
"""Hydrate registry datasets from canonical GDrive when local staging was compacted."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from scripts.research_data_mcp.collection_hydrate import execute_hydrate
from scripts.research_data_mcp.procurement_fast import local_path_has_data


def _canonical_remote(spec: dict[str, Any]) -> str:
    remote = str(spec.get("canonical_remote") or "").strip()
    if remote:
        return remote
    lineage = spec.get("lineage") or {}
    if isinstance(lineage, dict):
        return str(lineage.get("canonical_remote") or "").strip()
    return ""


def _local_path(spec: dict[str, Any]) -> str:
    for key in ("local_path", "local_file"):
        val = str(spec.get(key) or "").strip()
        if val:
            return val
    root = str(spec.get("local_root") or "").strip()
    fname = str(spec.get("local_file") or "").strip()
    if root and fname:
        return f"{root.rstrip('/')}/{fname}"
    return ""


def dataset_needs_hydrate(repo_root: Path, spec: dict[str, Any]) -> bool:
    local = _local_path(spec)
    remote = _canonical_remote(spec)
    if not local or not remote:
        return False
    if str(spec.get("source_of_truth") or "") not in {"", "gdrive"} and not remote:
        return False
    return not local_path_has_data(repo_root, local)


def build_registry_hydrate_plan(repo_root: Path, spec: dict[str, Any]) -> dict[str, Any] | None:
    """Build rclone hydrate plan for a registry row with canonical_remote."""
    repo_root = Path(repo_root).resolve()
    local_rel = _local_path(spec)
    remote = _canonical_remote(spec)
    if not local_rel or not remote:
        return None
    if local_path_has_data(repo_root, local_rel):
        return {"skip_reason": "already_on_local", "local_path": local_rel}

    local_abs = (repo_root / local_rel).resolve()
    local_abs.parent.mkdir(parents=True, exist_ok=True)
    remote = remote.rstrip("/")
    did = str(spec.get("dataset_id") or "dataset")

    # Single file target: copy file or first matching file from remote folder.
    if "*" not in local_rel and not local_rel.endswith("/"):
        basename = Path(local_rel).name
        return {
            "title": f"Hydrate {did}",
            "job_type": "collection_hydrate",
            "scope": "registry_file",
            "remote_path": remote,
            "remote_basename": basename,
            "local_path": local_rel,
            "local_abs": str(local_abs),
            "verify": True,
            "launchable": True,
            "timeout_seconds": 600,
            "dataset_id": did,
        }

    return {
        "title": f"Hydrate {did}",
        "job_type": "collection_hydrate",
        "scope": "full",
        "remote_path": remote,
        "local_path": local_rel.rstrip("*").rstrip("/") or local_rel,
        "local_abs": str(local_abs.parent if local_abs.suffix else local_abs),
        "verify": True,
        "launchable": True,
        "timeout_seconds": 1200,
        "dataset_id": did,
    }


def _rclone_flags() -> list[str]:
    return ["--drive-acknowledge-abuse"]


def _hydrate_registry_file(plan: dict[str, Any], *, log_path: Path | None = None) -> dict[str, Any]:
    remote = str(plan["remote_path"]).rstrip("/")
    basename = str(plan.get("remote_basename") or Path(plan["local_path"]).name)
    local = Path(plan["local_abs"])
    local.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "rclone",
        "copyto",
        f"{remote}/{basename}",
        str(local),
        *_rclone_flags(),
        "--retries",
        "5",
    ]
    if log_path:
        with log_path.open("w", encoding="utf-8") as log:
            proc = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, timeout=600, check=False)
    else:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600, check=False)

    if proc.returncode == 0 and local.is_file() and local.stat().st_size > 0:
        return {"ok": True, "local_path": str(plan["local_path"]), "bytes": local.stat().st_size}

    # Remote may be a directory without basename at top level — copy tree and pick file.
    parent = local.parent
    cmd2 = [
        "rclone",
        "copy",
        remote,
        str(parent),
        *_rclone_flags(),
        "--transfers",
        "2",
        "--retries",
        "5",
    ]
    if log_path:
        with log_path.open("a", encoding="utf-8") as log:
            proc2 = subprocess.run(cmd2, stdout=log, stderr=subprocess.STDOUT, timeout=1200, check=False)
    else:
        proc2 = subprocess.run(cmd2, capture_output=True, text=True, timeout=1200, check=False)

    if local.is_file() and local.stat().st_size > 0:
        return {"ok": True, "local_path": str(plan["local_path"]), "bytes": local.stat().st_size}

    # If basename differs on remote, accept any same-suffix file in parent.
    if local.suffix:
        matches = sorted(parent.glob(f"*{local.suffix}"))
        if matches and matches[0].stat().st_size > 0:
            if matches[0] != local:
                shutil.copy2(matches[0], local)
            return {"ok": True, "local_path": str(plan["local_path"]), "bytes": local.stat().st_size}

    return {
        "ok": False,
        "error": "hydrate_failed",
        "returncode": proc2.returncode if "proc2" in dir() else proc.returncode,
    }


def ensure_registry_local_bytes(
    repo_root: Path,
    spec: dict[str, Any],
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Pull canonical GDrive bytes to local_path when missing. No-op if already on disk."""
    repo_root = Path(repo_root).resolve()
    if not dataset_needs_hydrate(repo_root, spec):
        return {"skipped": True, "reason": "local_present_or_no_remote"}

    if not shutil.which("rclone"):
        return {"ok": False, "error": "rclone_missing", "skipped": False}

    plan = build_registry_hydrate_plan(repo_root, spec)
    if not plan:
        return {"ok": False, "error": "no_hydrate_plan"}
    if plan.get("skip_reason"):
        return {"skipped": True, "reason": plan["skip_reason"]}

    if dry_run:
        return {"dry_run": True, "plan": plan}

    if plan.get("scope") == "registry_file":
        return _hydrate_registry_file(plan)

    return execute_hydrate(repo_root, plan)


def ensure_dataset_hydrated(
    repo_root: Path,
    dataset_id: str,
    *,
    registry_path: Path | None = None,
) -> dict[str, Any]:
    reg_path = registry_path or (repo_root / "config/research_query_registry.json")
    doc = json.loads(reg_path.read_text(encoding="utf-8"))
    spec = next((d for d in doc.get("datasets") or [] if d.get("dataset_id") == dataset_id), None)
    if not spec:
        return {"ok": False, "error": "unknown_dataset", "dataset_id": dataset_id}
    out = ensure_registry_local_bytes(repo_root, spec)
    out["dataset_id"] = dataset_id
    return out
