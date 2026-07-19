#!/usr/bin/env python3
"""Build master collection dictionary (mini-schema + availability matrix)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from sharpe_kernel.paths import repo_root_from_file

REPO = repo_root_from_file(__file__)
sys.path.insert(0, str(REPO))

from scripts.research_data_mcp.collection_dictionary import write_dictionary  # noqa: E402


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--gaps-only", action="store_true", help="Print only gap rows")
    ap.add_argument("--table", default="", help="Print one table: datacite_shards, partitions, registry_datasets, …")
    args = ap.parse_args()

    payload = write_dictionary(REPO)
    if args.gaps_only:
        print(json.dumps(payload.get("gaps") or [], indent=2))
        return 0
    if args.table.strip():
        rows = (payload.get("tables") or {}).get(args.table.strip()) or []
        print(json.dumps(rows, indent=2))
        return 0

    slim = {
        "output_path": payload.get("output_path"),
        "summary": payload.get("summary"),
        "datacite_shards": [
            {
                "shard": r.get("shard"),
                "action_label": r.get("action_label"),
                "records": r.get("availability", {}).get("records_committed"),
                "on_drive": r.get("availability", {}).get("on_drive"),
                "local_jsonl": r.get("availability", {}).get("on_local_jsonl_bytes"),
                "missing": r.get("availability", {}).get("missing"),
            }
            for r in (payload.get("tables") or {}).get("datacite_shards") or []
        ],
        "gap_count": payload.get("summary", {}).get("gap_count"),
    }
    print(json.dumps(slim, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
