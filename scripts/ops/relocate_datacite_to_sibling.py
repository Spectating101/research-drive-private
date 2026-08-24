#!/usr/bin/env python3
"""Move DataCite harvest out of collection/ → sibling datacite_catalog/ at vault root.

Professor-facing tree stays clean; backend bulk is not under collection/.

WARNING: rclone move may trigger Google Drive malware re-scans on datacite_*.jsonl.gz.
Default is --dry-run. Use --apply only when ready.

Usage:
  python3 scripts/ops/relocate_datacite_to_sibling.py --dry-run
  python3 scripts/ops/relocate_datacite_to_sibling.py --apply
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PARTITIONS = REPO / "config/collection_partitions.json"

SRC_SUFFIX = "collection/catalog/datacite"
DST_SUFFIX = "datacite_catalog"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry-run", action="store_true", default=True)
    ap.add_argument("--no-dry-run", action="store_true", help="Same as --apply")
    args = ap.parse_args()
    apply = args.apply or args.no_dry_run

    cfg = json.loads(PARTITIONS.read_text(encoding="utf-8"))
    vault = str(cfg["canonical_root"]).rstrip("/")
    src = f"{vault}/{SRC_SUFFIX}"
    dst = f"{vault}/{DST_SUFFIX}"

    cmd = ["rclone", "move", src, dst, "--drive-acknowledge-abuse", "-v"]
    if not apply:
        cmd.append("--dry-run")

    print(f"{'APPLY' if apply else 'DRY-RUN'}: {src} → {dst}")
    proc = subprocess.run(cmd, text=True, capture_output=True, timeout=86400)
    if proc.stdout:
        print(proc.stdout[-3000:])
    if proc.returncode != 0:
        print(proc.stderr or proc.stdout, file=sys.stderr)
        return proc.returncode

    if apply:
        for part in cfg.get("partitions") or []:
            if part.get("id") == "catalog.datacite-harvest":
                part["legacy_drive_path"] = "datacite_catalog/harvest/index_v3"
                part["status"] = "migrated"
                break
        PARTITIONS.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
        print("Updated collection_partitions.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
