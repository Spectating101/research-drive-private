#!/usr/bin/env python3
"""GDrive / rclone readiness probe for desk health and archive verify."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

from scripts.research_data_mcp.storage_tiers import canonical_drive_root


def rclone_ready() -> bool:
    return bool(shutil.which("rclone"))


def rclone_remotes() -> list[str]:
    if not rclone_ready():
        return []
    try:
        proc = subprocess.run(
            ["rclone", "listremotes"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    return [line.strip().rstrip(":") for line in (proc.stdout or "").splitlines() if line.strip()]


def gdrive_verify_status(repo_root: Path) -> dict[str, Any]:
    """Light probe — does not copy bytes."""
    repo_root = Path(repo_root).resolve()
    drive_root = canonical_drive_root(repo_root)
    remotes = rclone_remotes()
    gdrive_ok = any(r == "gdrive" for r in remotes)
    out: dict[str, Any] = {
        "rclone_installed": rclone_ready(),
        "remotes": remotes,
        "gdrive_remote": gdrive_ok,
        "drive_root": drive_root,
        "ready": bool(drive_root and gdrive_ok and rclone_ready()),
    }
    if not out["ready"]:
        return out
    try:
        proc = subprocess.run(
            ["rclone", "lsd", drive_root, "--max-depth", "1"],
            capture_output=True,
            text=True,
            timeout=45,
            check=False,
        )
        out["drive_list_ok"] = proc.returncode == 0
        out["drive_list_error"] = (proc.stderr or proc.stdout or "").strip()[:200] if proc.returncode else ""
    except (OSError, subprocess.TimeoutExpired) as exc:
        out["drive_list_ok"] = False
        out["drive_list_error"] = str(exc)[:200]
    out["ready"] = bool(out.get("drive_list_ok"))
    return out
