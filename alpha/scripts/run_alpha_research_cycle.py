#!/usr/bin/env python3
"""Alpha research flywheel step: inventory Drive fuel + emit next supply asks.

Does not edit Drive. Uses kernel local resolve; optionally probes HTTP :8765.
Run repeatedly as Drive supplies new panels; pair with promote gates / live cycle.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import importlib.util as _ilu
from pathlib import Path as _Path

_bspec = _ilu.spec_from_file_location("sr_bootstrap", _Path(__file__).resolve().parent / "_repo_bootstrap.py")
_bmod = _ilu.module_from_spec(_bspec)
_bspec.loader.exec_module(_bmod)
SR_ROOT = _bmod.bootstrap_repo_paths(__file__)

from src.research.drive_fuel import inventory_fuel, write_inventory  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--manifest",
        type=Path,
        default=SR_ROOT / "alpha" / "config" / "alpha_fuel_manifest.json",
    )
    ap.add_argument(
        "--out-dir",
        type=Path,
        default=SR_ROOT / "backtests" / "outputs" / "platform" / "alpha_fuel",
    )
    ap.add_argument("--no-http", action="store_true", help="Skip :8765 probe.")
    ap.add_argument("--query-engine-url", type=str, default=None)
    ap.add_argument("--json", action="store_true", help="Print inventory JSON to stdout.")
    args = ap.parse_args()

    report = inventory_fuel(
        SR_ROOT,
        manifest_path=args.manifest if args.manifest.exists() else None,
        query_engine_url=args.query_engine_url,
        probe_http=not bool(args.no_http),
    )
    report["cycle"] = {
        "name": "alpha_research_fuel_inventory",
        "built_at_utc": datetime.now(timezone.utc).isoformat(),
        "next": (
            "1) Use Drive MCP/API to clear supply_asks "
            "2) Rebuild/join features from ready panels "
            "3) Walk-forward + promote_signal gates "
            "4) On pass → live alpha; on fail → beta_core (not rejected prior)"
        ),
    }
    paths = write_inventory(report, args.out_dir)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(paths["md"].read_text(encoding="utf-8"))
        print(f"\nWrote {paths['json']}")
    # Non-zero if P0 fuel missing — research should notice.
    p0_missing = [
        r
        for r in report.get("datasets") or []
        if r.get("priority") == "P0" and r.get("status") == "missing"
    ]
    return 2 if p0_missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
