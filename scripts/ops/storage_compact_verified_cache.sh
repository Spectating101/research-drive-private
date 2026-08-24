#!/usr/bin/env bash
# Compact large GDELT *staging* files on the USB cache after GDrive verify.
# Canonical copy stays on GDrive; daily panels on cache are kept for local query.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${repo_root}"

exec python3 - "$@" <<'PY'
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1] if False else Path.cwd()
sys.path.insert(0, str(REPO))

from scripts.research_data_mcp.storage_tiers import (  # noqa: E402
    cache_retention_mode,
    canonical_drive_root,
    load_storage_tiers,
)
from scripts.research_data_mcp.data_paths import bulk_storage_root  # noqa: E402

dry_run = os.environ.get("DRY_RUN", "0") == "1"
max_months = int(os.environ.get("MAX_MONTHS", "0") or "0")
status_dir = Path(os.environ.get("STATUS_DIR", "data_lake/news_shock_taxonomy/backfill_status/gkg_backfill_2018_2023"))

cfg = load_storage_tiers(REPO)
remote_root = os.environ.get(
    "REMOTE_ROOT",
    (cfg.get("tiers") or {}).get("canonical", {}).get("gdelt_backfill_root")
    or f"{canonical_drive_root(REPO)}/news_shock_taxonomy/gdelt_gkg_asia_backfill_2018_2023",
)

if bulk_storage_root() is None:
    print("cache_offline skip compact (canonical on GDrive; hydrate cache when needed)")
    sys.exit(0)

if cache_retention_mode(REPO) != "compact_staging_only":
    print(f"retention_mode={cache_retention_mode(REPO)} skip auto compact")
    sys.exit(0)

norm_root = REPO / "data_lake/news_shock_taxonomy/normalized/gdelt_gkg_asia_bulk"
proc_root = REPO / "data_lake/news_shock_taxonomy/processed"


def remote_size(remote_path: str) -> int | None:
    proc = subprocess.run(
        ["rclone", "lsl", remote_path],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    return int(proc.stdout.split()[0])


def compact_run(run_id: str) -> bool:
    local_norm = norm_root / run_id / "asia_gkg_filtered.csv.gz"
    if not local_norm.is_file():
        return True
    remote_norm = f"{remote_root}/normalized/gdelt_gkg_asia_bulk/{run_id}/asia_gkg_filtered.csv.gz"
    local_bytes = local_norm.stat().st_size
    remote_bytes = remote_size(remote_norm)
    if not remote_bytes or remote_bytes != local_bytes:
        print(f"skip_not_verified run_id={run_id} local={local_bytes} remote={remote_bytes}")
        return False
    panel = proc_root / run_id / "daily_country_shock_panel.csv"
    if not panel.is_file():
        print(f"skip_no_panel run_id={run_id}")
        return False
    targets = [
        local_norm,
        proc_root / run_id / "asia_gkg_scored.csv.gz",
        proc_root / run_id / "url_enrichment_queue.csv.gz",
        proc_root / run_id / "url_enrichment_enrich_high_priority.csv.gz",
        proc_root / run_id / "url_enrichment_enrich_high_priority.jsonl.gz",
    ]
    if dry_run:
        print(f"dry_run_compact run_id={run_id} bytes={local_bytes}")
        return True
    for path in targets:
        if path.is_file():
            path.unlink()
    try:
        (norm_root / run_id).rmdir()
    except OSError:
        pass
    print(f"compacted_staging run_id={run_id} bytes={local_bytes}")
    return True


markers = sorted(status_dir.glob("*.ok.json"))
processed = reclaimed = failed = 0
for marker in markers:
    if max_months and processed >= max_months:
        break
    processed += 1
    try:
        payload = json.loads(marker.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        failed += 1
        continue
    if payload.get("status") != "drive_verified":
        continue
    run_id = payload.get("run_id") or marker.stem.replace(".ok", "")
    if compact_run(str(run_id)):
        reclaimed += 1
    else:
        failed += 1

print(json.dumps({"processed": processed, "compacted": reclaimed, "failed": failed, "dry_run": dry_run}))
PY
