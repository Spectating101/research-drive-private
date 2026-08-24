#!/usr/bin/env python3
"""CLI: print three-tier storage status as JSON or text."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from scripts.research_data_mcp.storage_tiers import storage_tiers_status  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pretty", action="store_true")
    args = ap.parse_args()
    payload = storage_tiers_status(REPO)
    if args.pretty:
        c = payload["canonical"]
        h = payload["hot"]
        cache = payload["cache"]
        print(payload.get("architecture", ""))
        print()
        print(f"Canonical: {c['label']} ({c['drive_root']})")
        print(f"Hot desk:  {h['label']} — {h['free_gb']} GB free (min {h['required_min_gb']} GB)")
        if cache.get("mounted"):
            print(f"Cache:     {cache['label']} — {cache['free_gb']} GB free @ {cache['root']}")
        else:
            print(f"Cache:     offline — {cache.get('message', '')}")
    else:
        print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
