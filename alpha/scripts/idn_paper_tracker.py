#!/usr/bin/env python3
"""Paper ledger for Indonesia invest trial portfolios (weekly rebalance).

Loads latest_portfolio_*.json from idn_invest runs, marks daily via yfinance,
appends to ledger.csv, and prints recent move summary (today / yesterday / since rebalance).

Example:
  python scripts/idn_paper_tracker.py --strategy top5
  python scripts/idn_paper_tracker.py --portfolio backtests/outputs/idn_invest/.../latest_portfolio_top5.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

import importlib.util as _ilu
from pathlib import Path as _Path

_bspec = _ilu.spec_from_file_location("sr_bootstrap", _Path(__file__).resolve().parent / "_repo_bootstrap.py")
_bmod = _ilu.module_from_spec(_bspec)
_bspec.loader.exec_module(_bmod)
REPO = _bmod.repo_root_from_file(__file__)
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

IDN_INVEST = REPO / "backtests/outputs/idn_invest"
DEFAULT_PORTFOLIO = REPO / "backtests/outputs/idn_weekly_position_sheet/latest_portfolio.json"
DEFAULT_LEDGER = REPO / "backtests/outputs/idn_weekly_position_sheet/paper/ledger.csv"
DEFAULT_MOVES = REPO / "backtests/outputs/idn_weekly_position_sheet/paper/recent_moves.json"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _find_latest_portfolio(strategy: str) -> Path:
    runs = sorted(IDN_INVEST.glob("*/latest_portfolio_*.json"), reverse=True)
    needle = f"latest_portfolio_{strategy}.json"
    for p in runs:
        if p.name == needle:
            return p
    raise SystemExit(f"No {needle} under {IDN_INVEST}/*/ — run run_idn_invest_trial.py first")


def _fetch_closes(tickers: list[str], start: str, end: str | None = None) -> pd.DataFrame:
    import yfinance as yf

    end = end or datetime.now(UTC).strftime("%Y-%m-%d")
    raw = yf.download(tickers, start=start, end=end, progress=False, auto_adjust=True)
    if raw is None or raw.empty:
        raise SystemExit(f"yfinance returned no data for {tickers}")
    if isinstance(raw.columns, pd.MultiIndex):
        close = raw["Close"]
    else:
        close = raw[["Close"]].rename(columns={"Close": tickers[0]})
    close.index = pd.to_datetime(close.index)
    return close.sort_index()


def _append_ledger(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame([row])
    if path.exists():
        old = pd.read_csv(path)
        old = old[old["date"].astype(str) != str(row["date"])]
        df = pd.concat([old, df], ignore_index=True)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.sort_values("date")
    df["date"] = df["date"].dt.date.astype(str)
    df.to_csv(path, index=False)


def _weighted_return(returns: pd.Series, weights: dict[str, float]) -> float:
    w = pd.Series(weights, dtype=float)
    w = w / w.sum()
    common = [c for c in w.index if c in returns.index and np.isfinite(returns[c])]
    if not common:
        return 0.0
    return float((returns[common] * w[common]).sum())


def recent_moves_report(
    weights: dict[str, float],
    prices: pd.DataFrame,
    as_of_week: str,
) -> dict[str, Any]:
    ret = prices.pct_change()
    dates = prices.index.dropna()
    if len(dates) < 2:
        return {"error": "insufficient price history"}

    last = dates[-1]
    prev = dates[-2]
    prev2 = dates[-3] if len(dates) >= 3 else prev

    def day_pack(d: pd.Timestamp, label: str) -> dict:
        row = ret.loc[d]
        per = {}
        for sym in weights:
            if sym in prices.columns and sym in row.index and np.isfinite(row[sym]):
                per[sym] = {
                    "return_pct": float(row[sym] * 100),
                    "close": float(prices.loc[d, sym]),
                    "prev_close": float(prices.loc[prev if d == last else dates[dates.get_loc(d) - 1], sym])
                    if dates.get_loc(d) > 0
                    else float("nan"),
                }
        return {
            "label": label,
            "date": str(d.date()),
            "portfolio_return_pct": _weighted_return(row, weights) * 100,
            "tickers": per,
        }

    reb = pd.Timestamp(as_of_week)
    reb_idx = dates[dates >= reb]
    since_reb = float("nan")
    if len(reb_idx) > 0:
        start_d = reb_idx[0]
        cum = prices.loc[last] / prices.loc[start_d] - 1.0
        since_reb = _weighted_return(cum, weights) * 100

    return {
        "as_of_week": as_of_week,
        "latest_price_date": str(last.date()),
        "yesterday": day_pack(prev, "day_before_latest"),
        "today": day_pack(last, "latest_session"),
        "since_rebalance_pct": since_reb,
        "since_rebalance_from": str(reb_idx[0].date()) if len(reb_idx) else None,
    }


def update_ledger(
    portfolio: dict[str, Any],
    ledger_path: Path,
    initial_equity: float,
) -> pd.DataFrame:
    weights = {k: float(v) for k, v in portfolio.get("weights", {}).items() if k != "CASH"}
    if not weights:
        return pd.DataFrame()

    as_of_week = pd.Timestamp(portfolio["as_of_week"])
    tickers = list(weights.keys())
    start = (as_of_week - pd.Timedelta(days=7)).strftime("%Y-%m-%d")
    prices = _fetch_closes(tickers, start=start)
    w = pd.Series(weights, dtype=float)
    w = w / w.sum()

    equity0 = initial_equity
    strategy = portfolio.get("strategy", "unknown")
    if ledger_path.exists():
        old = pd.read_csv(ledger_path)
        sub = old[(old["strategy"] == strategy) & (old["as_of_week"] == str(as_of_week.date()))]
        if not sub.empty:
            equity0 = float(pd.to_numeric(sub["equity"], errors="coerce").dropna().iloc[-1])

    dates = prices.index[prices.index >= as_of_week]
    if len(dates) < 1:
        dates = prices.index[-5:]
    dret = prices.pct_change(fill_method=None).fillna(0.0)

    eq = equity0
    peak = equity0
    prev_eq = equity0
    rows = []
    for dt in dates:
        if dt == dates[0] and dret.loc[dt].abs().sum() == 0:
            continue
        r = _weighted_return(dret.loc[dt], weights)
        eq = float(eq * (1.0 + r))
        peak = max(peak, eq)
        dd = eq / peak - 1.0 if peak > 0 else 0.0
        dr = eq / prev_eq - 1.0 if prev_eq > 0 else 0.0
        prev_eq = eq
        row = {
            "date": str(dt.date()),
            "as_of_week": str(as_of_week.date()),
            "strategy": strategy,
            "equity": eq,
            "daily_return": dr,
            "drawdown": dd,
            "n_holdings": len(weights),
        }
        _append_ledger(ledger_path, row)
        rows.append(row)
    return pd.DataFrame(rows)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--strategy", default="top5", help="latest_portfolio_{strategy}.json under idn_invest (legacy)")
    ap.add_argument("--portfolio", type=Path, default=DEFAULT_PORTFOLIO, help="Portfolio JSON path")
    ap.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    ap.add_argument("--moves-out", type=Path, default=DEFAULT_MOVES)
    ap.add_argument("--initial-equity", type=float, default=10_000.0)
    ap.add_argument("--skip-ledger", action="store_true")
    args = ap.parse_args()

    port_path = args.portfolio
    if not port_path.exists() and args.portfolio == DEFAULT_PORTFOLIO:
        port_path = _find_latest_portfolio(args.strategy)
    portfolio = _read_json(port_path)
    weights = {k: float(v) for k, v in portfolio.get("weights", {}).items() if k != "CASH"}
    if not weights:
        print("Portfolio is 100% cash — nothing to mark.")
        return 0

    as_of_week = portfolio.get("as_of_week", "")
    tickers = list(weights.keys())
    prices = _fetch_closes(tickers, start=(pd.Timestamp(as_of_week) - pd.Timedelta(days=30)).strftime("%Y-%m-%d"))

    moves = recent_moves_report(weights, prices, as_of_week)
    moves["portfolio_path"] = str(port_path)
    moves["strategy"] = portfolio.get("strategy")
    moves["weights"] = weights
    args.moves_out.parent.mkdir(parents=True, exist_ok=True)
    args.moves_out.write_text(json.dumps(moves, indent=2), encoding="utf-8")

    if not args.skip_ledger:
        update_ledger(portfolio, args.ledger, args.initial_equity)

    # Print human summary
    print(f"Portfolio: {portfolio.get('strategy')}  as_of_week={as_of_week}")
    print(f"  Weights: {', '.join(f'{k} {v:.0%}' for k,v in weights.items())}")
    print(f"  Latest price date: {moves.get('latest_price_date')}")
    if "today" in moves:
        t = moves["today"]
        print(f"\n  Latest session ({t['date']}): portfolio {t['portfolio_return_pct']:+.2f}%")
        for sym, info in sorted(t.get("tickers", {}).items()):
            print(f"    {sym:10} {info['return_pct']:+.2f}%  close={info['close']:.0f}")
    if "yesterday" in moves:
        y = moves["yesterday"]
        print(f"\n  Prior session ({y['date']}): portfolio {y['portfolio_return_pct']:+.2f}%")
        for sym, info in sorted(y.get("tickers", {}).items()):
            print(f"    {sym:10} {info['return_pct']:+.2f}%")
    if moves.get("since_rebalance_pct") is not None and np.isfinite(moves["since_rebalance_pct"]):
        print(
            f"\n  Since rebalance ({moves.get('since_rebalance_from')}): "
            f"{moves['since_rebalance_pct']:+.2f}%"
        )
    if not args.skip_ledger:
        print(f"\nLedger: {args.ledger}")
    print(f"Moves JSON: {args.moves_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
