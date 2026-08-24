#!/usr/bin/env python3
"""Catch up IDX legacy SQLite from Yahoo Finance (full ticker list).

Fills the gap after data_lake/markets/idx_legacy_restore/historical_data.db ends
(2025-02-07) through today, then optionally refreshes name types + exports parquet.

Examples:
  python scripts/run_idx_legacy_catchup.py
  python scripts/run_idx_legacy_catchup.py --dry-run
  python scripts/run_idx_legacy_catchup.py --symbols BBCA.JK BBRI.JK --no-export
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from idn_idx_catchup_lib import (  # noqa: E402
    catchup_symbols,
    export_all_daily_panel,
    global_latest_date,
)


def main() -> int:
    ap = argparse.ArgumentParser(description="Backfill IDX legacy DB via Yahoo Finance")
    ap.add_argument("--symbols", nargs="*", default=[], help="Subset; default = full 648 list")
    ap.add_argument("--batch-size", type=int, default=24)
    ap.add_argument("--sleep", type=float, default=0.75)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-export", action="store_true", help="Skip parquet export")
    ap.add_argument("--no-refresh-types", action="store_true", help="Skip name-type snapshot refresh")
    args = ap.parse_args()

    before = global_latest_date()
    print(json.dumps({"global_max_before": str(before.date()) if before is not None else None}, indent=2))

    result = catchup_symbols(
        args.symbols,
        batch_size=args.batch_size,
        sleep_s=args.sleep,
        dry_run=args.dry_run,
    )
    print(json.dumps(result, indent=2))

    if args.dry_run:
        return 0

    after = global_latest_date()
    print(json.dumps({"global_max_after": str(after.date()) if after is not None else None}, indent=2))

    if not args.no_export:
        out = export_all_daily_panel()
        panel_rows = len(pd.read_parquet(out))
        print(json.dumps({"exported_panel": str(out), "panel_rows": panel_rows}, indent=2))

    if not args.no_refresh_types:
        from idn_name_type_lib import refresh_full_universe_snapshot

        snap = refresh_full_universe_snapshot()
        print(
            json.dumps(
                {
                    "name_types_refreshed": True,
                    "date_max": snap.get("date_max"),
                    "name_type_counts": snap.get("name_type_counts"),
                    "liquid_core_symbols": snap.get("liquid_core_symbols"),
                },
                indent=2,
            )
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
