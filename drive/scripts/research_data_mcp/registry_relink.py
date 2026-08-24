#!/usr/bin/env python3
"""Reconnect registry rows to bytes the desk already holds.

A dataset can be registered, its bytes present on disk, and still unreadable
because the registry row carries no ``local_path``.  That is not a missing
dataset — it is a broken link, and it reports as ``local_bytes_missing`` which
reads like an acquisition problem.

Seven Refinitiv datasets were in that state: their parquet files sat in
``data_lake/refinitiv_backfill`` (a symlink to bulk storage) under names that
drop the ``refinitiv_`` prefix, so nothing resolved them.

This only ever *adds* a ``local_path`` to a row that has none, and only when the
file is actually there.  It never edits an existing path, never removes a row,
and never invents a location.

    python3 -m scripts.research_data_mcp.registry_relink            # report only
    python3 -m scripts.research_data_mcp.registry_relink --apply    # write
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

# Snapshot preference: the most complete backfill wins when several carry a file.
SNAPSHOTS = (
    "2026-07-06-complete",
    "2026-07-06-value-v2",
    "2026-07-06-value",
    "2026-07-06-fundamentals",
    "2026-07-06-scale",
    "2026-07-06",
)
BACKFILL = "data_lake/refinitiv_backfill"


def _stems(dataset_id: str) -> list[str]:
    """Names a backfill file might carry for this dataset."""
    out = [dataset_id]
    if dataset_id.startswith("refinitiv_"):
        out.append(dataset_id[len("refinitiv_") :])
    return out


def locate(data_root: Path, dataset_id: str) -> str | None:
    for snapshot in SNAPSHOTS:
        for stem in _stems(dataset_id):
            rel = f"{BACKFILL}/{snapshot}/processed/{stem}.parquet"
            if (data_root / rel).is_file():
                return rel
    return None


def plan(registry: dict[str, Any], data_root: Path) -> list[tuple[str, str]]:
    datasets = registry.get("datasets") or {}
    rows = datasets.values() if isinstance(datasets, dict) else datasets
    found: list[tuple[str, str]] = []
    for row in rows:
        dataset_id = str(row.get("dataset_id") or "")
        if not dataset_id or row.get("local_path"):
            continue
        rel = locate(data_root, dataset_id)
        if rel:
            found.append((dataset_id, rel))
    return found


def apply(registry: dict[str, Any], links: list[tuple[str, str]]) -> int:
    datasets = registry.get("datasets") or {}
    rows = list(datasets.values()) if isinstance(datasets, dict) else datasets
    by_id = {str(r.get("dataset_id")): r for r in rows}
    changed = 0
    for dataset_id, rel in links:
        row = by_id.get(dataset_id)
        if row is not None and not row.get("local_path"):
            row["local_path"] = rel
            changed += 1
    return changed


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--registry", required=True)
    ap.add_argument("--data-root", default=os.environ.get("RESEARCH_DATA_ROOTS", "."))
    ap.add_argument("--apply", action="store_true", help="write the links (default: report only)")
    args = ap.parse_args(argv)

    registry_path = Path(args.registry).resolve()
    data_root = Path(str(args.data_root).split(os.pathsep)[0]).resolve()
    registry = json.loads(registry_path.read_text(encoding="utf-8"))

    links = plan(registry, data_root)
    for dataset_id, rel in links:
        print(f"relink {dataset_id} -> {rel}")
    if not links:
        print("no registry row is missing a local_path it could resolve")
        return 0
    if not args.apply:
        print(f"{len(links)} row(s) resolvable; re-run with --apply to write")
        return 0

    backup = registry_path.with_suffix(registry_path.suffix + ".before-relink")
    if not backup.exists():
        backup.write_text(registry_path.read_text(encoding="utf-8"), encoding="utf-8")
    changed = apply(registry, links)
    registry_path.write_text(json.dumps(registry, indent=2), encoding="utf-8")
    print(f"wrote {changed} link(s); prior registry kept at {backup.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
