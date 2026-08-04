#!/usr/bin/env python3
"""Seed the curated catalog and topic index from the registry the desk already holds.

The flywheel is reactive by design: ``promote_after_collect`` fires only when a
collect job completes *and* promotes a registry dataset.  That is correct for
newly acquired data, but it cannot enumerate anything the desk acquired before
auto-promotion existed, or acquired by a route that never ran as a job.

Measured consequence: ``curated_live`` held 2 files and the ``curated_fts``
topic index held **0 rows**, built over a registry of 163 datasets of which 100
are query-verified.  Topic and category search were therefore dead -- not
degraded, dead -- while the underlying data sat on disk.  ``flywheel_backfill``
is the existing hand-crank, but it only knows the pipelines listed in
``procurement_registry_map.json`` (two of them), so it cannot close this gap.

This seeds from the registry itself, which is the desk's own record of what it
holds, reusing the flywheel's own row builder and writers rather than opening a
second path into the catalog.  Re-running is safe: ``append_curated_row`` keys
rows and skips duplicates, so this converges rather than accumulating.

It deliberately does *not* invent metadata.  A dataset with no usable title is
skipped rather than given a placeholder, because a curated row exists to be
searched, and an unsearchable row that merely raises the count is worse than an
absent one.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def seed(
    repo_root: Path,
    registry_path: Path | None = None,
    *,
    dry_run: bool = False,
    visible_only: bool = True,
) -> dict[str, Any]:
    """Append a curated row per registry dataset, then rebuild the topic index."""
    from scripts.research_data_mcp.collection_flywheel import CollectionFlywheel

    root = Path(repo_root).resolve()
    registry = Path(registry_path) if registry_path else root / "config/research_query_registry.json"
    doc = json.loads(registry.read_text(encoding="utf-8"))
    rows = [r for r in (doc.get("datasets") or []) if isinstance(r, dict)]
    if visible_only:
        # The catalog is a faculty-facing surface; internal ops rows would add
        # noise to every search without ever being a usable answer.
        rows = [r for r in rows if r.get("professor_visible")]

    wheel = CollectionFlywheel(root, registry)
    added = skipped_dupe = skipped_thin = 0
    for row in rows:
        curated = wheel._curated_row_from_sources(
            registry_row=row, job={}, promoted={}, search_goal="", campaign_id=""
        )
        if not curated:
            skipped_thin += 1
            continue
        if dry_run:
            added += 1
            continue
        if wheel.append_curated_row(curated):
            added += 1
        else:
            skipped_dupe += 1

    index: dict[str, Any] | None = None
    if not dry_run and added:
        index = wheel.rebuild_search_index()

    return {
        "registry": str(registry),
        "considered": len(rows),
        "curated_added": added,
        "skipped_already_present": skipped_dupe,
        "skipped_no_title": skipped_thin,
        "dry_run": dry_run,
        "index": index,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo-root", type=Path, default=Path.cwd())
    ap.add_argument("--registry", type=Path)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--all-datasets", action="store_true",
                    help="Include rows not marked professor_visible.")
    args = ap.parse_args(argv)
    out = seed(args.repo_root, args.registry, dry_run=args.dry_run,
               visible_only=not args.all_datasets)
    print(json.dumps(out, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
