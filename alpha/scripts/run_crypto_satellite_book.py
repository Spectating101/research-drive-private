#!/usr/bin/env python3
"""Capped crypto satellite book for personal IDN+TW+crypto universe.

Research + actionable weights (max 10% of total book by default).
Strategies horse-raced OOS; best sleeve becomes the paper weights.

Example:
  python scripts/run_crypto_satellite_book.py
  python scripts/run_crypto_satellite_book.py --book-cap 0.10
"""

from __future__ import annotations

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

CSV = REPO / "data_lake/markets/crypto_majors_10y_20260718.csv"
OUT = REPO / "backtests/outputs/crypto_satellite_book"

# Majors only — no meme satellite
DEFAULT_UNIVERSE = ["BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "XRP-USD", "ADA-USD", "AVAX-USD", "DOT-USD"]
COST_BPS = 15.0  # round-trip-ish daily turnover cost proxy


def load_panel() -> pd.DataFrame:
    if not CSV.exists():
        raise SystemExit(f"missing {CSV}")
    df = pd.read_csv(CSV)
    cols = {c.lower(): c for c in df.columns}
    # expect Date + ticker columns or long form
    # Long tidy: Instrument/Date/Price_Close or symbol/date/close
    if "date" in cols and ("close" in cols or "price_close" in cols):
        sym = cols.get("symbol") or cols.get("ticker") or cols.get("instrument")
        close_c = cols.get("close") or cols.get("price_close")
        if not sym:
            raise SystemExit(f"no symbol column in {list(df.columns)}")
        long = pd.DataFrame({
            "date": pd.to_datetime(df[cols["date"]]),
            "symbol": df[sym].astype(str),
            "close": pd.to_numeric(df[close_c], errors="coerce"),
        }).dropna()
        close = long.pivot_table(index="date", columns="symbol", values="close", aggfunc="last").sort_index()
    else:
        date_col = cols.get("date") or cols.get("datetime") or df.columns[0]
        close = df.set_index(pd.to_datetime(df[date_col]))
        close = close.drop(columns=[date_col], errors="ignore")
        close = close.apply(pd.to_numeric, errors="coerce").sort_index()
    # keep universe intersection
    keep = [c for c in DEFAULT_UNIVERSE if c in close.columns]
    if not keep:
        keep = [c for c in close.columns if str(c).endswith("-USD")][:8]
    return close[keep].dropna(how="all")


def turnover_cost(prev: pd.Series, cur: pd.Series, bps: float = COST_BPS) -> float:
    idx = prev.index.union(cur.index)
    p = prev.reindex(idx).fillna(0.0)
    c = cur.reindex(idx).fillna(0.0)
    return float((p - c).abs().sum()) * (bps / 10000.0)


def backtest(weights_fn, close: pd.DataFrame, oos_start: str) -> dict[str, Any]:
    rets = close.pct_change().fillna(0.0)
    dates = close.index
    oos = dates[dates >= pd.Timestamp(oos_start)]
    if len(oos) < 60:
        return {"ok": False, "reason": "short_oos"}
    equity = 1.0
    curve = []
    prev_w = pd.Series(0.0, index=close.columns)
    w = None
    # Prior-close weights → next-day return (no same-day look-ahead)
    for i, dt in enumerate(oos):
        if w is not None:
            day_ret = float((w * rets.loc[dt]).sum())
            equity *= 1.0 + day_ret
            curve.append(equity)
        hist = close.loc[:dt]
        if len(hist) < 90:
            w = None
            continue
        new_w = weights_fn(hist).reindex(close.columns).fillna(0.0)
        s = float(new_w.sum())
        if s > 0:
            new_w = new_w / s
        if w is not None:
            equity *= 1.0 - turnover_cost(prev_w, new_w)
        prev_w = new_w
        w = new_w
    if len(curve) < 40:
        return {"ok": False, "reason": "thin_curve"}
    ser = pd.Series(curve)
    rets_e = ser.pct_change().dropna()
    sharpe = float(rets_e.mean() / rets_e.std() * np.sqrt(365)) if rets_e.std() > 0 else 0.0
    ann = float(ser.iloc[-1] ** (365 / len(ser)) - 1.0)
    peak = ser.cummax()
    mdd = float((ser / peak - 1.0).min())
    return {
        "ok": True,
        "sharpe": round(sharpe, 3),
        "ann_return": round(ann, 4),
        "max_dd": round(mdd, 4),
        "terminal": round(float(ser.iloc[-1]), 4),
        "n_days": len(ser),
        "oos_start": oos_start,
    }


def w_equal(hist: pd.DataFrame) -> pd.Series:
    return pd.Series(1.0 / hist.shape[1], index=hist.columns)


def w_mom20(hist: pd.DataFrame) -> pd.Series:
    if len(hist) < 25:
        return w_equal(hist)
    mom = hist.iloc[-1] / hist.iloc[-21] - 1.0
    mom = mom.replace([np.inf, -np.inf], np.nan).fillna(-1)
    top = mom.nlargest(3).index
    w = pd.Series(0.0, index=hist.columns)
    w.loc[top] = 1.0 / len(top)
    return w


def w_btc_core_eth_satellite(hist: pd.DataFrame) -> pd.Series:
    w = pd.Series(0.0, index=hist.columns)
    if "BTC-USD" in w.index:
        w["BTC-USD"] = 0.70
    if "ETH-USD" in w.index:
        w["ETH-USD"] = 0.30
    if w.sum() == 0:
        return w_equal(hist)
    return w


def w_vol_target_btc_eth(hist: pd.DataFrame, target_vol: float = 0.40) -> pd.Series:
    """60/40 BTC/ETH vol-scaled vs trailing 30d realized."""
    base = w_btc_core_eth_satellite(hist)
    sub = hist[[c for c in base.index if base[c] > 0]].pct_change().dropna()
    if len(sub) < 40:
        return base
    port = (sub * base[sub.columns]).sum(axis=1)
    rv = float(port.iloc[-30:].std() * np.sqrt(365))
    if rv <= 0:
        return base
    scale = min(1.0, target_vol / rv)
    return base * scale  # remainder implicit cash when used as satellite cap


def w_regime_btc(hist: pd.DataFrame) -> pd.Series:
    """Risk-on when BTC above 200d MA; else cash (zeros)."""
    w = pd.Series(0.0, index=hist.columns)
    if "BTC-USD" not in hist.columns or len(hist) < 210:
        return w_btc_core_eth_satellite(hist)
    btc = hist["BTC-USD"].dropna()
    ma = btc.rolling(200).mean().iloc[-1]
    last = btc.iloc[-1]
    if last >= ma:
        w["BTC-USD"] = 0.65
        if "ETH-USD" in w.index:
            w["ETH-USD"] = 0.35
    # else all cash (zeros)
    return w


def latest_weights(close: pd.DataFrame, name: str) -> dict[str, float]:
    fns = {
        "equal": w_equal,
        "mom20_top3": w_mom20,
        "btc70_eth30": w_btc_core_eth_satellite,
        "vol_target_btc_eth": w_vol_target_btc_eth,
        "regime_btc_200ma": w_regime_btc,
    }
    w = fns[name](close)
    w = w[w > 0]
    s = float(w.sum())
    if s <= 0:
        return {"CASH": 1.0}
    w = w / s
    return {str(k): float(v) for k, v in w.items()}


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--book-cap", type=float, default=0.10, help="Max fraction of total personal book")
    ap.add_argument("--oos-start", default="2024-01-01")
    args = ap.parse_args()

    close = load_panel()
    strats = {
        "equal": w_equal,
        "mom20_top3": w_mom20,
        "btc70_eth30": w_btc_core_eth_satellite,
        "vol_target_btc_eth": w_vol_target_btc_eth,
        "regime_btc_200ma": w_regime_btc,
    }
    results = {}
    for name, fn in strats.items():
        results[name] = backtest(fn, close, args.oos_start)

    ranked = sorted(
        [(k, v) for k, v in results.items() if v.get("ok")],
        key=lambda x: (x[1]["sharpe"], x[1]["ann_return"]),
        reverse=True,
    )
    best = ranked[0][0] if ranked else "btc70_eth30"
    best_m = results.get(best, {})
    verdict = "candidate_satellite" if best_m.get("ok") and best_m.get("sharpe", 0) >= 0.5 else "research_only"
    if best_m.get("max_dd", 0) < -0.55:
        verdict = "research_only_high_dd"

    raw = latest_weights(close, best)
    # Scale into book_cap; rest cash at satellite layer (caller mixes into total book)
    scaled = {k: float(v) * float(args.book_cap) for k, v in raw.items() if k != "CASH"}
    cash = 1.0 - sum(scaled.values())
    scaled["CASH"] = cash  # within satellite sleeve framing: CASH means "not in crypto"

    report = {
        "strategy": "crypto_satellite_book",
        "as_of": str(close.index[-1].date()),
        "book_cap": float(args.book_cap),
        "best_strategy": best,
        "verdict": verdict,
        "horse_race": results,
        "ranked": [k for k, _ in ranked],
        "weights_within_satellite": raw,
        "weights_in_total_book": scaled,
        "note": "weights_in_total_book already scaled by book_cap; CASH is non-crypto residual of the 100% book view",
        "universe": list(close.columns.astype(str)),
        "panel": str(CSV),
        "generated_at_utc": datetime.now(UTC).isoformat(),
    }

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "latest.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (OUT / "latest_portfolio.json").write_text(json.dumps({
        "strategy": "crypto_satellite",
        "as_of_week": report["as_of"],
        "as_of": report["as_of"],
        "weight_mode": f"crypto_{best}",
        "weights": scaled,
        "rationale": {k: f"{best} @ book_cap={args.book_cap}" for k in scaled if k != "CASH"} | {"CASH": "non-crypto residual"},
        "verdict": verdict,
        "horse_race_best": best_m,
    }, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Crypto satellite book",
        "",
        f"- as_of: `{report['as_of']}` · best: **{best}** · verdict: `{verdict}`",
        f"- book_cap: {args.book_cap:.0%} (personal book ceiling)",
        "",
        "## Horse race (OOS)",
        "",
        "| Strategy | Sharpe | Ann | MaxDD | Terminal |",
        "|----------|-------:|----:|------:|---------:|",
    ]
    for name, m in sorted(results.items(), key=lambda x: -(x[1].get("sharpe") or -99)):
        if not m.get("ok"):
            lines.append(f"| {name} | — | — | — | {m.get('reason')} |")
        else:
            lines.append(f"| {name} | {m['sharpe']:.2f} | {m['ann_return']:.1%} | {m['max_dd']:.1%} | {m['terminal']:.2f}× |")
    lines += ["", "## Weights in total book", ""]
    for k, v in sorted(scaled.items(), key=lambda x: -x[1]):
        lines.append(f"- `{k}`: {v:.1%}")
    lines.append("")
    (OUT / "latest.md").write_text("\n".join(lines), encoding="utf-8")
    print((OUT / "latest.md").read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
