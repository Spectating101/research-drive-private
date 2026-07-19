#!/usr/bin/env python3
"""Build SQLite FTS collection index for fast procurement chat search."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from sharpe_kernel.paths import repo_root_from_file

REPO = repo_root_from_file(__file__)
sys.path.insert(0, str(REPO))

from scripts.research_data_mcp.collection_index import build_index, search_index  # noqa: E402


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--query", default="", help="Optional test search after build")
    ap.add_argument("--limit", type=int, default=6)
    args = ap.parse_args()

    stats = build_index(REPO)
    print(json.dumps(stats, indent=2))
    if args.query.strip():
        hits = search_index(REPO, args.query, limit=args.limit)
        for i, hit in enumerate(hits, 1):
            print(f"#{i} [{hit.get('action_label')}] {hit.get('chat_line')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
