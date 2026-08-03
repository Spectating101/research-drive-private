#!/usr/bin/env python3
"""Build IDX turnaround / shock research artifacts.

Outputs (no markdown):
  data_lake/research_panels/idn_turnaround/daily_features.parquet
  data_lake/research_panels/idn_turnaround/turn_events.parquet
  backtests/outputs/idn_turnaround/signal_eval.json
  backtests/outputs/idn_turnaround/case_book.json
  backtests/outputs/idn_turnaround/signal_follow_guide.json
  backtests/outputs/idn_turnaround/registry_snapshot.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

import importlib.util as _ilu
from pathlib import Path as _Path

_bspec = _ilu.spec_from_file_location("sr_bootstrap", _Path(__file__).resolve().parent / "_repo_bootstrap.py")
_bmod = _ilu.module_from_spec(_bspec)
_bspec.loader.exec_module(_bmod)
REPO = _bmod.repo_root_from_file(__file__)
sys.path.insert(0, str(REPO / "scripts"))

from idn_eval_splits import split_meta  # noqa: E402
from idn_turnaround_lib import (  # noqa: E402
    OUT_DIR,
    apply_signal_rules,
    build_case_book,
    build_turnaround_panel,
    confluence_matrix,
    evaluate_signals,
    load_registry,
    signal_follow_guide,
)

OUT_BT = REPO / "backtests/outputs/idn_turnaround"


def main() -> int:
    ap = argparse.ArgumentParser(description="IDX turnaround / shock research pipeline")
    ap.add_argument("--skip-panel", action="store_true", help="Reuse existing daily_features.parquet")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_BT.mkdir(parents=True, exist_ok=True)

    feat_path = OUT_DIR / "daily_features.parquet"
    ev_path = OUT_DIR / "turn_events.parquet"

    if args.skip_panel and feat_path.exists():
        panel = pd.read_parquet(feat_path)
        turn_events = pd.read_parquet(ev_path) if ev_path.exists() else pd.DataFrame()
    else:
        panel, turn_events = build_turnaround_panel()
        panel = panel.drop(columns=[c for c in panel.columns if c.startswith("sig_")], errors="ignore")
        panel.to_parquet(feat_path, index=False)
        if not turn_events.empty:
            turn_events.to_parquet(ev_path, index=False)

    panel = apply_signal_rules(panel)
    panel.to_parquet(feat_path, index=False)

    eval_results = evaluate_signals(panel)
    cases = build_case_book(panel)
    guide = signal_follow_guide(eval_results)
    registry = load_registry()
    conf = confluence_matrix(panel, turn_events)

    panel["week_end"] = pd.to_datetime(panel["date"]).dt.to_period("W-FRI").dt.to_timestamp("W-FRI")
    split = split_meta(panel.groupby("week_end", as_index=False).first(), time_col="week_end")

    manifest = {
        "built_at_utc": datetime.now(UTC).isoformat(),
        "universe": "full_tradable",
        "panel_rows": int(len(panel)),
        "symbols": int(panel["yahoo_symbol"].nunique()),
        "turn_events": int(len(turn_events)),
        "date_min": str(panel["date"].min().date()),
        "date_max": str(panel["date"].max().date()),
        "split_meta": split,
        "signal_rules_n": len(registry.get("signal_rules", [])),
        "schools_n": len(registry.get("schools", [])),
    }

    (OUT_BT / "confluence_matrix.json").write_text(json.dumps(conf, indent=2) + "\n", encoding="utf-8")
    (OUT_BT / "signal_eval.json").write_text(json.dumps({"manifest": manifest, "results": eval_results}, indent=2) + "\n", encoding="utf-8")
    (OUT_BT / "case_book.json").write_text(json.dumps(cases, indent=2) + "\n", encoding="utf-8")
    (OUT_BT / "signal_follow_guide.json").write_text(json.dumps(guide, indent=2) + "\n", encoding="utf-8")
    (OUT_BT / "registry_snapshot.json").write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(manifest, indent=2))
    print(f"wrote {feat_path}")
    print(f"wrote {OUT_BT / 'signal_follow_guide.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
