#!/usr/bin/env python3
"""Monthly / swing horizon report with OOS split — no annual CAGR headline.

Reports mean return **per period** (week, 2w, 4w, or calendar month) plus hit rate,
period Sharpe, max drawdown, and $1 compound — split full / pre-2024 / OOS from 2024.

Example:
  python scripts/run_quant_horizon_report.py --country IDN --oos-start 2024-01-01
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

from quant_ai.config import load_config  # noqa: E402
from quant_ai.horizons import format_report_table, horizon_report  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--country", default="IDN")
    ap.add_argument("--oos-start", default="2024-01-01")
    ap.add_argument("--universe-asof", default="2023-12-31", help="Fix stock universe before OOS")
    ap.add_argument("--stock-universe", type=int, default=25)
    ap.add_argument("--min-train-weeks", type=int, default=78)
    ap.add_argument("--horizons", default="1w,2w,4w,monthly")
    ap.add_argument("--focus", default="equal_weight", help="Filter table to strategy substring")
    args = ap.parse_args()

    cfg = load_config(country=args.country)
    cfg.stock_universe = args.stock_universe
    cfg.min_train_weeks = args.min_train_weeks
    horizons = [h.strip() for h in args.horizons.split(",") if h.strip()]

    print(f"Building horizon report for {cfg.country_label} ({cfg.country})...")
    print(f"  OOS from {args.oos_start} | universe fixed as-of {args.universe_asof}")
    print(f"  Horizons: {horizons}\n")

    rows = horizon_report(
        cfg,
        horizons=horizons,  # type: ignore[arg-type]
        oos_start=args.oos_start,
        universe_asof=args.universe_asof or None,
    )

    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_dir = cfg.out_root / cfg.country / f"horizons_{run_id}"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "horizon_report.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")

    table = format_report_table(rows, focus=args.focus if args.focus != "all" else None)
    (out_dir / "horizon_report.txt").write_text(table + "\n", encoding="utf-8")
    print(table)

    # Highlight OOS equal-weight across horizons
    eq_oos = [r for r in rows if r["sample"] == "oos_from2024" and "equal_weight" in r["strategy"]]
    if eq_oos:
        print("\n--- OOS equal-weight basket (what matters for 'can we trade this now?') ---")
        for r in eq_oos:
            print(
                f"  {r['horizon']:7}  mean {r['mean_return']*100:+.2f}%/period  "
                f"hit {r['hit_rate']*100:.0f}%  sharpe {r['sharpe']:.2f}  "
                f"compound {r['total_compound']:.2f}x over {r['n_periods']} periods"
            )

    print(f"\nWrote {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
