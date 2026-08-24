#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from research_query_engine.engine import ResearchQueryEngine, parse_kv_args


def main() -> int:
    parser = argparse.ArgumentParser(description="Research data query engine CLI")
    parser.add_argument("--registry", default="config/research_query_registry.json")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("datasets")

    describe = sub.add_parser("describe")
    describe.add_argument("dataset_id")

    search = sub.add_parser("search")
    search.add_argument("--q", default="")
    search.add_argument("--domain", default="")
    search.add_argument("--readiness", default="")
    search.add_argument("--access-mode", default="")
    search.add_argument("--limit", type=int, default=50)

    query = sub.add_parser("query")
    query.add_argument("dataset_id")
    query.add_argument("params", nargs="*", help="key=value query params")

    args = parser.parse_args()
    engine = ResearchQueryEngine(args.registry, repo_root=REPO_ROOT)
    if args.cmd == "datasets":
        payload = {"datasets": engine.list_datasets()}
    elif args.cmd == "describe":
        payload = engine.describe(args.dataset_id)
    elif args.cmd == "search":
        payload = {"datasets": engine.search_datasets(args.q, args.domain, args.readiness, args.access_mode, args.limit)}
    elif args.cmd == "query":
        payload = engine.query(args.dataset_id, **parse_kv_args(args.params)).to_dict()
    else:
        raise RuntimeError(args.cmd)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
