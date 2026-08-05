"""Record how big each registered dataset actually is.

Discover rows could say what a dataset was about but not how much of it there
was, so a 412-row probe snapshot and a 15M-row panel looked identical. Every
comparable product states size; the registry recorded none.

This measures only what the filesystem reports -- bytes on disk and file count
at the dataset's resolved path -- and writes it under ``materialization.scale``
with the time it was taken. Nothing is estimated: a dataset whose path is not
reachable gets no scale block, and the UI says so rather than guessing.

Row counts are deliberately NOT computed here. Counting rows means parsing
every file in a 17GB lake, and a wrong or stale row count is worse than an
absent one.

Usage:
    python3 -m scripts.research_data_mcp.dataset_scale_probe [--dry-run] [--limit N]
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REGISTRY_REL = "config/research_query_registry.json"

# A dataset directory can hold tens of thousands of files. Stop well before
# that and mark the result partial rather than stalling the probe.
MAX_FILES_WALKED = 20_000


def _resolved_path(row: dict[str, Any]) -> Path | None:
    """The path that belongs to *this* dataset.

    `resolved_root` and `local_root` are shared directories -- several
    datasets are materialized from the same tree. Measuring those credited
    every sibling with the whole directory: two GDELT datasets each reported
    265GB across 1415 files, which is not a size, it is the lake. Only
    dataset-specific paths are measured.
    """
    mat = row.get("materialization") or {}
    for value in (mat.get("resolved_path"), row.get("local_file"), row.get("local_path")):
        text = str(value or "").strip()
        if text:
            return Path(text)
    return None


def measure(path: Path) -> dict[str, Any] | None:
    """Bytes and file count at ``path``; None when it is not reachable."""
    try:
        if not path.exists():
            return None
        if path.is_file():
            return {"size_bytes": path.stat().st_size, "file_count": 1, "partial": False}
    except OSError:
        return None

    total = 0
    files = 0
    partial = False
    try:
        for entry in path.rglob("*"):
            if files >= MAX_FILES_WALKED:
                partial = True
                break
            try:
                if entry.is_file():
                    total += entry.stat().st_size
                    files += 1
            except OSError:
                continue
    except OSError:
        return None

    if not files:
        return None
    return {"size_bytes": total, "file_count": files, "partial": partial}


def run(repo_root: Path, *, dry_run: bool = False, limit: int = 0) -> dict[str, Any]:
    registry_path = (repo_root / REGISTRY_REL).resolve()
    doc = json.loads(registry_path.read_text(encoding="utf-8"))
    rows = doc if isinstance(doc, list) else (doc.get("datasets") or doc.get("rows") or [])

    measured = 0
    unreachable = 0
    shared = 0
    now = datetime.now(timezone.utc).isoformat()

    # A path used by more than one dataset cannot be attributed to either.
    usage: dict[str, int] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        path = _resolved_path(row)
        if path is not None:
            usage[str(path)] = usage.get(str(path), 0) + 1

    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        # Clear any previous measurement so a path that has become shared or
        # unreachable stops reporting a stale size.
        mat_existing = row.get("materialization")
        if isinstance(mat_existing, dict):
            mat_existing.pop("scale", None)
        if limit and measured + unreachable >= limit:
            break
        path = _resolved_path(row)
        if path is None:
            unreachable += 1
            continue
        if usage.get(str(path), 0) > 1:
            shared += 1
            continue
        stats = measure(path)
        if stats is None:
            unreachable += 1
            continue
        mat = row.setdefault("materialization", {})
        if not isinstance(mat, dict):
            continue
        mat["scale"] = {**stats, "measured_at": now}
        measured += 1

    # Always write when not a dry run: clearing stale/shared measurements is
    # itself a change worth persisting, even if nothing new was measured.
    if not dry_run:
        registry_path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")

    return {
        "registry": str(registry_path),
        "total": len(rows),
        "measured": measured,
        "unreachable": unreachable,
        "shared_path_skipped": shared,
        "written": not dry_run,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    result = run(Path(args.repo_root).resolve(), dry_run=args.dry_run, limit=args.limit)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
