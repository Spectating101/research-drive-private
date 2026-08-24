#!/usr/bin/env python3
"""Ingest Dec 2025 desktop Eikon RESCUED vol/skew panel into tidy parquet vault."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
DEFAULT_SRC = REPO / "From-refinitiv/RESCUED_Full_Market_Data_20251215.csv"
DEFAULT_OUT = REPO / "data_lake/refinitiv_backfill/rescued_desktop_20251215/processed"

METRIC_MAP = {
    "Price Close": "price_close",
    "Volume": "volume",
    "Volatility - 30 days": "volatility_30d",
    "Volatility - 90 days": "volatility_90d",
    "TR.VOLATILITY360D": "volatility_360d",
    "TR.IMPVOLPUTDELTA10": "impvol_put_delta10",
    "TR.IMPVOLPUTDELTA25": "impvol_put_delta25",
    "TR.IMPVOLDELTA10": "impvol_call_delta10",
    "TR.IMPVOLDELTA25": "impvol_call_delta25",
    "TR.SHORTINTERESTRATIO": "short_interest_ratio",
    "Put Call Ratio": "put_call_ratio",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def rescued_to_long(src: Path) -> pd.DataFrame:
    wide = pd.read_csv(src, header=[0, 1], index_col=0, parse_dates=True)
    wide.index.name = "date"
    rows: list[pd.DataFrame] = []
    for (ric, metric_raw), series in wide.items():
        if str(ric).startswith("Unnamed"):
            continue
        metric = METRIC_MAP.get(str(metric_raw), re.sub(r"[^\w]+", "_", str(metric_raw).lower()).strip("_"))
        frame = series.rename("value").reset_index()
        frame["ric"] = str(ric)
        frame["metric"] = metric
        frame["source"] = "desktop.eikon.rescued_20251215"
        rows.append(frame[["date", "ric", "metric", "value", "source"]])
    if not rows:
        return pd.DataFrame()
    out = pd.concat(rows, ignore_index=True)
    out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    out["value"] = pd.to_numeric(out["value"], errors="coerce")
    return out.dropna(subset=["date"]).sort_values(["ric", "date", "metric"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=str(DEFAULT_SRC))
    ap.add_argument("--out-dir", default=str(DEFAULT_OUT))
    args = ap.parse_args()

    src = Path(args.src)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    long = rescued_to_long(src)
    out_path = out_dir / "us_risk_vol_skew_daily.parquet"
    long.to_parquet(out_path, index=False)

    manifest = {
        "generated_at": utc_now(),
        "source": str(src),
        "output": str(out_path),
        "rows": int(len(long)),
        "rics": int(long["ric"].nunique()) if not long.empty else 0,
        "metrics": sorted(long["metric"].unique().tolist()) if not long.empty else [],
        "date_range": {"min": str(long["date"].min()), "max": str(long["date"].max())} if not long.empty else None,
        "notes": "Desktop Eikon pull; full US S&P vol/skew/SI history not available on YZU EDP.",
    }
    (out_dir.parent / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
