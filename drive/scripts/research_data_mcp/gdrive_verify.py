#!/usr/bin/env python3
"""GDrive / rclone readiness probe for desk health and archive verify."""

from __future__ import annotations

import shutil
import subprocess
import uuid
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


def canonical_remote_name(drive_root: str) -> str:
    """Return the configured rclone remote name without accepting a path as one."""
    raw = str(drive_root or "").strip()
    remote, sep, suffix = raw.partition(":")
    if not sep or not remote or not suffix.lstrip("/"):
        return ""
    if any(ch.isspace() for ch in remote) or "/" in remote or "\\" in remote:
        return ""
    return remote


def gdrive_verify_status(repo_root: Path) -> dict[str, Any]:
    """Light probe — does not copy bytes."""
    repo_root = Path(repo_root).resolve()
    drive_root = canonical_drive_root(repo_root)
    remotes = rclone_remotes()
    remote_name = canonical_remote_name(drive_root)
    remote_ok = bool(remote_name and remote_name in remotes)
    out: dict[str, Any] = {
        "rclone_installed": rclone_ready(),
        # The service archive is host-owned and root-scoped.  Do not expose
        # every other rclone remote through the browser health document.
        "archive_authority": "service_managed",
        "canonical_remote": remote_name or None,
        "canonical_remote_configured": remote_ok,
        "drive_root": drive_root,
        "ready": bool(drive_root and remote_ok and rclone_ready()),
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


def exercise_canonical_archive(repo_root: Path) -> dict[str, Any]:
    """Prove the service archive can write, read and remove one scoped probe.

    This is intentionally a release/preflight operation, never a health-read:
    it creates exactly one zero-byte object below ``collection/.rd_release_probe``
    and removes only that object.  The containing directory is removed only when
    empty.  It proves the same service credential used by canonical collection
    writes without touching research evidence.
    """
    status = gdrive_verify_status(repo_root)
    if not status.get("ready"):
        return {**status, "exercise_ok": False, "exercise_error": "canonical_archive_unavailable"}

    root = str(status["drive_root"]).rstrip("/")
    probe_dir = f"{root}/collection/.rd_release_probe"
    probe = f"{probe_dir}/release-{uuid.uuid4().hex}.ready"
    created = False
    try:
        touch = subprocess.run(["rclone", "touch", probe], capture_output=True, text=True, timeout=45, check=False)
        if touch.returncode != 0:
            return {**status, "exercise_ok": False, "exercise_error": "write_failed"}
        created = True
        listed = subprocess.run(["rclone", "lsf", probe], capture_output=True, text=True, timeout=45, check=False)
        if listed.returncode != 0 or not (listed.stdout or "").strip():
            return {**status, "exercise_ok": False, "exercise_error": "readback_failed"}
        deleted = subprocess.run(["rclone", "deletefile", probe], capture_output=True, text=True, timeout=45, check=False)
        if deleted.returncode != 0:
            return {**status, "exercise_ok": False, "exercise_error": "cleanup_failed"}
        created = False
        # rmdir is non-recursive: it cannot remove a folder that acquired a
        # real object concurrently.
        subprocess.run(["rclone", "rmdir", probe_dir], capture_output=True, text=True, timeout=45, check=False)
        return {**status, "exercise_ok": True, "exercise": "write_read_delete"}
    except (OSError, subprocess.TimeoutExpired):
        return {**status, "exercise_ok": False, "exercise_error": "rclone_unavailable"}
    finally:
        if created:
            try:
                subprocess.run(["rclone", "deletefile", probe], capture_output=True, text=True, timeout=45, check=False)
                subprocess.run(["rclone", "rmdir", probe_dir], capture_output=True, text=True, timeout=45, check=False)
            except (OSError, subprocess.TimeoutExpired):
                pass


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Verify the configured service-owned canonical Drive archive")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--exercise", action="store_true", help="write/read/delete a scoped release probe")
    args = parser.parse_args()
    payload = exercise_canonical_archive(Path(args.repo_root)) if args.exercise else gdrive_verify_status(Path(args.repo_root))
    print(json.dumps(payload, sort_keys=True))
    raise SystemExit(0 if payload.get("exercise_ok", payload.get("ready")) else 1)
