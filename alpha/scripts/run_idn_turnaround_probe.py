#!/usr/bin/env python3
"""Probe turnaround features + fired signals for one symbol/date."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

import importlib.util as _ilu
from pathlib import Path as _Path

_bspec = _ilu.spec_from_file_location("sr_bootstrap", _Path(__file__).resolve().parent / "_repo_bootstrap.py")
_bmod = _ilu.module_from_spec(_bspec)
_bspec.loader.exec_module(_bmod)
REPO = _bmod.repo_root_from_file(__file__)
sys.path.insert(0, str(REPO / "scripts"))

from idn_turnaround_lib import OUT_DIR, apply_signal_rules, load_registry  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--date", required=True)
    args = ap.parse_args()

    path = OUT_DIR / "daily_features.parquet"
    if not path.exists():
        print("Run scripts/run_idn_turnaround_research.py first", file=sys.stderr)
        return 1

    panel = pd.read_parquet(path)
    if not any(c.startswith("sig_") for c in panel.columns):
        panel = apply_signal_rules(panel)

    dt = pd.Timestamp(args.date)
    row = panel[(panel["yahoo_symbol"] == args.symbol) & (pd.to_datetime(panel["date"]) == dt)]
    if row.empty:
        print(json.dumps({"found": False, "symbol": args.symbol, "date": args.date}))
        return 0

    r = row.iloc[0]
    reg = load_registry()
    fired = [rule["id"] for rule in reg.get("signal_rules", []) if r.get(f"sig_{rule['id']}") == 1]
    out = {
        "found": True,
        "symbol": args.symbol,
        "date": str(dt.date()),
        "return_1d_pct": round(float(r["return_1d"]) * 100, 2),
        "reward_5d_pct": round(float(r["reward_5d_pct"]), 2) if pd.notna(r.get("reward_5d_pct")) else None,
        "rsi14": round(float(r["rsi14"]), 1) if pd.notna(r.get("rsi14")) else None,
        "near_support_60d": int(r.get("near_support_60d", 0)),
        "near_resistance_60d": int(r.get("near_resistance_60d", 0)),
        "ihsg_regime": r.get("ihsg_regime"),
        "bandar_lite_label": r.get("bandar_lite_label"),
        "consecutive_ara_days": int(r.get("consecutive_ara_days", 0)),
        "signals_fired": fired,
    }
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
