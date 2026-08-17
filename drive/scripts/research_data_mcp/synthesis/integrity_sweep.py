"""Reconcile what the catalogue claims against what the storage holds.

Two directions, because the failures run both ways.

Registry to bytes: an entry claiming a dataset is available proves nothing about
the file. us_sp500_yfinance_daily is 14MB with valid PAR1 magic at both ends and
a corrupt thrift footer; it was registered and unreadable and nothing knew until
someone opened it.

Bytes to registry: a collection that landed correctly is worthless if no row
points at it. 32 of 33 directories under data_lake/procured — 18MB of SEC EDGAR
filings, Taiwan exchange feeds and the Keeling series, content-addressed with
manifests and validation records — were invisible to the desk because acquisition
and cataloguing keep separate books and nothing compared them.

A landing describes itself: CURRENT.json carries the dataset_id it expects, its
revision, file count and content hashes, and the revision manifest carries the
source URL and validation result. So the comparison is exact rather than a guess
from directory names.

States what it observed. It does not register, repair, or delete anything —
deciding that an orphan deserves a catalogue row is the operator's call.
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
# Held, but not addressable as one file. The synthesis resolver refuses a directory
# holding several data files because it must not guess which one a spec meant — the
# right answer for "which file do I read" and the wrong one for "do we hold this".
# Conflating them made this sweep report 38 datasets absent while 4,320 of their
# files sat on disk, gdelt_asia_daily_country_panel among them at 1,415 files.
STATUS_MULTI = "held_not_single_file"


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
        declared = str(source.get("local_path") or source.get("local_root") or "").rstrip("/*")
        if declared:
            from scripts.research_data_mcp.synthesis.dataset_paths import data_roots

            for root in data_roots(repo_root):
                candidate = root / declared
                if not candidate.is_dir():
                    continue
                files = [f for f in candidate.rglob("*") if f.is_file()]
                if files:
                    out["status"] = STATUS_MULTI
                    out["path"] = str(candidate)
                    out["data_files"] = len(files)
                    out["bytes"] = sum(f.stat().st_size for f in files[:2000])
                    out["detail"] = (
                        f"{len(files)} files present; not addressable as a single file, "
                        "so synthesis cannot read it without a local_file"
                    )
                    break
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
        "held_not_single_file": [r for r in results if r["status"] == STATUS_MULTI],
        "corrupt": [r for r in results if r["status"] in (STATUS_UNREADABLE, STATUS_EMPTY)],
    }


def runtime_readiness(repo_root: Path | str) -> dict[str, dict[str, str]]:
    """What the engine tells a caller, after its own start-up reconciliation.

    This sweep resolves through the synthesis path resolver, which answers "which
    single file do I read". The engine answers a different question and has
    dedicated handlers for partitioned directories, so a dataset this sweep calls
    held_not_single_file may still serve rows. Reporting the sweep's status alone
    overstates breakage: of 40 such datasets, 38 are already downgraded by the
    engine with a reason and 2 (the GDELT panels) query fine.
    """
    try:
        from scripts.research_query_engine.engine import ResearchQueryEngine

        engine = ResearchQueryEngine(repo_root=Path(repo_root))
    except Exception:
        return {}
    rows = engine.datasets
    rows = list(rows.values()) if isinstance(rows, dict) else list(rows or [])
    out: dict[str, dict[str, str]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        out[str(row.get("dataset_id") or "")] = {
            "readiness": str(row.get("analysis_readiness") or ""),
            "reason": str(row.get("runtime_readiness_reason") or ""),
        }
    return out


SERVING_READINESS = {"instant", "query_ready"}

LANDING_ROOTS = ("data_lake/procured", "data_lake/spectator_engine/scrapes")
STATUS_ORPHAN = "landed_unregistered"
STATUS_PHANTOM = "registered_absent"


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def landings(repo_root: Path | str, *, roots: tuple[str, ...] = LANDING_ROOTS) -> list[dict[str, Any]]:
    """Every collection that reached storage, as the landing itself describes it."""
    repo_root = Path(repo_root).resolve()
    found: list[dict[str, Any]] = []
    for rel in roots:
        base = repo_root / rel
        if not base.is_dir():
            continue
        for entry in sorted(base.iterdir()):
            if not entry.is_dir():
                continue
            current = _read_json(entry / "CURRENT.json")
            manifest = _read_json(entry / "manifest.json")
            if not manifest:
                revisions = sorted((entry / "revisions").glob("*/manifest.json")) if (entry / "revisions").is_dir() else []
                manifest = _read_json(revisions[-1]) if revisions else {}
            plan = manifest.get("plan") or {}
            validation = manifest.get("validation") or {}
            data_files = [
                f for f in entry.rglob("*")
                if f.is_file() and f.suffix.lower() in {".csv", ".json", ".jsonl", ".parquet", ".xpt", ""}
                and f.name not in {"CURRENT.json", "manifest.json"}
            ]
            found.append({
                "declared_dataset_id": str(current.get("dataset_id") or entry.name),
                "directory": str(entry.relative_to(repo_root)),
                "revision": str(current.get("revision_id") or ""),
                "job_id": str(current.get("job_id") or manifest.get("job_id") or ""),
                "updated_at": str(current.get("updated_at") or manifest.get("created_at") or ""),
                "source_url": str(plan.get("url") or ""),
                "job_type": str(plan.get("job_type") or ""),
                "validated": bool(validation.get("ok")) if validation else None,
                "data_files": len(data_files),
                "bytes": sum(f.stat().st_size for f in data_files if f.exists()),
                "content_sha256": list(current.get("content_sha256") or []),
            })
    return found


def reconcile(repo_root: Path | str, *, deep: bool = False) -> dict[str, Any]:
    """Both directions at once: phantoms in the catalogue, orphans in the storage."""
    repo_root = Path(repo_root).resolve()
    forward = sweep(repo_root, deep=deep)
    registered_ids = {str(r["dataset_id"]) for r in forward["results"]}

    landed = landings(repo_root)
    orphans = [item for item in landed
               if item["declared_dataset_id"] not in registered_ids and item["data_files"] > 0]
    phantoms = [r for r in forward["results"] if r["status"] == STATUS_ABSENT]

    runtime = runtime_readiness(repo_root)
    misreported: list[dict[str, Any]] = []
    for item in forward["results"]:
        state = runtime.get(item["dataset_id"])
        if not state:
            continue
        item["engine_readiness"] = state["readiness"]
        item["engine_reason"] = state["reason"]
        serving = state["readiness"] in SERVING_READINESS
        item["engine_serves"] = serving
        # A row still promising a usable dataset over bytes nothing can open is the
        # only case here that misleads a caller; a downgraded row is the engine
        # doing its job, and a served directory is this sweep being too narrow.
        if serving and item["status"] in (STATUS_ABSENT, STATUS_UNREADABLE, STATUS_EMPTY):
            misreported.append(item)

    return {
        "runtime_checked": bool(runtime),
        "engine_serves": sum(1 for r in forward["results"] if r.get("engine_serves")),
        "engine_downgraded": sum(
            1 for r in forward["results"]
            if r.get("engine_readiness") and not r.get("engine_serves")),
        "misreported": misreported,
        "registered": forward["registered"],
        "counts": forward["counts"],
        "readable_rows": forward["readable_rows"],
        "readable_bytes": forward["readable_bytes"],
        "landings": len(landed),
        "orphans": orphans,
        "orphan_bytes": sum(o["bytes"] for o in orphans),
        "phantoms": phantoms,
        "corrupt": forward["corrupt"],
        "results": forward["results"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Open every registered dataset and report what is there.")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--deep", action="store_true", help="scan every row, not just the header")
    parser.add_argument("--json", action="store_true", help="emit the full result as json")
    parser.add_argument("--only", nargs="*", help="limit to these dataset ids")
    parser.add_argument("--reconcile", action="store_true",
                        help="also walk storage and report landings with no catalogue row")
    args = parser.parse_args(argv)

    if args.reconcile:
        report = reconcile(Path(args.repo_root), deep=args.deep)
        if args.json:
            print(json.dumps(report, indent=1, default=str))
            return 1 if (report["corrupt"] or report["orphans"] or report.get("misreported")) else 0
        counts = report["counts"]
        print(f"registered {report['registered']}  ·  landings on disk {report['landings']}")
        for status in (STATUS_READABLE, STATUS_MULTI, STATUS_ABSENT, STATUS_UNREADABLE, STATUS_EMPTY):
            if counts.get(status):
                print(f"  {status:<11} {counts[status]}")
        print(f"  {'rows':<11} {report['readable_rows']:,} across {report['readable_bytes'] / 1e6:.1f} MB")
        if report.get("runtime_checked"):
            print(f"\nwhat the engine actually tells a caller — {report['engine_serves']} served, "
                  f"{report['engine_downgraded']} downgraded with a reason.")
            print("  a status above is this sweep's single-file resolver, not the engine's answer;")
            print("  only the rows below promise data that cannot be opened.")
            if report["misreported"]:
                for item in report["misreported"]:
                    print(f"  MISREPORTED {item['dataset_id'][:38]:<38} engine={item['engine_readiness']:<10} "
                          f"bytes={item['status']}")
            else:
                print("  none — every serving row has bytes behind it.")
        if report["orphans"]:
            print(f"\nheld but not in the catalogue — {len(report['orphans'])} landings, "
                  f"{report['orphan_bytes'] / 1e6:.1f} MB, invisible to the desk:")
            for item in sorted(report["orphans"], key=lambda x: -x["bytes"]):
                print(f"  {item['declared_dataset_id'][:44]:<44} {item['data_files']:>3} files "
                      f"{item['bytes'] / 1e3:>9.1f} KB  {item['source_url'][:38]}")
        if report["phantoms"]:
            print(f"\nin the catalogue with nothing behind it — {len(report['phantoms'])}:")
            for item in report["phantoms"][:12]:
                print(f"  {item['dataset_id'][:44]:<44} {str(item['detail'])[:58]}")
        if report["corrupt"]:
            print(f"\npresent but unusable — {len(report['corrupt'])}:")
            for item in report["corrupt"]:
                print(f"  {item['dataset_id'][:44]:<44} {item['status']:<10} {str(item['detail'])[:44]}")
        return 1 if (report["corrupt"] or report["orphans"] or report.get("misreported")) else 0

    report = sweep(Path(args.repo_root), deep=args.deep, only=args.only)
    if args.json:
        print(json.dumps(report, indent=1, default=str))
        return 1 if report["corrupt"] else 0

    counts = report["counts"]
    print(f"registered {report['registered']}")
    for status in (STATUS_READABLE, STATUS_MULTI, STATUS_ABSENT, STATUS_UNREADABLE, STATUS_EMPTY):
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
