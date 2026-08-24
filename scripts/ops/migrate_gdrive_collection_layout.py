#!/usr/bin/env python3
"""Migrate GDrive vault from scattered legacy folders → collection/{domain}/…

Uses rclone move (same remote = fast server-side rename on Google Drive).
Updates collection_partitions.json after each successful partition.

Usage:
  python3 scripts/ops/migrate_gdrive_collection_layout.py --list
  python3 scripts/ops/migrate_gdrive_collection_layout.py --all --skip-large
  nohup python3 scripts/ops/migrate_gdrive_collection_layout.py --all > migrate.log 2>&1 &
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
PARTITIONS_PATH = REPO / "config/collection_partitions.json"
SCALE_PATH = REPO / "config/collection_scale.json"
LOG_DIR = REPO / "data_lake/collection/_index/migration"

LARGE_IDS = {"news.gdelt-asia", "catalog.datacite-harvest", "catalog.curated-index"}

# Never rclone move/copy — GDrive mass-flags datacite_*.jsonl.gz on re-scan.
DO_NOT_TOUCH_IDS = {"catalog.datacite-harvest"}


def _load_cfg() -> dict[str, Any]:
    return json.loads(PARTITIONS_PATH.read_text(encoding="utf-8"))


def _save_cfg(cfg: dict[str, Any]) -> None:
    PARTITIONS_PATH.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")


def _vault_root(cfg: dict[str, Any]) -> str:
    return str(cfg["canonical_root"]).rstrip("/")


def _build_jobs(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    for part in cfg.get("partitions") or []:
        legacy = part.get("legacy_drive_path")
        target = part.get("target_drive_path")
        if not legacy or not target:
            continue
        if part.get("status") in {"local_only", "migrated"}:
            continue
        if legacy == target:
            continue
        exclude: list[str] = []
        if part["id"] == "catalog.curated-index":
            exclude = ["datacite/**", "**/datacite_*.jsonl.gz", "**/datacite_*.jsonl.gz.partial"]
        jobs.append(
            {
                "id": part["id"],
                "partition_id": part["id"],
                "src": legacy.strip("/"),
                "dst": target.strip("/"),
                "exclude": exclude,
                "title": part.get("title", ""),
            }
        )
    jobs.sort(key=lambda j: (0 if j["id"] == "catalog.datacite-harvest" else 1, j["src"]))
    return jobs


def _run(cmd: list[str], *, timeout: int = 86400) -> subprocess.CompletedProcess[str]:
    print(f"$ {' '.join(cmd)}", flush=True)
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)


def _remote_exists(remote: str) -> bool:
    proc = _run(["rclone", "lsd", remote], timeout=120)
    return proc.returncode == 0 and bool(proc.stdout.strip())


def _cutover_one(cfg: dict[str, Any], partition_id: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    for part in cfg.get("partitions") or []:
        if part["id"] == partition_id:
            target = str(part.get("target_drive_path") or "").strip("/")
            if target:
                part["legacy_drive_path"] = target
                part["migrated_at"] = now
                part["status"] = "migrated"
            break
    _save_cfg(cfg)


def _migrate_one(
    vault: str,
    job: dict[str, Any],
    *,
    dry_run: bool,
) -> dict[str, Any]:
    src = f"{vault}/{job['src']}"
    dst = f"{vault}/{job['dst']}"
    result: dict[str, Any] = {"id": job["id"], "src": src, "dst": dst, "status": "pending"}

    src_exists = _remote_exists(src)
    dst_exists = _remote_exists(dst)

    if not src_exists and dst_exists:
        result["status"] = "already_migrated"
        print(f"SKIP {job['id']}: already at {job['dst']}")
        return result

    if not src_exists:
        result["status"] = "skipped_missing_source"
        print(f"SKIP {job['id']}: source missing {src}")
        return result

    if src_exists and dst_exists:
        # Partial destination (e.g. aborted copy) — finish copy then remove source.
        copy_cmd = [
            "rclone",
            "copy",
            src,
            dst,
            "--checksum",
            "--checkers",
            "16",
            "--transfers",
            "8",
        ]
        for pattern in job.get("exclude") or []:
            copy_cmd.extend(["--exclude", pattern])
        if dry_run:
            copy_cmd.append("--dry-run")
            proc = _run(copy_cmd, timeout=600)
            result["status"] = "dry_run"
            result["returncode"] = proc.returncode
            return result
        proc = _run(copy_cmd)
        if proc.returncode != 0:
            result["status"] = "copy_failed"
            result["stderr"] = (proc.stderr or proc.stdout)[-4000:]
            return result
        purge = _run(["rclone", "purge", src])
        if purge.returncode != 0:
            result["status"] = "purge_failed"
            result["stderr"] = (purge.stderr or purge.stdout)[-4000:]
            return result
        result["status"] = "migrated"
        print(f"OK {job['id']}: merged partial → {job['dst']}, legacy purged")
        return result

    move_cmd = [
        "rclone",
        "move",
        src,
        dst,
        "--checkers",
        "16",
        "--transfers",
        "8",
        "--stats",
        "1m",
        "--stats-one-line",
    ]
    for pattern in job.get("exclude") or []:
        move_cmd.extend(["--exclude", pattern])

    if dry_run:
        move_cmd.append("--dry-run")
        proc = _run(move_cmd, timeout=600)
        result["status"] = "dry_run"
        result["returncode"] = proc.returncode
        return result

    proc = _run(move_cmd)
    if proc.returncode != 0:
        result["status"] = "move_failed"
        result["stderr"] = (proc.stderr or proc.stdout)[-4000:]
        print(result["stderr"], file=sys.stderr)
        return result

    result["status"] = "migrated"
    print(f"OK {job['id']}: {job['src']} → {job['dst']}")
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--partition", help="Migrate one partition (slug or id)")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-large", action="store_true")
    ap.add_argument("--only-large", action="store_true")
    ap.add_argument(
        "--professor-first",
        action="store_true",
        help="Skip DataCite harvest (do not touch jsonl.gz on Drive) and optional large news",
    )
    args = ap.parse_args()

    cfg = _load_cfg()
    vault = _vault_root(cfg)
    jobs = _build_jobs(cfg)

    if args.list:
        for j in jobs:
            ex = f" exclude={j['exclude']}" if j.get("exclude") else ""
            print(f"{j['id']}: {j['src']} → {j['dst']}{ex}")
        return 0

    if args.partition:
        needle = args.partition.lower()
        jobs = [j for j in jobs if needle in j["id"].lower() or needle in j["src"].lower()]
        if not jobs:
            print(f"No job matching {args.partition!r}", file=sys.stderr)
            return 2
    elif not args.all:
        ap.print_help()
        return 2

    if args.skip_large:
        jobs = [j for j in jobs if j["id"] not in LARGE_IDS]
    if args.only_large:
        jobs = [j for j in jobs if j["id"] in LARGE_IDS]
    if args.professor_first:
        jobs = [j for j in jobs if j["id"] not in DO_NOT_TOUCH_IDS]

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []

    for job in jobs:
        print(f"\n=== {job['id']}: {job.get('title', '')} ===")
        res = _migrate_one(vault, job, dry_run=args.dry_run)
        results.append(res)
        if res["status"] in {"migrated", "already_migrated"} and job.get("partition_id") and not args.dry_run:
            cfg = _load_cfg()
            _cutover_one(cfg, job["partition_id"])

    report_path = LOG_DIR / f"migration_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    report_path.write_text(
        json.dumps(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "vault": vault,
                "results": results,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nWrote {report_path.relative_to(REPO)}")

    failed = [r for r in results if r["status"] in {"move_failed"}]
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
