#!/usr/bin/env python3
from __future__ import annotations

"""
Paper tracker for a monthly signal.json.

Given:
  - a signal.json with weights (from export_alpha_signal.py)
  - a tidy panel csv with daily prices

It simulates holding the weights from the signal's as_of month-end forward
and appends daily equity to a ledger CSV.
"""

import argparse
import json
from pathlib import Path
from typing import Any, Dict

import numpy as np
import pandas as pd


def _read_json(path: Path) -> Dict[str, Any]:
    obj = json.loads(path.read_text())
    if not isinstance(obj, dict):
        raise ValueError(f"Expected dict JSON: {path}")
    return obj


def _load_panel_prices(panel_csv: Path) -> pd.DataFrame:
    df = pd.read_csv(panel_csv, parse_dates=["Date"])
    need = {"Instrument", "Date", "Price_Close"}
    if not need.issubset(df.columns):
        raise ValueError(f"Panel must have columns: {sorted(need)}")
    df = df.dropna(subset=["Instrument", "Date", "Price_Close"]).copy()
    df["Price_Close"] = pd.to_numeric(df["Price_Close"], errors="coerce")
    df = df.dropna(subset=["Price_Close"])
    px = df.pivot_table(index="Date", columns="Instrument", values="Price_Close", aggfunc="last").sort_index().ffill()
    return px


def _append_row(path: Path, row: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame([row])
    if path.exists():
        existing = pd.read_csv(path)
        # Remove any existing row with the same date so the new row wins
        existing = existing[existing["date"].astype(str) != str(row["date"])]
        out = pd.concat([existing, df], ignore_index=True)
    else:
        out = df
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    out = out.sort_values("date")
    out["date"] = out["date"].dt.date.astype(str)
    out.to_csv(path, index=False)


def main() -> int:
    ap = argparse.ArgumentParser(description="Paper tracker: mark-to-market a monthly signal.json daily.")
    ap.add_argument("--signal", type=Path, required=True)
    ap.add_argument("--panel", type=Path, required=True)
    ap.add_argument("--ledger", type=Path, default=Path("Sharpe-Renaissance/backtests/outputs/alpha_paper/ledger.csv"))
    ap.add_argument("--initial-equity", type=float, default=10_000.0)
    args = ap.parse_args()

    sig = _read_json(args.signal)
    as_of = pd.to_datetime(sig.get("as_of_month"), errors="coerce")
    if pd.isna(as_of):
        raise SystemExit("signal.json missing/invalid as_of_month")
    weights = {str(k): float(v) for k, v in (sig.get("weights") or {}).items()}
    if not weights:
        raise SystemExit("signal.json has no weights")

    px = _load_panel_prices(args.panel)
    if as_of not in px.index:
        # Use the last price date <= as_of.
        idx = px.index[px.index <= as_of]
        if len(idx) == 0:
            raise SystemExit(f"No prices on/before as_of={as_of.date()}")
        as_of = pd.Timestamp(idx[-1])

    cols = set(px.columns)
    held = {k: v for k, v in weights.items() if k in cols and np.isfinite(v) and v != 0.0}
    if not held:
        raise SystemExit("No signal tickers exist in the panel prices.")

    # Start equity for the current signal period.
    # If the ledger has rows from a PRIOR signal (different as_of), carry
    # forward that period's equity at or before the current as_of date.
    # This avoids reading stale rows where the old signal simulated past its period.
    equity0 = float(args.initial_equity)
    if args.ledger.exists():
        df = pd.read_csv(args.ledger)
        if not df.empty and "equity" in df.columns and "as_of" in df.columns:
            prior = df[df["as_of"].astype(str) != str(as_of.date())]
            if not prior.empty:
                try:
                    prior_dated = prior.copy()
                    prior_dated["_dt"] = pd.to_datetime(prior_dated["date"], errors="coerce")
                    # Only use rows on/before the current signal's as_of date
                    prior_dated = prior_dated[prior_dated["_dt"] <= as_of]
                    if not prior_dated.empty:
                        equity0 = float(pd.to_numeric(prior_dated["equity"], errors="coerce").dropna().iloc[-1])
                except Exception:
                    pass

    dates = px.index[px.index >= as_of]
    if len(dates) < 2:
        print("Not enough dates after as_of to mark.")
        return 0

    # Daily returns for held symbols; assume weights are constant (monthly rebalance).
    sub = px[list(held.keys())].reindex(dates).ffill()
    dret = sub.pct_change(fill_method=None).fillna(0.0)
    w = pd.Series(held, dtype=float)
    w = w / (float(w.abs().sum()) or 1.0)

    eq = equity0
    peak = equity0
    prev_eq = equity0
    for dt in dates[1:]:
        r = float((dret.loc[dt] * w).sum())
        eq = float(eq * (1.0 + r))
        peak = float(max(peak, eq))
        dd = float(eq / peak - 1.0) if peak > 0 else 0.0
        dr = float(eq / prev_eq - 1.0) if prev_eq > 0 else 0.0
        prev_eq = eq
        _append_row(
            args.ledger,
            {
                "date": str(pd.Timestamp(dt).date()),
                "as_of": str(pd.Timestamp(as_of).date()),
                "equity": float(eq),
                "daily_return": float(dr),
                "drawdown": float(dd),
                "n_holdings": int(len(w)),
            },
        )

    print(f"Updated ledger: {args.ledger}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

