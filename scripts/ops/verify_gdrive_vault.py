#!/usr/bin/env python3
"""Verify GDrive vault is Promise-1 ready: one collection/ tree, no stray legacy roots."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PARTITIONS_PATH = REPO / "config/collection_partitions.json"

ALLOWED_ROOT = {
    "collection",
    "datacite_catalog",  # operator backend (sibling tree; not professor-facing)
    "START_HERE.md",
    "PARTITION_MAP.json",
    "README.md",
}


def _lsd(remote: str) -> list[str]:
    proc = subprocess.run(
        ["rclone", "lsf", remote, "--dirs-only", "--max-depth", "1"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if proc.returncode != 0:
        return []
    return sorted(x.strip().rstrip("/") for x in proc.stdout.splitlines() if x.strip())


def main() -> int:
    cfg = json.loads(PARTITIONS_PATH.read_text(encoding="utf-8"))
    vault = str(cfg["canonical_root"]).rstrip("/")
    roots = _lsd(vault)
    legacy = [r for r in roots if r not in ALLOWED_ROOT and not r.endswith(".md") and not r.endswith(".json")]

    coll = _lsd(f"{vault}/collection")
    domains = set(coll)

    print(f"Vault: {vault}")
    print(f"Root entries: {len(roots)}")
    print(f"collection/ domains: {', '.join(coll) or '(empty)'}")

    try:
        link_proc = subprocess.run(
            ["rclone", "link", f"{vault}/collection"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if link_proc.returncode == 0 and link_proc.stdout.strip():
            print(f"\nProfessor link (collection/): {link_proc.stdout.strip()}")
        link_root = subprocess.run(
            ["rclone", "link", vault],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if link_root.returncode == 0 and link_root.stdout.strip():
            print(f"Vault root link: {link_root.stdout.strip()}")
    except Exception as exc:
        print(f"(rclone link failed: {exc})", file=sys.stderr)

    ok = not legacy and bool(coll)
    core = {"markets", "official", "reference", "acquired", "derived"}
    professor_ready = core.issubset(set(coll))
    if professor_ready:
        print("\nProfessor core domains present under collection/ (share collection/ link).")
    if legacy:
        print(f"\nLEGACY ROOT FOLDERS STILL PRESENT ({len(legacy)}):")
        for name in legacy:
            print(f"  - {name}")
        print("\nRun: python3 scripts/ops/migrate_gdrive_collection_layout.py --all")
    else:
        print("\nOK: no legacy root folders — Promise 1 vault layout ready.")

    expected_domains = {"markets", "news", "official", "reference", "social", "catalog", "acquired", "derived", "ops"}
    missing = expected_domains - domains
    if missing:
        print(f"Note: collection/ missing domains (may be empty): {', '.join(sorted(missing))}")

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
