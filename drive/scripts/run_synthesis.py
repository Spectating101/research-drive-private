#!/usr/bin/env python3
"""CLI for multi-source dataset synthesis (backend)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
for _p in (_REPO, _REPO / "kernel", _REPO / "drive"):
    _s = str(_p)
    if _s not in sys.path:
        sys.path.insert(0, _s)

from sharpe_kernel.paths import repo_root_from_file

from scripts.research_data_mcp.bootstrap import create_stack
from scripts.research_data_mcp.synthesis.engine import (
    get_latest_synthesis,
    list_synthesis_profiles,
    run_synthesis,
    run_synthesis_pair,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="List synthesis profiles")

    run_p = sub.add_parser("run", help="Run a synthesis profile")
    run_p.add_argument("profile_id", help="Profile id from config/synthesis_profiles.json")
    run_p.add_argument("--preview-limit", type=int, default=50)
    run_p.add_argument("--gap-limit", type=int, default=100)

    latest_p = sub.add_parser("latest", help="Show latest run for a profile")
    latest_p.add_argument("profile_id")

    pair_p = sub.add_parser("pair", help="Registry metadata pair synthesis")
    pair_p.add_argument("left_dataset_id")
    pair_p.add_argument("right_dataset_id")

    args = parser.parse_args()
    repo = repo_root_from_file(__file__)

    if args.cmd == "list":
        print(json.dumps(list_synthesis_profiles(repo), indent=2))
        return 0

    if args.cmd == "latest":
        hit = get_latest_synthesis(repo, args.profile_id)
        if not hit:
            print(json.dumps({"found": False, "profile_id": args.profile_id}, indent=2))
            return 1
        print(json.dumps(hit, indent=2, default=str))
        return 0

    if args.cmd == "run":
        result = run_synthesis(
            repo,
            args.profile_id,
            preview_limit=args.preview_limit,
            gap_limit=args.gap_limit,
        )
        print(json.dumps(result, indent=2, default=str))
        return 0

    if args.cmd == "pair":
        stack = create_stack(repo)
        result = run_synthesis_pair(
            repo,
            args.left_dataset_id,
            args.right_dataset_id,
            describe_fn=stack.gateway.describe_dataset,
        )
        print(json.dumps(result, indent=2, default=str))
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
