#!/usr/bin/env python3
"""Auto-archive procured files to GDrive when storage policy allows."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.research_data_mcp.storage_policy import load_storage_policy


def _rel_path(repo_root: Path, local_path: str) -> str:
    path = Path(local_path)
    if not path.is_absolute():
        return local_path
    try:
        return str(path.relative_to(repo_root))
    except ValueError:
        return str(path)


def maybe_auto_archive(
    gateway: Any,
    *,
    local_path: str,
    dataset_id: str,
    campaign_id: str = "",
) -> dict[str, Any] | None:
    """Queue archive_upload when auto_archive_procured is enabled."""
    policy = load_storage_policy(gateway.repo_root)
    if not policy.get("auto_archive_procured"):
        return None
    rel = _rel_path(gateway.repo_root, local_path.strip())
    if not rel:
        return None
    from scripts.research_data_mcp.archive_after_job import resolve_archive_target

    target = resolve_archive_target(gateway.repo_root, rel)
    if not target:
        return None
    rel = _rel_path(gateway.repo_root, str(target))
    job = gateway.archive_to_gdrive(
        rel,
        remote_suffix=f"collection/acquired/procured/{dataset_id or campaign_id or 'dataset'}",
        title=f"Archive procured {dataset_id or rel}",
        auto_approve=True,
        verify=True,
    )
    return {"local_path": rel, "archive_job": job}


def archive_from_card(gateway: Any, card: dict[str, Any], *, campaign_id: str = "") -> dict[str, Any] | None:
    """Pick primary file from a dataset card and queue archive if policy allows."""
    primary = card.get("primary_file") or {}
    path = str(primary.get("path") or "")
    if not path:
        files = card.get("files") or []
        if files and isinstance(files[0], dict):
            path = str(files[0].get("path") or "")
    if not path:
        return None
    dataset_id = str(card.get("dataset_id") or card.get("handle") or campaign_id or "dataset")
    return maybe_auto_archive(gateway, local_path=path, dataset_id=dataset_id, campaign_id=campaign_id)
