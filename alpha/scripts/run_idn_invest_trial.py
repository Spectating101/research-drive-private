#!/usr/bin/env python3
"""Indonesia invest trial: liquid IDX universe + weekly ticker picks + net costs.

Uses config/markets/asia_yfinance_universes.json → indonesia_liquid_core (BBCA, BMRI, …)
NOT row_count_daily ranking.

Strategies (weekly rebalance on week_end):
  liquid_eq       — equal-weight all names with a return that week
  top5 / top10    — ridge news features per ticker, hold top-N by predicted 1w return
  top5_cash_flat  — top5 only when basket avg prediction > 0, else cash
  bbca_hold       — 100% BBCA.JK benchmark

Outputs holdings_weekly.csv, ledger_gross.csv, ledger_net.csv, strategy_summary.json,
latest_portfolio.json (last rebalance weights for paper tracking).

Example:
  python scripts/run_idn_invest_trial.py --top-n 5 --cost-bps 25 --oos-frac 0.25
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

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

from run_asia_news_market_modeling_trial import ridge_fit_predict  # noqa: E402
from quant_ai.pipeline import SHOCKS  # noqa: E402

BROADCAST = REPO / "data_lake/research_panels/ticker_news_market/ticker_20260610/ticker_week_country_broadcast_panel.parquet"
UNIVERSE_CFG = REPO / "config/markets/asia_yfinance_universes.json"
OUT_ROOT = REPO / "backtests/outputs/idn_invest"
TARGET = "fwd_return_1w"


@dataclass
class WeekResult:
    week_end: str
    strategy: str
    gross_return: float
    net_return: float
    turnover: float
    cost_bps: float
    n_holdings: int
    holdings: dict[str, float]


def load_liquid_universe() -> list[str]:
    cfg = json.loads(UNIVERSE_CFG.read_text(encoding="utf-8"))
    for u in cfg.get("universes", []):
        if u.get("id") == "indonesia_liquid_core":
            return list(u["tickers"])
    raise SystemExit("indonesia_liquid_core not found in asia_yfinance_universes.json")


def walkforward_predictions(
    symbols: list[str],
    min_train: int,
    alpha: float,
) -> pd.DataFrame:
    b = pd.read_parquet(BROADCAST)
    b["week_end"] = pd.to_datetime(b["week_end"])
    b = b[(b["country_iso3"] == "IDN") & (b["yahoo_symbol"].isin(symbols))].copy()
    feat = [f"{s}_per_1k_rows" for s in SHOCKS if f"{s}_per_1k_rows" in b.columns]
    weeks = sorted(b["week_end"].dropna().unique())
    rows = []
    for i, week in enumerate(weeks):
        if i < min_train:
            continue
        train = b[b["week_end"] < week]
        test = b[b["week_end"] == week]
        if len(test) < 5:
            continue
        for sym, grp in test.groupby("yahoo_symbol"):
            tr = train[train["yahoo_symbol"] == sym]
            if len(tr) < 30:
                continue
            if grp[TARGET].isna().all():
                continue
            p = ridge_fit_predict(tr, grp, feat, TARGET, alpha)
            rows.append(
                {
                    "week_end": week,
                    "yahoo_symbol": sym,
                    TARGET: float(grp[TARGET].iloc[0]),
                    "pred_fwd_return_1w": float(p[0]),
                }
            )
    return pd.DataFrame(rows)


def pick_holdings(
    g: pd.DataFrame,
    strategy: str,
    top_n: int,
) -> dict[str, float]:
    sub = g.dropna(subset=[TARGET])
    if sub.empty:
        return {}

    if strategy == "bbca_hold":
        row = sub[sub["yahoo_symbol"] == "BBCA.JK"]
        return {"BBCA.JK": 1.0} if not row.empty and np.isfinite(row[TARGET].iloc[0]) else {}

    if strategy == "liquid_eq":
        names = sub["yahoo_symbol"].tolist()
        w = 1.0 / len(names)
        return {s: w for s in names}

    ranked = sub.dropna(subset=["pred_fwd_return_1w"]).sort_values("pred_fwd_return_1w", ascending=False)
    if ranked.empty:
        return {}

    if strategy == "top5_cash_flat":
        if float(ranked["pred_fwd_return_1w"].mean()) <= 0:
            return {}
        pick = ranked.head(top_n)
    elif strategy in {"top5", "top10"}:
        n = 5 if strategy == "top5" else 10
        pick = ranked.head(n)
    else:
        raise ValueError(strategy)

    w = 1.0 / len(pick)
    return {str(r.yahoo_symbol): w for r in pick.itertuples()}


def turnover_cost(prev: dict[str, float], new: dict[str, float], cost_bps: float) -> tuple[float, float]:
    """Return (turnover, cost_fraction_of_portfolio)."""
    keys = set(prev) | set(new)
    to = sum(abs(new.get(k, 0.0) - prev.get(k, 0.0)) for k in keys)
    # One-way bps on each leg; sum |Δw| approximates both sides for a full rebalance.
    cost_frac = to * (cost_bps / 10_000.0)
    return float(to), float(cost_frac)


def portfolio_return(holdings: dict[str, float], g: pd.DataFrame) -> float:
    if not holdings:
        return 0.0
    ret_map = g.set_index("yahoo_symbol")[TARGET].to_dict()
    total = 0.0
    for sym, w in holdings.items():
        r = ret_map.get(sym)
        if r is not None and np.isfinite(r):
            total += w * float(r)
    return total


def simulate_strategy(
    preds: pd.DataFrame,
    strategy: str,
    top_n: int,
    cost_bps: float,
    initial_equity: float,
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    holdings_rows = []
    ledger_rows = []
    prev_w: dict[str, float] = {}
    equity_gross = initial_equity
    equity_net = initial_equity

    for week, g in preds.groupby("week_end"):
        w = pick_holdings(g, strategy, top_n)
        to, cost_frac = turnover_cost(prev_w, w, cost_bps)
        gross_r = portfolio_return(w, g)
        net_r = gross_r - cost_frac

        equity_gross *= 1.0 + gross_r
        equity_net *= 1.0 + net_r

        week_s = str(pd.Timestamp(week).date())
        for sym, wt in sorted(w.items()):
            holdings_rows.append(
                {
                    "week_end": week_s,
                    "strategy": strategy,
                    "yahoo_symbol": sym,
                    "weight": wt,
                    "pred_fwd_return_1w": float(
                        g.loc[g["yahoo_symbol"] == sym, "pred_fwd_return_1w"].iloc[0]
                    )
                    if sym in g["yahoo_symbol"].values
                    else float("nan"),
                    "realized_fwd_return_1w": float(
                        g.loc[g["yahoo_symbol"] == sym, TARGET].iloc[0]
                    )
                    if sym in g["yahoo_symbol"].values
                    else float("nan"),
                }
            )
        if not w:
            holdings_rows.append(
                {"week_end": week_s, "strategy": strategy, "yahoo_symbol": "CASH", "weight": 1.0,
                 "pred_fwd_return_1w": float("nan"), "realized_fwd_return_1w": 0.0}
            )

        ledger_rows.append(
            {
                "week_end": week_s,
                "strategy": strategy,
                "gross_return": gross_r,
                "net_return": net_r,
                "turnover": to,
                "cost_bps": cost_frac * 10_000,
                "equity_gross": equity_gross,
                "equity_net": equity_net,
                "n_holdings": len(w),
            }
        )
        prev_w = w

    return pd.DataFrame(holdings_rows), pd.DataFrame(ledger_rows), {}


def perf_from_ledger(ledger: pd.DataFrame, col: str, initial_equity: float = 10_000.0) -> dict:
    r = ledger[col].dropna()
    if r.empty:
        return {}
    eq = initial_equity * (1.0 + r).cumprod()
    dd = eq / eq.cummax() - 1.0
    vol = float(r.std(ddof=1))
    hz = 52
    return {
        "weeks": int(len(r)),
        "mean_weekly_pct": float(r.mean() * 100),
        "hit_rate_pct": float((r > 0).mean() * 100),
        "sharpe_weekly": float(r.mean() / vol * math.sqrt(hz)) if vol > 0 else float("nan"),
        "max_drawdown_pct": float(dd.min() * 100),
        "terminal_equity": float(eq.iloc[-1]),
        "total_return_pct": float((eq.iloc[-1] - 1.0) * 100) if len(eq) else float("nan"),
        "avg_turnover": float(ledger["turnover"].mean()),
        "avg_cost_bps": float(ledger["cost_bps"].mean()),
    }


def split_ledger(ledger: pd.DataFrame, oos_start: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    cut = pd.Timestamp(oos_start)
    ledger = ledger.copy()
    ledger["week_end"] = pd.to_datetime(ledger["week_end"])
    return ledger[ledger["week_end"] < cut], ledger[ledger["week_end"] >= cut]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--min-train-weeks", type=int, default=78)
    ap.add_argument("--ridge-alpha", type=float, default=10.0)
    ap.add_argument("--top-n", type=int, default=5, help="Names for top5_cash_flat custom top-N")
    ap.add_argument("--cost-bps", type=float, default=25.0, help="Per-leg spread+commission bps (.JK emerging)")
    ap.add_argument("--initial-equity", type=float, default=10_000.0)
    ap.add_argument("--oos-frac", type=float, default=0.25, help="Holdout fraction for OOS split (default last 25%%)")
    ap.add_argument("--oos-start", default=None, help="Optional explicit OOS start date (overrides --oos-frac)")
    ap.add_argument(
        "--strategies",
        default="liquid_eq,top5,top10,top5_cash_flat,bbca_hold",
        help="Comma-separated strategy keys",
    )
    args = ap.parse_args()

    universe = load_liquid_universe()
    print(f"Universe: indonesia_liquid_core ({len(universe)} names)")
    print(f"  e.g. {', '.join(universe[:8])} …")

    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    cache = OUT_ROOT / "_latest_preds_cache.csv"
    if cache.exists() and cache.stat().st_mtime > (datetime.now().timestamp() - 86400):
        print(f"Loading cached predictions from {cache}")
        preds = pd.read_csv(cache, parse_dates=["week_end"])
    else:
        print("Running walk-forward per ticker (this takes a few minutes)…")
        preds = walkforward_predictions(universe, args.min_train_weeks, args.ridge_alpha)
        preds.to_csv(cache, index=False)

    if args.oos_start:
        oos_start = args.oos_start
    else:
        from idn_eval_splits import time_cutoff

        oos_start = str(time_cutoff(preds["week_end"]).date())

    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_dir = OUT_ROOT / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    strategies = [s.strip() for s in args.strategies.split(",") if s.strip()]
    summaries = []
    all_ledger = []
    latest_week = str(pd.to_datetime(preds["week_end"]).max().date())

    for strat in strategies:
        holdings, ledger, _ = simulate_strategy(
            preds, strat, args.top_n, args.cost_bps, args.initial_equity
        )
        holdings.to_csv(out_dir / f"holdings_{strat}.csv", index=False)
        ledger.to_csv(out_dir / f"ledger_{strat}.csv", index=False)
        all_ledger.append(ledger)

        is_l, oos_l = split_ledger(ledger, oos_start)
        for sample, sub in [("full", ledger), ("train", is_l), ("oos_holdout", oos_l)]:
            if sub.empty:
                continue
            summaries.append(
                {
                    "strategy": strat,
                    "sample": sample,
                    "gross": perf_from_ledger(sub, "gross_return", args.initial_equity),
                    "net": perf_from_ledger(sub, "net_return", args.initial_equity),
                }
            )

        # Latest portfolio for paper tracking
        last_h = holdings[holdings["week_end"] == latest_week]
        if not last_h.empty:
            weights = {
                r["yahoo_symbol"]: float(r["weight"])
                for _, r in last_h.iterrows()
                if r["yahoo_symbol"] != "CASH"
            }
            if not weights and (last_h["yahoo_symbol"] == "CASH").any():
                weights = {"CASH": 1.0}
            port = {
                "as_of_week": latest_week,
                "strategy": strat,
                "country": "IDN",
                "universe": "indonesia_liquid_core",
                "weights": weights,
                "cost_bps_assumed": args.cost_bps,
            }
            (out_dir / f"latest_portfolio_{strat}.json").write_text(
                json.dumps(port, indent=2), encoding="utf-8"
            )

    (out_dir / "strategy_summary.json").write_text(json.dumps(summaries, indent=2), encoding="utf-8")
    (out_dir / "universe.json").write_text(json.dumps(universe, indent=2), encoding="utf-8")

    # Console table — OOS net returns
    print(f"\n=== OOS from {args.oos_start} (net of {args.cost_bps}bps/leg) ===")
    print(f"{'strategy':18} | {'wk%':>6} | {'hit%':>4} | {'sharpe':>6} | {'maxDD':>6} | {'$10k→':>8} | {'avg to':>6}")
    print("-" * 75)
    for row in summaries:
        if row["sample"] != "oos_from2024":
            continue
        n = row["net"]
        if not n:
            continue
        print(
            f"{row['strategy']:18} | {n['mean_weekly_pct']:+5.2f}% | {n['hit_rate_pct']:4.0f}% | "
            f"{n['sharpe_weekly']:6.2f} | {n['max_drawdown_pct']:5.1f}% | "
            f"${n['terminal_equity']:7.0f} | {n['avg_turnover']:6.2f}"
        )

    # Show last week top5 picks
    top_h = pd.read_csv(out_dir / "holdings_top5.csv")
    last = top_h[top_h["week_end"] == latest_week]
    print(f"\n=== Last rebalance ({latest_week}) — top5 picks ===")
    if last.empty:
        print("  (no holdings)")
    else:
        for _, r in last.iterrows():
            pred = r["pred_fwd_return_1w"]
            pred_s = f"{pred:+.3f}" if np.isfinite(pred) else "n/a"
            print(f"  {r['yahoo_symbol']:10} weight={r['weight']:.1%}  pred_1w={pred_s}")

    print(f"\nWrote {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
