#!/usr/bin/env python3
"""One report saying what state every registry row is actually in.

Headline counts kept disagreeing because they answered different questions: serving rows,
resolving to one file for synthesis, and doing both are three different things. Collapsing
the remainder into "mostly metadata-only" hid absent paths, ambiguous directories,
operational status endpoints and remote APIs as one category.

Quote this report, never a figure copied out of a docstring — a hardcoded number here went
stale within a day and became the contradiction it was written to prevent.

    python -m scripts.research_query_engine.library_classification [--json]

Needs RESEARCH_DATA_ROOTS; without it almost everything reads as absent.
"""

from __future__ import annotations

import argparse
import json
import signal
from pathlib import Path
from typing import Any

STATES = (
    "queryable",          # engine returns rows AND synthesis can address one file
    "engine_only",        # engine returns rows, synthesis cannot address it
    "synthesis_only",     # synthesis can address a file, engine returns nothing
    "remote_queryable",   # serves rows from a live API, no local bytes to address
    "operational",        # a status/ops endpoint, not a research dataset
    "ambiguous",          # bytes present, multiple files, no local_file named
    "absent",             # no bytes under any configured data root
    "unreadable",         # bytes present but the reader fails on them
    "metadata_only",      # declares no local path and serves nothing
)

# Status and manifest endpoints. They answer "how is the desk doing", not a research
# question, so counting them as datasets overstates the Library either way.
OPERATIONAL_BACKENDS = frozenset({
    "collection_ops_status",
    "datacite_local_harvest_status",
    "ops_json_manifest",
    "ops_json",
})
TIMEOUT_SECONDS = 25


class _Timeout(Exception):
    pass


def _alarm(_sig, _frm):
    raise _Timeout()


def classify(repo_root: Path | str = ".") -> dict[str, Any]:
    from scripts.research_data_mcp.synthesis.dataset_paths import resolve_dataset_file
    from scripts.research_query_engine.engine import ResearchQueryEngine

    root = Path(repo_root).resolve()
    engine = ResearchQueryEngine(repo_root=root)
    signal.signal(signal.SIGALRM, _alarm)

    rows: list[dict[str, Any]] = []
    for spec in engine.list_datasets():
        dataset_id = str(spec.get("dataset_id") or "")
        declared = str(spec.get("local_path") or spec.get("local_root") or "").strip()
        served, err = 0, ""
        signal.alarm(TIMEOUT_SECONDS)
        try:
            result = engine.query(dataset_id, limit=3)
            served = len(result.rows or [])
            err = str((result.meta or {}).get("error") or "")
        except _Timeout:
            err = f"timeout>{TIMEOUT_SECONDS}s"
        except Exception as exc:
            err = f"{type(exc).__name__}: {exc}"
        finally:
            signal.alarm(0)

        path, resolve_err = resolve_dataset_file(root, spec)
        reason = str(resolve_err or "")
        addressable = path is not None

        backend = str(spec.get("backend") or "")
        if backend in OPERATIONAL_BACKENDS:
            # Classified by what it is, before anything about paths.
            state = "operational"
        elif not declared:
            # A live API serves without local bytes; that is not missing metadata.
            state = "remote_queryable" if served else "metadata_only"
        elif served and addressable:
            state = "queryable"
        elif served:
            state = "ambiguous" if "refusing to guess" in reason else "engine_only"
        elif addressable:
            state = "synthesis_only"
        elif "unreadable" in err.lower() or "OSError" in err or "not open" in err.lower():
            state = "unreadable"
        elif "refusing to guess" in reason:
            state = "ambiguous"
        else:
            state = "absent"

        rows.append({
            "dataset_id": dataset_id,
            "state": state,
            "backend": backend,
            "served_rows": served,
            "synthesis_addressable": addressable,
            "declared": declared,
            "error": err[:160],
            "resolve_reason": reason[:160],
        })

    counts = {state: sum(1 for r in rows if r["state"] == state) for state in STATES}
    return {
        "registry_rows": len(rows),
        "counts": counts,
        "end_to_end_capable": counts["queryable"],
        "engine_serves_total": sum(1 for r in rows if r["served_rows"] > 0),
        "synthesis_addressable_total": sum(1 for r in rows if r["synthesis_addressable"]),
        "results": rows,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo-root", default=".")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--state", default="", help="list dataset ids in one state")
    args = ap.parse_args(argv)
    report = classify(args.repo_root)
    if args.json:
        print(json.dumps(report, indent=2))
        return 0
    if args.state:
        for row in report["results"]:
            if row["state"] == args.state:
                print(f"  {row['dataset_id']:<46}{row['resolve_reason'][:70] or row['error'][:70]}")
        return 0
    print(f"registry rows {report['registry_rows']}")
    for state in STATES:
        print(f"  {state:<16}{report['counts'][state]:>5}")
    print(f"\n  engine serves rows          {report['engine_serves_total']}")
    print(f"  synthesis can address a file {report['synthesis_addressable_total']}")
    print(f"  END TO END capable           {report['end_to_end_capable']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
