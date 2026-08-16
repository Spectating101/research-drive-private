"""Open every registered dataset's bytes and report what is actually there.

A registry entry claiming a dataset is available proves nothing about the file.
us_sp500_yfinance_daily is 14MB with valid PAR1 magic at both ends and a corrupt
thrift footer; it was registered and unreadable and nothing knew until someone
opened it. Magic bytes are not a check — only a real read is.

States what it observed. It does not repair, re-register, or delete anything.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from scripts.research_data_mcp.synthesis.dataset_paths import resolve_dataset_file

STATUS_READABLE = "readable"
STATUS_UNREADABLE = "unreadable"
STATUS_ABSENT = "absent"
STATUS_EMPTY = "empty"


def _load_registry(repo_root: Path) -> list[dict[str, Any]]:
    raw = json.loads((repo_root / "drive/config/research_query_registry.json").read_text(encoding="utf-8"))
    rows = raw.get("datasets") if isinstance(raw, dict) else raw
    return list(rows or [])


def check_dataset(repo_root: Path, source: dict[str, Any], *, deep: bool = False) -> dict[str, Any]:
    """Resolve, open and read one dataset. `deep` reads every row, not the header."""
    dataset_id = str(source.get("dataset_id") or "")
    out: dict[str, Any] = {"dataset_id": dataset_id, "status": STATUS_ABSENT,
                           "path": None, "bytes": 0, "rows": None, "columns": None, "detail": None}
    path, reason = resolve_dataset_file(repo_root, source)
    if path is None:
        out["detail"] = reason
        return out

    out["path"] = str(path)
    try:
        out["bytes"] = path.stat().st_size
    except OSError as exc:
        out["detail"] = f"{type(exc).__name__}: {exc}"
        return out

    if out["bytes"] == 0:
        out["status"] = STATUS_EMPTY
        out["detail"] = "file is zero bytes"
        return out

    from scripts.research_data_mcp.synthesis_executor import _read_frame

    try:
        frame = _read_frame(path)
    except Exception as exc:
        out["status"] = STATUS_UNREADABLE
        out["detail"] = f"{type(exc).__name__}: {exc}"[:300]
        return out

    try:
        out["rows"] = int(len(frame))
        out["columns"] = int(len(frame.columns))
    except Exception as exc:
        out["status"] = STATUS_UNREADABLE
        out["detail"] = f"opened but not tabular: {type(exc).__name__}: {exc}"[:300]
        return out

    if out["rows"] == 0:
        out["status"] = STATUS_EMPTY
        out["detail"] = "parsed with zero rows"
        return out

    if deep:
        try:
            frame.notna().sum()
        except Exception as exc:
            out["status"] = STATUS_UNREADABLE
            out["detail"] = f"header read but full scan failed: {type(exc).__name__}: {exc}"[:300]
            return out

    out["status"] = STATUS_READABLE
    return out


def sweep(repo_root: Path, *, deep: bool = False, only: list[str] | None = None) -> dict[str, Any]:
    repo_root = Path(repo_root).resolve()
    rows = _load_registry(repo_root)
    if only:
        wanted = set(only)
        rows = [r for r in rows if str(r.get("dataset_id") or "") in wanted]

    results = [check_dataset(repo_root, row, deep=deep) for row in rows]
    counts: dict[str, int] = {}
    for item in results:
        counts[item["status"]] = counts.get(item["status"], 0) + 1

    return {
        "registered": len(rows),
        "counts": counts,
        "readable_bytes": sum(r["bytes"] for r in results if r["status"] == STATUS_READABLE),
        "readable_rows": sum(r["rows"] or 0 for r in results if r["status"] == STATUS_READABLE),
        "results": results,
        "corrupt": [r for r in results if r["status"] in (STATUS_UNREADABLE, STATUS_EMPTY)],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Open every registered dataset and report what is there.")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--deep", action="store_true", help="scan every row, not just the header")
    parser.add_argument("--json", action="store_true", help="emit the full result as json")
    parser.add_argument("--only", nargs="*", help="limit to these dataset ids")
    args = parser.parse_args(argv)

    report = sweep(Path(args.repo_root), deep=args.deep, only=args.only)
    if args.json:
        print(json.dumps(report, indent=1, default=str))
        return 1 if report["corrupt"] else 0

    counts = report["counts"]
    print(f"registered {report['registered']}")
    for status in (STATUS_READABLE, STATUS_ABSENT, STATUS_UNREADABLE, STATUS_EMPTY):
        if counts.get(status):
            print(f"  {status:<11} {counts[status]}")
    print(f"  {'rows':<11} {report['readable_rows']:,} across {report['readable_bytes'] / 1e6:.1f} MB")
    if report["corrupt"]:
        print("\nregistered but not usable:")
        for item in report["corrupt"]:
            print(f"  {item['dataset_id'][:44]:<44} {item['status']:<10} {str(item['detail'])[:70]}")
    return 1 if report["corrupt"] else 0


if __name__ == "__main__":
    sys.exit(main())
