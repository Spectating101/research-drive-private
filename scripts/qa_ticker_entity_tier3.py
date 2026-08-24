#!/usr/bin/env python3
"""QA report for Tier-3 entity-resolved ticker panels."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
DEFAULT_RUN = REPO / "data_lake/research_panels/ticker_news_market/ticker_20260610"
OVERLAY = REPO / "data_lake/news_shock_taxonomy/derived/gdelt_entity_ticker_overlay"


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-dir", type=Path, default=DEFAULT_RUN)
    ap.add_argument("--out", type=Path, default=None)
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    run_dir = args.run_dir
    report: dict[str, object] = {"run_dir": str(run_dir)}

    fused_path = run_dir / "ticker_week_entity_market_panel.parquet"
    if fused_path.exists():
        fused = pd.read_parquet(fused_path)
        fused["week_end"] = pd.to_datetime(fused["week_end"], errors="coerce")
        report["fused"] = {
            "rows": int(len(fused)),
            "tickers": int(fused["yahoo_symbol"].nunique()),
            "week_min": str(fused["week_end"].min().date()),
            "week_max": str(fused["week_end"].max().date()),
            "median_entity_mentions": float(fused["entity_mention_rows"].median()) if "entity_mention_rows" in fused.columns else None,
            "return_1w_nonnull_pct": float(fused["return_1w"].notna().mean() * 100) if "return_1w" in fused.columns else None,
            "liquidity_buckets": fused["liquidity_bucket"].value_counts().to_dict() if "liquidity_bucket" in fused.columns else {},
        }
        thin = fused.groupby("yahoo_symbol").size()
        report["sparse_tickers_lt4_weeks"] = int((thin < 4).sum())

    for name in ("ticker_week_entity_long_panel", "ticker_week_entity_residual_panel"):
        path = run_dir / f"{name}.parquet"
        if path.exists():
            df = pd.read_parquet(path)
            report[name] = {"rows": int(len(df)), "columns": int(len(df.columns))}

    if OVERLAY.exists():
        manifest = OVERLAY / "manifest.json"
        if manifest.exists():
            rows = json.loads(manifest.read_text(encoding="utf-8"))
            report["overlay_windows"] = {
                "total": len(rows),
                "complete": sum(1 for r in rows if r.get("status") == "complete"),
                "corrupt": sum(1 for r in rows if r.get("status") == "corrupt_input"),
            }

    prefetch = REPO / "data_lake/news_shock_taxonomy/derived/gdelt_entity_article_prefetch/manifest.jsonl"
    if prefetch.exists():
        pulled = skipped = failed = 0
        for line in prefetch.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            st = row.get("status", "")
            if st == "pulled":
                pulled += 1
            elif st in {"scored_exists", "normalized_exists"}:
                skipped += 1
            elif st == "failed":
                failed += 1
        report["article_prefetch"] = {"pulled": pulled, "skipped": skipped, "failed": failed}

    out_path = args.out or run_dir / "tier3_qa_report.json"
    out_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
