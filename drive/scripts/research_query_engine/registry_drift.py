#!/usr/bin/env python3
"""Report registry paths the engine had to descend below, so they can be corrected.

The engine reaching held bytes is not the same as the catalogue being right. A silent
compensation makes 31 wrong entries permanent; this names each one and the pattern that
actually served, so the fix is mechanical rather than archaeological.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

GLOB_BACKENDS = {"local_json_glob", "local_csv_glob"}


def scan(repo_root: Path | str = ".", registry: str | Path | None = None) -> dict[str, Any]:
    from scripts.research_query_engine.engine import ResearchQueryEngine

    engine = (
        ResearchQueryEngine(registry_path=registry, repo_root=repo_root)
        if registry
        else ResearchQueryEngine(repo_root=repo_root)
    )
    drifted: list[dict[str, Any]] = []
    exact: list[str] = []
    empty: list[str] = []
    for row in engine.list_datasets():
        if str(row.get("backend") or "") not in GLOB_BACKENDS:
            continue
        dataset_id = str(row.get("dataset_id") or "")
        pattern = str(row.get("local_path") or "")
        if not dataset_id or not pattern:
            continue
        _files, report = engine._resolve_glob(pattern)
        if report["registry_drift"]:
            drifted.append(
                {
                    "dataset_id": dataset_id,
                    "declared": report["declared"],
                    "served_pattern": report["served_pattern"],
                    "suggested_local_path": report["served_relative"],
                    "depth": report["depth"],
                    "files": report["matched"],
                }
            )
        elif report["matched"]:
            exact.append(dataset_id)
        else:
            empty.append(dataset_id)
    drifted.sort(key=lambda r: -r["files"])
    return {
        "glob_datasets": len(drifted) + len(exact) + len(empty),
        "declared_correctly": len(exact),
        "drifted": drifted,
        "no_files_at_any_depth": empty,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--registry", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = scan(args.repo_root, args.registry or None)
    if args.json:
        print(json.dumps(report, indent=2))
        return 0
    print(f"glob datasets        {report['glob_datasets']}")
    print(f"  declared correctly {report['declared_correctly']}")
    print(f"  registry drift     {len(report['drifted'])}")
    print(f"  no files anywhere  {len(report['no_files_at_any_depth'])}")
    if report["drifted"]:
        print("\ncorrect these declarations:")
        for row in report["drifted"]:
            print(f"  {row['files']:>5} files  {row['depth']:<10} {row['dataset_id']}")
            print(f"           {row['declared']}")
            print(f"        -> {row['suggested_local_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
