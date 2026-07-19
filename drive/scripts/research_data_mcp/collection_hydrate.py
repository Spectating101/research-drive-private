#!/usr/bin/env python3
"""Hydrate collection partitions / DataCite shards from canonical GDrive → local cache."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from scripts.research_data_mcp.collection_dictionary import build_dictionary, dictionary_path
from scripts.research_data_mcp.collection_catalog import catalog_root, get_swarm
from scripts.research_data_mcp.collection_resolve import canonical_remote, load_partitions, partition_by_id
from scripts.research_data_mcp.data_paths import bulk_data_lake_root, bulk_storage_root
from scripts.research_data_mcp.procurement_fast import local_path_has_data, wants_refresh
from scripts.research_data_mcp.storage_tiers import canonical_drive_root, is_bulk_cache_path, resolve_data_path_tiered

HYDRATE_FULL_RE = re.compile(r"\b(full|bulk|jsonl|all\s+files)\b", re.I)
METADATA_GLOBS = (
    "datacite.complete.json",
    "datacite.checkpoint.json",
    "datacite.heartbeat.json",
    "full_index_manifest.json",
)

RCLONE_ACK_ABUSE = ("--drive-acknowledge-abuse",)  # GDrive false-positive quarantine on jsonl.gz


def _rclone_base_flags() -> list[str]:
    return list(RCLONE_ACK_ABUSE)


def _drive_root(repo_root: Path) -> str:
    root = canonical_drive_root(repo_root)
    if root:
        return root.rstrip("/")
    cfg_path = Path(repo_root) / "config/yzu_cluster.json"
    if cfg_path.is_file():
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        return str((cfg.get("storage") or {}).get("drive_root") or "").rstrip("/")
    return ""


def _resolve_local_dest(repo_root: Path, rel_path: str) -> Path:
    rel = str(rel_path).replace("\\", "/").lstrip("/")
    dest = resolve_data_path_tiered(repo_root, rel)
    dest.parent.mkdir(parents=True, exist_ok=True)
    return dest


def _dictionary_row(repo_root: Path, *, partition_id: str = "", row_id: str = "") -> dict[str, Any] | None:
    path = dictionary_path(repo_root)
    doc = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else build_dictionary(repo_root)
    tables = doc.get("tables") or {}
    if row_id:
        for rows in tables.values():
            for row in rows:
                if str(row.get("id")) == row_id:
                    return row
    if partition_id:
        for row in tables.get("partitions") or []:
            if str(row.get("id")) == partition_id:
                return row
        for row in tables.get("datacite_shards") or []:
            if str(row.get("partition_id")) == partition_id and not row_id:
                continue
    return None


def infer_hydrate_scope(message: str, *, row: dict[str, Any] | None = None, repo_root: Path | None = None) -> str:
    """metadata = status JSON only; full = entire remote tree."""
    if HYDRATE_FULL_RE.search(message or ""):
        return "full"
    av = (row or {}).get("availability") or {}
    records = int(av.get("records_committed") or 0)
    if (row or {}).get("kind") == "datacite_shard" and records > 2_000_000:
        return "metadata"
    pid = str((row or {}).get("partition_id") or "")
    if pid and repo_root is not None:
        part = partition_by_id(Path(repo_root).resolve(), pid)
        if part:
            hint = str(part.get("drive_size_hint") or "")
            if "GiB" in hint:
                try:
                    gb = float(hint.split()[0])
                    if gb > 8:
                        return "metadata"
                except ValueError:
                    pass
    return "full"


def build_hydrate_plan(
    repo_root: Path,
    *,
    partition_id: str = "",
    shard: str = "",
    row_id: str = "",
    scope: str = "auto",
    message: str = "",
) -> dict[str, Any]:
    repo_root = Path(repo_root).resolve()
    row: dict[str, Any] | None = None
    if row_id:
        row = _dictionary_row(repo_root, row_id=row_id)
    elif shard:
        doc = json.loads(dictionary_path(repo_root).read_text(encoding="utf-8")) if dictionary_path(repo_root).is_file() else build_dictionary(repo_root)
        row = next((r for r in (doc.get("tables") or {}).get("datacite_shards") or [] if r.get("shard") == shard), None)
    elif partition_id:
        row = _dictionary_row(repo_root, partition_id=partition_id)

    part: dict[str, Any] | None = None
    if row and row.get("kind") == "datacite_shard":
        shard = str(row.get("shard") or shard)
        part = partition_by_id(repo_root, str(row.get("partition_id") or "catalog.datacite-harvest"))
    elif partition_id or (row and row.get("kind") == "partition"):
        pid = partition_id or str(row.get("id") or "")
        part = partition_by_id(repo_root, pid)
        row = row or _dictionary_row(repo_root, partition_id=pid)

    if not part:
        raise ValueError(f"unknown hydrate target partition_id={partition_id!r} shard={shard!r} row_id={row_id!r}")

    drive_root = _drive_root(repo_root)
    if not drive_root:
        raise ValueError("canonical GDrive root is not configured")

    legacy_drive = str(part.get("legacy_drive_path") or "").strip("/")
    legacy_local = str(part.get("legacy_local_path") or "").strip("/")
    if not legacy_drive or not legacy_local:
        raise ValueError(f"partition {part['id']} missing legacy_drive_path or legacy_local_path")

    remote_rel = legacy_drive
    local_rel = legacy_local
    title = str(part.get("title") or part["id"])
    if shard:
        remote_rel = f"{legacy_drive}/{shard}"
        local_rel = f"{legacy_local}/{shard}"
        title = f"{title} / {shard}"

    if scope == "auto":
        scope = infer_hydrate_scope(message, row=row, repo_root=repo_root)

    remote = f"{drive_root}/{remote_rel}"
    local_dest = _resolve_local_dest(repo_root, local_rel)
    local_path_logical = local_rel

    av = (row or {}).get("availability") or {}
    if av.get("on_local") and scope == "full" and local_path_has_data(repo_root, local_path_logical):
        return {
            "title": f"Hydrate {title}",
            "job_type": "collection_hydrate",
            "partition_id": part["id"],
            "shard": shard or None,
            "scope": scope,
            "remote_path": remote,
            "local_path": local_path_logical,
            "launchable": False,
            "skip_reason": "already_on_local",
            "action_note": f"**{title}** already has local data at `{local_path_logical}`. Say **refresh** to re-pull from source.",
        }

    plan: dict[str, Any] = {
        "title": f"Hydrate {title} ({scope})",
        "job_type": "collection_hydrate",
        "partition_id": str(part["id"]),
        "shard": shard or "",
        "scope": scope,
        "remote_path": remote,
        "local_path": local_path_logical,
        "local_abs": str(local_dest),
        "verify": scope == "full",
        "launchable": True,
        "timeout_seconds": 7200 if scope == "full" else 600,
        "records_committed": av.get("records_committed"),
        "missing": list(av.get("missing") or []),
    }
    bulk = bulk_storage_root()
    if bulk and is_bulk_cache_path(repo_root, local_rel):
        plan["dest_tier"] = "bulk_cache"
        plan["bulk_root"] = str(bulk)
    else:
        plan["dest_tier"] = "nvme"
    if shard:
        swarm = get_swarm(repo_root, shard)
        if swarm:
            plan["catalog_swarm_id"] = swarm.get("swarm_id")
            plan["piece_count"] = swarm.get("piece_count")
            plan["pieces_local"] = swarm.get("pieces_local")
            plan["fetch"] = swarm.get("fetch")
    return plan


def plan_from_candidate(repo_root: Path, candidate: dict[str, Any], *, message: str = "") -> dict[str, Any]:
    kind = str(candidate.get("kind") or "")
    if kind in {"datacite_shard", "datacite_swarm"}:
        shard = str(candidate.get("shard") or "")
        if not shard:
            payload = candidate.get("payload") or {}
            swarm = payload.get("swarm") or {}
            shard = str(swarm.get("shard") or payload.get("shard") or "")
        if not shard and candidate.get("id", "").startswith("datacite:"):
            shard = str(candidate["id"]).split(":", 1)[-1]
        if not shard and candidate.get("id", "").startswith("datacite_shard:"):
            shard = str(candidate["id"]).split(":", 1)[-1]
        return build_hydrate_plan(repo_root, shard=shard, message=message)
    pid = str(candidate.get("partition_id") or "")
    if not pid and kind == "partition":
        pid = str(candidate.get("id") or "")
    if pid:
        return build_hydrate_plan(repo_root, partition_id=pid, message=message)
    raise ValueError("candidate is not a hydrate target (need partition_id or datacite shard)")


def plan_hydrate_for_message(repo_root: Path, message: str) -> dict[str, Any] | None:
    """If user asks to hydrate and we can resolve a target, return job plan."""
    if not re.search(r"\bhydrate\b", message, re.I):
        return None
    if wants_refresh(message):
        return None

    m_part = re.search(r"\bhydrate\s+partition\s+([\w.-]+)\b", message, re.I)
    if m_part:
        return build_hydrate_plan(repo_root, partition_id=m_part.group(1), message=message)

    m_shard = re.search(r"\bhydrate\s+(?:shard\s+)?(y[\w_]+)\b", message, re.I)
    if m_shard:
        return build_hydrate_plan(repo_root, shard=m_shard.group(1), message=message)

    from scripts.research_data_mcp.collection_index import search_index

    hits = search_index(repo_root, message, limit=4)
    for hit in hits:
        if str(hit.get("action")) in {"hydrate", "search_datacite"}:
            return plan_from_candidate(repo_root, hit, message=message)
    return None


def _rclone_copy_files(remote: str, local: Path, includes: tuple[str, ...], *, log_path: Path | None) -> dict[str, Any]:
    copied = 0
    errors: list[str] = []
    local.mkdir(parents=True, exist_ok=True)
    for name in includes:
        cmd = [
            "rclone",
            "copyto",
            f"{remote.rstrip('/')}/{name}",
            str(local / name),
            *_rclone_base_flags(),
            "--retries",
            "5",
            "--low-level-retries",
            "10",
        ]
        if log_path:
            with log_path.open("a", encoding="utf-8") as log:
                proc = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, timeout=300, check=False)
        else:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300, check=False)
        if proc.returncode == 0 and (local / name).is_file():
            copied += 1
        else:
            errors.append(name)
    return {"scope": "metadata", "files_copied": copied, "errors": errors}


def execute_hydrate(repo_root: Path, plan: dict[str, Any], *, job_id: str = "", dry_run: bool = False) -> dict[str, Any]:
    repo_root = Path(repo_root).resolve()
    if plan.get("skip_reason"):
        return {"skipped": True, "reason": plan["skip_reason"]}

    remote = str(plan["remote_path"])
    local = Path(plan.get("local_abs") or (repo_root / plan["local_path"]))
    scope = str(plan.get("scope") or "full")
    log_path = None
    if job_id:
        log_path = repo_root / "data_lake/yzu_cluster/jobs" / job_id / "hydrate.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)

    if dry_run:
        return {"dry_run": True, "remote_path": remote, "local_path": str(local), "scope": scope}

    if scope == "metadata":
        result = _rclone_copy_files(remote, local, METADATA_GLOBS, log_path=log_path)
        result.update({"remote_path": remote, "local_path": str(plan.get("local_path") or "")})
        return result

    local.mkdir(parents=True, exist_ok=True)
    cmd = [
        "rclone",
        "copy",
        remote,
        str(local),
        *_rclone_base_flags(),
        "--transfers",
        "4",
        "--checkers",
        "8",
        "--retries",
        "5",
        "--low-level-retries",
        "10",
        "--stats-one-line",
    ]
    if log_path:
        with log_path.open("w", encoding="utf-8") as log:
            proc = subprocess.run(
                cmd,
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=int(plan.get("timeout_seconds", 7200)),
                check=False,
            )
    else:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=int(plan.get("timeout_seconds", 7200)),
            check=False,
        )
    if proc.returncode:
        raise RuntimeError(f"rclone hydrate failed (exit {proc.returncode})")

    verified = False
    if plan.get("verify"):
        check = subprocess.run(
            ["rclone", "check", remote, str(local), "--one-way", "--size-only"],
            capture_output=True,
            text=True,
            timeout=1800,
            check=False,
        )
        if check.returncode:
            raise RuntimeError("rclone verify failed after hydrate")
        verified = True

    rel = str(plan.get("local_path") or "")
    on_disk = local_path_has_data(repo_root, rel)
    return {
        "remote_path": remote,
        "local_path": rel,
        "scope": scope,
        "verified": verified,
        "local_ready": on_disk,
        "bytes_local": _dir_bytes(local),
    }


def _dir_bytes(path: Path) -> int:
    if not path.is_dir():
        return path.stat().st_size if path.is_file() else 0
    total = 0
    for p in path.rglob("*"):
        if p.is_file():
            try:
                total += p.stat().st_size
            except OSError:
                continue
    return total


def collection_status_summary(repo_root: Path) -> dict[str, Any]:
    """Desk-facing inventory summary from collection_dictionary."""
    repo_root = Path(repo_root).resolve()
    path = dictionary_path(repo_root)
    doc = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else build_dictionary(repo_root)
    summary = dict(doc.get("summary") or {})
    gaps = (doc.get("gaps") or [])[:12]
    bulk = bulk_storage_root()
    summary["bulk_cache_mounted"] = bulk is not None
    if bulk:
        try:
            usage = shutil.disk_usage(bulk)
            summary["bulk_cache_free_gb"] = round(usage.free / (1024**3), 1)
        except OSError:
            pass
    summary["top_gaps"] = gaps
    summary["dictionary_path"] = str(path.relative_to(repo_root)) if path.is_file() else ""
    cat = catalog_root(repo_root) / "INDEX.json"
    summary["catalog_path"] = str(cat.relative_to(repo_root)) if cat.is_file() else ""
    return summary
