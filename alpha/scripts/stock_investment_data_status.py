#!/usr/bin/env python3
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
ROOT = _bmod.bootstrap_repo_paths(__file__)

from src.research.stock_investment_data import data_surface_snapshot, make_universe_record, universe_from_panel, upsert_universe_registry


def main() -> int:
    parser = argparse.ArgumentParser(description="Stock-investment data facade status and universe registry.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("status")
    c.add_argument("--repo", type=Path, default=ROOT)

    c = sub.add_parser("register-universe")
    c.add_argument("--panel", type=Path, default=ROOT / "data_lake" / "daily_alpha_panel.csv")
    c.add_argument("--registry", type=Path, default=ROOT / "config" / "stock_universe_registry.json")
    c.add_argument("--universe-id", required=True)
    c.add_argument("--source", default="price_panel")
    c.add_argument("--as-of")
    c.add_argument("--notes", default="")

    args = parser.parse_args()
    if args.cmd == "status":
        print(json.dumps(data_surface_snapshot(args.repo), indent=2, sort_keys=True))
    elif args.cmd == "register-universe":
        tickers = universe_from_panel(args.panel, as_of=args.as_of)
        rec = make_universe_record(
            universe_id=args.universe_id,
            tickers=tickers,
            source=args.source,
            as_of=args.as_of,
            notes=args.notes,
        )
        upsert_universe_registry(args.registry, rec)
        print(json.dumps(rec, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
