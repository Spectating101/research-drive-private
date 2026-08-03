#!/usr/bin/env python3
"""Refresh IDX name-type snapshot on the full exchange ticker list (not liquid-50).

Reads all symbols from config/markets/indonesia_idx_legacy_all.tickers.txt and
OHLCV from data_lake/markets/idx_legacy_restore/historical_data.db.

Output:
  data_lake/research_panels/idn_name_types/latest.json
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

from idn_name_type_lib import (  # noqa: E402
    SNAPSHOT_PATH,
    ensure_full_universe_snapshot,
    load_idx_all_universe,
    refresh_full_universe_snapshot,
)


def main() -> int:
    ap = argparse.ArgumentParser(description="Refresh IDX name types on full ticker list")
    ap.add_argument("--force", action="store_true", help="Rebuild even if snapshot exists")
    args = ap.parse_args()

    universe = load_idx_all_universe()
    if args.force:
        snap = refresh_full_universe_snapshot()
    else:
        snap = ensure_full_universe_snapshot()

    summary = {
        "universe_id": snap.get("universe_id"),
        "n_symbols": snap.get("n_symbols"),
        "n_classified": snap.get("n_classified"),
        "date_max": snap.get("date_max"),
        "name_type_counts": snap.get("name_type_counts"),
        "compounder_symbols": snap.get("compounder_symbols"),
        "liquid_core_symbols": snap.get("liquid_core_symbols"),
        "output": str(SNAPSHOT_PATH),
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
