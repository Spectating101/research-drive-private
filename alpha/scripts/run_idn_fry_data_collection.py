#!/usr/bin/env python3
"""Collect self-serve fry research data lanes (structural, attention, broker, reddit).

Examples:
  python scripts/run_idn_fry_data_collection.py --lane all
  python scripts/run_idn_fry_data_collection.py --lane structural --max-live-calls 100
  python scripts/run_idn_fry_data_collection.py --lane broker --broker-max-calls 50
  python scripts/run_idn_fry_data_collection.py --lane all --cache-only
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import importlib.util as _ilu
from pathlib import Path as _Path

_bspec = _ilu.spec_from_file_location("sr_bootstrap", _Path(__file__).resolve().parent / "_repo_bootstrap.py")
_bmod = _ilu.module_from_spec(_bspec)
_bspec.loader.exec_module(_bmod)
REPO = _bmod.repo_root_from_file(__file__)
sys.path.insert(0, str(REPO / "scripts"))

from idn_fry_data_collection_lib import (  # noqa: E402
    build_attention_panel,
    build_collection_manifest,
    collect_reddit_fry_mentions,
    collect_structural_panel,
    collect_technical_symbol_panel,
    collect_technical_trigger_panel,
    enrich_structural_from_emiten_cache,
    load_fry_symbols,
    load_structural_panel,
    merge_structural_into_triggers,
    refresh_broker_queue,
    run_all_lanes,
    run_broker_backfill,
    symbols_missing_structural,
)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--lane",
        choices=("structural", "attention", "technical", "technical_triggers", "enrich", "broker", "reddit", "merge", "all"),
        default="all",
    )
    ap.add_argument("--max-live-calls", type=int, default=450, help="RapidAPI budget for structural lanes")
    ap.add_argument("--broker-max-calls", type=int, default=200)
    ap.add_argument("--broker-delay", type=float, default=3.5)
    ap.add_argument("--cache-only", action="store_true", help="No live RapidAPI/broker calls; disk cache only")
    ap.add_argument("--skip-broker", action="store_true")
    ap.add_argument("--skip-reddit", action="store_true", default=True)
    ap.add_argument("--reddit", action="store_true", help="Enable Reddit lane (needs OAuth)")
    ap.add_argument("--missing-only", action="store_true", help="Structural/technical: only gaps or failed rows")
    args = ap.parse_args()
    cache_only = args.cache_only
    skip_reddit = not args.reddit

    symbols = load_fry_symbols()
    if args.missing_only:
        symbols = symbols_missing_structural(load_structural_panel())
        if not symbols:
            print(json.dumps({"coverage": {"structural_complete": True}, "n_missing": 0}, indent=2))
            return 0
        print(f"Missing structural: {len(symbols)} symbols", file=sys.stderr)
    if not symbols:
        print("No fry symbols — run run_idn_fry_episode_research.py first", file=sys.stderr)
        return 2

    results: dict = {"lane": args.lane, "n_symbols": len(symbols)}

    if args.lane == "all":
        results = run_all_lanes(
            max_live_calls=args.max_live_calls,
            broker_max_calls=args.broker_max_calls,
            broker_delay=args.broker_delay,
            skip_broker=args.skip_broker,
            skip_reddit=skip_reddit,
            cache_only=args.cache_only,
            symbols=symbols if args.missing_only else None,
        )
        print(json.dumps({"manifest": results.get("manifest", {}).get("coverage"), "lanes": list(results.keys())}, indent=2))
        return 0

    if args.lane == "structural":
        _, stats = collect_structural_panel(
            symbols,
            max_live_calls=0 if cache_only else args.max_live_calls,
            use_cache=True,
        )
        results["structural"] = stats
        merge_structural_into_triggers()
    elif args.lane == "attention":
        _, stats = build_attention_panel()
        results["attention"] = stats
    elif args.lane == "enrich":
        _, stats = enrich_structural_from_emiten_cache()
        results["enrich"] = stats
    elif args.lane == "technical":
        _, stats = collect_technical_symbol_panel(
            max_live_calls=0 if cache_only else args.max_live_calls,
            only_missing=args.missing_only,
        )
        results["technical"] = stats
    elif args.lane == "technical_triggers":
        _, stats = collect_technical_trigger_panel(max_live_calls=0 if cache_only else min(args.max_live_calls, 30))
        results["technical_triggers"] = stats
    elif args.lane == "broker":
        queue = refresh_broker_queue()
        results["broker_queue"] = {"pending": len(queue)}
        if not args.cache_only and not args.skip_broker:
            results["broker_backfill"] = run_broker_backfill(
                max_calls=args.broker_max_calls,
                delay=args.broker_delay,
            )
    elif args.lane == "reddit":
        _, stats = collect_reddit_fry_mentions(symbols)
        results["reddit"] = stats
    elif args.lane == "merge":
        merged = merge_structural_into_triggers()
        results["merge"] = {"n_triggers": len(merged)}

    manifest = build_collection_manifest(results)
    print(json.dumps({"coverage": manifest["coverage"], "outputs": manifest["outputs"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
