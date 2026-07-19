#!/usr/bin/env python3
"""Build torrent-style collection catalog (swarms, pieces, trackers)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from sharpe_kernel.paths import repo_root_from_file

REPO = repo_root_from_file(__file__)
sys.path.insert(0, str(REPO))

from scripts.research_data_mcp.collection_catalog import build_catalog, catalog_root  # noqa: E402


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--shard", default="", help="Print one swarm JSON")
    args = ap.parse_args()

    stats = build_catalog(REPO)
    print(json.dumps(stats, indent=2))
    if args.shard.strip():
        swarms = json.loads((catalog_root(REPO) / "datacite_swarms.json").read_text(encoding="utf-8"))
        match = next((s for s in swarms.get("swarms") or [] if s.get("shard") == args.shard.strip()), None)
        print(json.dumps(match, indent=2) if match else "not found")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
