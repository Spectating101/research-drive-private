#!/usr/bin/env python3
"""Mirror local/cache partition trees to the canonical GDrive vault.

Flow:
  1. Optional remote_pull bash scripts (cluster rsync / spectator failover).
  2. For each partition in collection_partitions.json with legacy_local_path + target_drive_path:
     resolve tiered local path → rclone copy → rclone check (copy_verify policy).
  3. Extra sync targets (exports, skynet harvest) from config/partition_sync.json.
  4. Write JSON report; optionally refresh inventory manifest.

Never uses rclone sync (hydration contract: copy + verify only).

Usage:
  python scripts/ops/sync_collection_partitions_to_gdrive.py --dry-run --pretty
  python scripts/ops/sync_collection_partitions_to_gdrive.py --partition markets.crypto-coingecko
  python scripts/ops/sync_collection_partitions_to_gdrive.py --all --include-large
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from scripts.research_data_mcp.storage_tiers import (  # noqa: E402
    canonical_drive_root,
    load_storage_tiers,
    resolve_data_path_tiered,
)

PARTITIONS_PATH = REPO / "config/collection_partitions.json"
SYNC_CONFIG_PATH = REPO / "config/partition_sync.json"
LOG_DIR = REPO / "logs"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _dir_stats(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False, "bytes": 0, "files": 0}
    if path.is_file():
        try:
            nbytes = path.stat().st_size
        except OSError:
            nbytes = 0
        return {"exists": True, "bytes": nbytes, "files": 1, "is_file": True}
    total = 0
    count = 0
    try:
        for p in path.rglob("*"):
            if p.is_file():
                count += 1
                try:
                    total += p.stat().st_size
                except OSError:
                    pass
    except OSError:
        return {"exists": True, "bytes": 0, "files": 0, "error": "walk_failed"}
    return {"exists": True, "bytes": total, "files": count, "is_file": False}


@dataclass
class SyncJob:
    job_id: str
    partition_id: str
    local_path: str
    remote_path: str
    exclude_globs: list[str] = field(default_factory=list)
    copyto_overrides: dict[str, str] = field(default_factory=dict)
    optional: bool = False
    skip_reason: str = ""
    priority: int = 50

    def resolved_local(self, repo_root: Path) -> Path:
        return resolve_data_path_tiered(repo_root, self.local_path)


def load_sync_config() -> dict[str, Any]:
    if SYNC_CONFIG_PATH.is_file():
        return _load_json(SYNC_CONFIG_PATH)
    return {}


def build_sync_jobs(
    repo_root: Path,
    partitions_cfg: dict[str, Any],
    sync_cfg: dict[str, Any],
    *,
    partition_filter: str = "",
    include_large: bool = False,
) -> list[SyncJob]:
    """Build ordered sync jobs from partitions + extras."""
    do_not = set(sync_cfg.get("do_not_sync_ids") or [])
    large_ids = set(sync_cfg.get("large_partition_ids") or [])
    overrides = sync_cfg.get("partition_overrides") or {}
    jobs: list[SyncJob] = []

    tier_priority = {"hot": 10, "cache": 20, "migrated": 30, "local_only": 40, "ops": 90}

    for part in partitions_cfg.get("partitions") or []:
        pid = str(part.get("id") or "")
        if not pid or pid in do_not:
            continue
        if partition_filter and pid != partition_filter:
            continue
        local_rel = part.get("legacy_local_path")
        target = part.get("target_drive_path")
        if not local_rel or not target:
            continue
        if pid in large_ids and not include_large:
            jobs.append(
                SyncJob(
                    job_id=pid,
                    partition_id=pid,
                    local_path=str(local_rel),
                    remote_path="",
                    skip_reason="large_partition_skipped",
                    priority=99,
                )
            )
            continue
        ov = overrides.get(pid) or {}
        tier = str(part.get("tier") or "cache")
        status = str(part.get("status") or "")
        pri = tier_priority.get(tier, 50)
        if status == "local_only":
            pri = tier_priority.get("local_only", 40)
        jobs.append(
            SyncJob(
                job_id=pid,
                partition_id=pid,
                local_path=str(local_rel),
                remote_path=str(target),
                exclude_globs=list(ov.get("exclude_globs") or []),
                copyto_overrides=dict(ov.get("copyto_overrides") or {}),
                optional=bool(ov.get("optional")),
                priority=pri,
            )
        )

    if partition_filter:
        return sorted(jobs, key=lambda j: j.priority)

    for extra in sync_cfg.get("extra_syncs") or []:
        eid = str(extra.get("id") or "")
        local_rel = extra.get("local_path")
        suffix = extra.get("remote_suffix")
        if not eid or not local_rel or not suffix:
            continue
        ep = str(extra.get("partition_id") or eid)
        if partition_filter and ep != partition_filter and eid != partition_filter:
            continue
        jobs.append(
            SyncJob(
                job_id=eid,
                partition_id=ep,
                local_path=str(local_rel),
                remote_path=str(suffix),
                optional=bool(extra.get("optional")),
                priority=35,
            )
        )

    return sorted(jobs, key=lambda j: (j.priority, j.job_id))


def remote_full_path(repo_root: Path, remote_suffix: str) -> str:
    root = canonical_drive_root(repo_root).rstrip("/")
    suffix = remote_suffix.lstrip("/")
    if suffix.startswith("collection/") or suffix.startswith("datacite_catalog/"):
        return f"{root}/{suffix}"
    return f"{root}/{suffix}"


def rclone_copy_verify(
    local: Path,
    remote: str,
    *,
    excludes: list[str],
    copyto_overrides: dict[str, str],
    rclone_cfg: dict[str, Any],
    dry_run: bool,
    log_path: Path | None = None,
) -> dict[str, Any]:
    if not local.exists():
        return {"ok": False, "error": "local_missing", "local": str(local)}
    if dry_run:
        return {"ok": True, "dry_run": True, "local": str(local), "remote": remote}

    transfers = str(rclone_cfg.get("transfers", 2))
    checkers = str(rclone_cfg.get("checkers", 4))
    retries = str(rclone_cfg.get("retries", 5))
    llr = str(rclone_cfg.get("low_level_retries", 10))
    timeout = int(rclone_cfg.get("timeout_seconds", 7200))
    verify_timeout = int(rclone_cfg.get("verify_timeout_seconds", 1800))

    extra_flags = list(rclone_cfg.get("extra_flags") or [])

    copy_cmd = [
        "rclone",
        "copy",
        str(local),
        remote,
        "--transfers",
        transfers,
        "--checkers",
        checkers,
        "--retries",
        retries,
        "--low-level-retries",
        llr,
        "--stats-one-line",
        *extra_flags,
    ]
    for glob in excludes:
        copy_cmd.extend(["--exclude", glob])
    for name in copyto_overrides:
        copy_cmd.extend(["--exclude", name])

    verify_mode = str(rclone_cfg.get("verify_mode") or "size-only")
    check_cmd = [
        "rclone",
        "check",
        str(local),
        remote,
        "--one-way",
        f"--{verify_mode}" if verify_mode in {"size-only", "checksum"} else "--size-only",
        *extra_flags,
    ]
    for glob in excludes:
        check_cmd.extend(["--exclude", glob])
    for name in copyto_overrides:
        check_cmd.extend(["--exclude", name])

    stdout_chunks: list[str] = []

    def _run(cmd: list[str], t: int) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            cmd,
            cwd=REPO,
            capture_output=True,
            text=True,
            timeout=t,
            check=False,
        )

    copy_proc = _run(copy_cmd, timeout)
    stdout_chunks.append(copy_proc.stdout or "")
    stdout_chunks.append(copy_proc.stderr or "")
    if copy_proc.returncode != 0:
        return {
            "ok": False,
            "stage": "copy",
            "returncode": copy_proc.returncode,
            "stderr": (copy_proc.stderr or copy_proc.stdout or "")[:500],
        }

    copyto_results: list[dict[str, Any]] = []
    for local_name, remote_rel in copyto_overrides.items():
        src = local / local_name
        if not src.is_file():
            copyto_results.append({"file": local_name, "ok": False, "error": "missing"})
            continue
        dst = f"{remote.rstrip('/')}/{remote_rel.lstrip('/')}"
        cto_cmd = ["rclone", "copyto", str(src), dst, *extra_flags]
        cto_proc = _run(cto_cmd, timeout)
        stdout_chunks.append(cto_proc.stdout or "")
        stdout_chunks.append(cto_proc.stderr or "")
        copyto_results.append(
            {"file": local_name, "remote": dst, "ok": cto_proc.returncode == 0, "returncode": cto_proc.returncode}
        )
        if cto_proc.returncode != 0:
            return {
                "ok": False,
                "stage": "copyto",
                "file": local_name,
                "returncode": cto_proc.returncode,
                "stderr": (cto_proc.stderr or cto_proc.stdout or "")[:500],
                "copyto": copyto_results,
            }

    verified = False
    if rclone_cfg.get("verify", True):
        check_proc = _run(check_cmd, verify_timeout)
        stdout_chunks.append(check_proc.stdout or "")
        stdout_chunks.append(check_proc.stderr or "")
        verified = check_proc.returncode == 0
        if not verified:
            return {
                "ok": False,
                "stage": "verify",
                "returncode": check_proc.returncode,
                "stderr": (check_proc.stderr or check_proc.stdout or "")[:500],
            }
    else:
        verified = True

    if log_path:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("\n".join(stdout_chunks), encoding="utf-8")

    return {"ok": True, "verified": verified, "local": str(local), "remote": remote, "copyto": copyto_results}


def run_remote_pulls(
    repo_root: Path,
    sync_cfg: dict[str, Any],
    *,
    dry_run: bool,
    skip_pull: bool,
) -> list[dict[str, Any]]:
    if skip_pull:
        return []
    results: list[dict[str, Any]] = []
    for spec in sync_cfg.get("remote_pulls") or []:
        if not spec.get("enabled", True):
            results.append({"id": spec.get("id"), "skipped": True, "reason": "disabled"})
            continue
        script = str(spec.get("script") or "")
        script_path = repo_root / script
        if not script_path.is_file():
            results.append({"id": spec.get("id"), "ok": False, "error": f"missing script: {script}"})
            continue
        if dry_run:
            results.append({"id": spec.get("id"), "dry_run": True, "script": script})
            continue
        proc = subprocess.run(
            ["bash", str(script_path)],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=int(spec.get("timeout_seconds", 600)),
            check=False,
        )
        results.append(
            {
                "id": spec.get("id"),
                "ok": proc.returncode == 0,
                "returncode": proc.returncode,
                "stdout_tail": (proc.stdout or "")[-400:],
                "stderr_tail": (proc.stderr or "")[-400:],
            }
        )
    return results


def run_inventory(*, quick: bool) -> dict[str, Any]:
    cmd = [sys.executable, "scripts/data_catalog/inventory_canonical_collection.py"]
    if quick:
        cmd.append("--quick")
    proc = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True, timeout=1800, check=False)
    return {"ok": proc.returncode == 0, "returncode": proc.returncode, "stderr": (proc.stderr or "")[:300]}


def update_partition_drive_status(
    partitions_cfg: dict[str, Any],
    synced_ids: list[str],
) -> bool:
    changed = False
    now = _utc_now()
    synced = set(synced_ids)
    for part in partitions_cfg.get("partitions") or []:
        pid = str(part.get("id") or "")
        if pid not in synced:
            continue
        part["drive_last_synced_at"] = now
        if part.get("status") == "local_only":
            part["status"] = "synced"
            part["drive_mirror"] = True
            changed = True
        elif not part.get("drive_last_synced_at"):
            changed = True
    return changed


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--partition", metavar="ID", help="Sync one partition id only")
    ap.add_argument("--all", action="store_true", help="Sync all eligible partitions (default)")
    ap.add_argument("--include-large", action="store_true", help="Include GDELT + DataCite harvest sizes")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-pull", action="store_true", help="Skip remote_pull rsync scripts")
    ap.add_argument("--skip-inventory", action="store_true")
    ap.add_argument("--update-partition-status", action="store_true", help="Stamp drive_last_synced_at in partitions JSON")
    ap.add_argument("--pretty", action="store_true")
    args = ap.parse_args()

    if not args.partition and not args.all:
        args.all = True

    partitions_cfg = _load_json(PARTITIONS_PATH)
    sync_cfg = load_sync_config()
    rclone_cfg = sync_cfg.get("default_rclone") or {}
    tiers = load_storage_tiers(REPO)
    upload_policy = (tiers.get("tiers") or {}).get("canonical", {}).get("upload_policy", "copy_verify")
    if upload_policy != "copy_verify":
        print(f"warning: canonical upload_policy={upload_policy!r} (expected copy_verify)", file=sys.stderr)

    jobs = build_sync_jobs(
        REPO,
        partitions_cfg,
        sync_cfg,
        partition_filter=args.partition or "",
        include_large=args.include_large,
    )

    report: dict[str, Any] = {
        "started_at": _utc_now(),
        "dry_run": args.dry_run,
        "include_large": args.include_large,
        "drive_root": canonical_drive_root(REPO),
        "remote_pulls": [],
        "jobs": [],
        "summary": {"ok": 0, "skipped": 0, "failed": 0, "optional_missing": 0},
    }

    report["remote_pulls"] = run_remote_pulls(REPO, sync_cfg, dry_run=args.dry_run, skip_pull=args.skip_pull)

    synced_ids: list[str] = []
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    for job in jobs:
        row: dict[str, Any] = {
            "job_id": job.job_id,
            "partition_id": job.partition_id,
            "local_path": job.local_path,
            "remote_suffix": job.remote_path,
            "optional": job.optional,
        }
        if job.skip_reason:
            row["status"] = "skipped"
            row["reason"] = job.skip_reason
            report["summary"]["skipped"] += 1
            report["jobs"].append(row)
            continue

        local = job.resolved_local(REPO)
        row["resolved_local"] = str(local)
        row["local_stats"] = _dir_stats(local)

        if not local.exists() or row["local_stats"].get("bytes", 0) == 0:
            if job.optional:
                row["status"] = "optional_missing"
                report["summary"]["optional_missing"] += 1
            else:
                row["status"] = "skipped"
                row["reason"] = "local_empty_or_missing"
                report["summary"]["skipped"] += 1
            report["jobs"].append(row)
            continue

        remote = remote_full_path(REPO, job.remote_path)
        row["remote_path"] = remote

        if args.dry_run:
            row["status"] = "dry_run"
            report["summary"]["ok"] += 1
            report["jobs"].append(row)
            continue

        log_path = LOG_DIR / f"partition_sync_{job.job_id.replace('.', '_')}.log"
        result = rclone_copy_verify(
            local,
            remote,
            excludes=job.exclude_globs,
            copyto_overrides=job.copyto_overrides,
            rclone_cfg=rclone_cfg,
            dry_run=False,
            log_path=log_path,
        )
        row["rclone"] = result
        row["log"] = str(log_path.relative_to(REPO))
        if result.get("ok"):
            row["status"] = "ok"
            report["summary"]["ok"] += 1
            synced_ids.append(job.partition_id)
        else:
            row["status"] = "failed"
            report["summary"]["failed"] += 1
        report["jobs"].append(row)

    report["finished_at"] = _utc_now()

    post = sync_cfg.get("post_sync") or {}
    run_inventory_post = (
        not args.dry_run
        and not args.skip_inventory
        and not args.partition
        and post.get("inventory")
        and report["summary"]["failed"] == 0
    )
    if run_inventory_post:
        report["inventory"] = run_inventory(quick=bool(post.get("inventory_quick", True)))

    report_path = REPO / str(sync_cfg.get("report_path") or "data_lake/collection/_index/migration/partition_sync_latest.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    report["report_path"] = str(report_path.relative_to(REPO))

    if args.update_partition_status and synced_ids and not args.dry_run:
        if update_partition_drive_status(partitions_cfg, synced_ids):
            PARTITIONS_PATH.write_text(json.dumps(partitions_cfg, indent=2) + "\n", encoding="utf-8")
            report["partitions_updated"] = True

    if args.pretty:
        s = report["summary"]
        print(f"Partition sync — ok={s['ok']} skipped={s['skipped']} failed={s['failed']} optional_missing={s['optional_missing']}")
        print(f"Report: {report['report_path']}")
        for row in report["jobs"]:
            st = row.get("status", "?")
            jid = row.get("job_id", "")
            if st in {"ok", "dry_run"}:
                print(f"  [{st}] {jid} → {row.get('remote_suffix') or row.get('reason', '')}")
            elif st == "failed":
                print(f"  [FAILED] {jid}: {row.get('rclone', {}).get('stage')} {row.get('rclone', {}).get('stderr', '')[:120]}")
            else:
                print(f"  [{st}] {jid}: {row.get('reason', '')}")
    else:
        print(json.dumps(report, indent=2))

    return 1 if report["summary"]["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
