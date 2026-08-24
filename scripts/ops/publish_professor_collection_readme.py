#!/usr/bin/env python3
"""Upload professor-facing README to collection/ on GDrive."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "data_lake/collection/_index/gdrive_nav/collection_README.md"
PARTITIONS = REPO / "config/collection_partitions.json"


def main() -> int:
    cfg = json.loads(PARTITIONS.read_text(encoding="utf-8"))
    vault = str(cfg["canonical_root"]).rstrip("/")
    staging = REPO / "data_lake/collection/_index/gdrive_nav/README.md"
    staging.write_text(SRC.read_text(encoding="utf-8"), encoding="utf-8")
    dest = f"{vault}/collection"
    proc = subprocess.run(
        ["rclone", "copyto", str(staging), f"{dest}/README.md", "--drive-acknowledge-abuse"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if proc.returncode != 0:
        print(proc.stderr or proc.stdout, file=sys.stderr)
        return proc.returncode
    link = subprocess.run(["rclone", "link", dest], capture_output=True, text=True, timeout=90)
    if link.returncode == 0 and link.stdout.strip():
        print(f"Professor share link: {link.stdout.strip()}")
    print(f"Uploaded {dest}/README.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
