#!/usr/bin/env python3
"""Fry signal backtest — guess accuracy vs random + strategy P&L."""

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

from idn_fry_backtest_lib import build_fry_backtest_report  # noqa: E402


def main() -> int:
    argparse.ArgumentParser(description="Fry backtest vs random").parse_args()
    report = build_fry_backtest_report()
    print(json.dumps(report["headline"], indent=2))
    print("\n--- classification OOS T1 ---")
    cls = report["classification"]["rule_metrics"]
    for r in cls:
        if r.get("era") == "oos" and r.get("rule_id") == "T1_deep_dd_vol" and r.get("label") == "pop_30d":
            print(json.dumps(r, indent=2))
    print("\n--- strategies ---")
    for s in report["strategy_pnl"]["strategies"]:
        print(f"{s.get('strategy')}: n={s.get('n')} mean={s.get('mean_return_pct')}% win={s.get('win_rate_pct')}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
