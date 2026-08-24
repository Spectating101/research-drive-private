#!/usr/bin/env python3
"""US SP500 daily price proxy via yfinance — interim panel until CRSP ingest completes."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO / "kernel") not in sys.path:
    sys.path.insert(0, str(REPO / "kernel"))

from sharpe_kernel.paths import repo_root_from_file

ROOT = repo_root_from_file(__file__)
TICKERS = ROOT / "config/tickers_sp500.txt"
OUT_DIR = ROOT / "data_lake/research_panels/public_equity"
OUT_PANEL = OUT_DIR / "us_sp500_yfinance_daily.parquet"


def _load_symbols(*, stride: int = 1, limit: int | None = None) -> list[str]:
    syms: list[str] = []
    for line in TICKERS.read_text(encoding="utf-8").splitlines():
        s = line.split("#", 1)[0].strip().upper()
        if s and not s.startswith("^"):
            syms.append(s)
    if stride > 1:
        syms = syms[::stride]
    if limit:
        syms = syms[:limit]
    return syms


def build_panel(*, stride: int = 1, limit: int | None = None, period: str = "10y") -> dict:
    import pandas as pd
    import yfinance as yf

    symbols = _load_symbols(stride=stride, limit=limit)
    if not symbols:
        raise RuntimeError(f"No symbols in {TICKERS}")

    frames: list[pd.DataFrame] = []
    for sym in symbols:
        try:
            hist = yf.Ticker(sym).history(period=period, auto_adjust=True)
        except Exception:
            continue
        if hist.empty:
            continue
        h = hist.reset_index()
        h["yahoo_symbol"] = sym
        h = h.rename(columns={"Date": "date", "Close": "close", "Volume": "volume"})
        frames.append(h[["date", "yahoo_symbol", "close", "volume"]])

    if not frames:
        raise RuntimeError("yfinance returned no rows")

    panel = pd.concat(frames, ignore_index=True)
    panel["date"] = pd.to_datetime(panel["date"], utc=True).dt.tz_localize(None)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    panel.to_parquet(OUT_PANEL, index=False)

    return {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "symbols_requested": len(symbols),
        "symbols_with_data": panel["yahoo_symbol"].nunique(),
        "rows": len(panel),
        "date_min": str(panel["date"].min().date()),
        "date_max": str(panel["date"].max().date()),
        "output": str(OUT_PANEL.relative_to(ROOT)),
        "proxy_note": "Interim US equity lane until CRSP us_stock_daily panel is ingested",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stride", type=int, default=1, help="Take every Nth ticker (1=full SP500)")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--period", default="10y")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    out = build_panel(stride=max(args.stride, 1), limit=args.limit, period=args.period)
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
