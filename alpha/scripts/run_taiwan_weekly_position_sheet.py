#!/usr/bin/env python3
"""Weekly Taiwan position sheet — regime + semi core + momentum tilt.

Built for investable TWSE large-caps (not global beta). Uses fresh
yfinance taiwan_expanded panel; optional group_sync across semi/EMS.

Example:
  python scripts/run_taiwan_weekly_position_sheet.py
  python scripts/idn_paper_tracker.py \\
    --portfolio backtests/outputs/taiwan_weekly_position_sheet/latest_portfolio.json \\
    --ledger backtests/outputs/taiwan_weekly_position_sheet/paper/ledger.csv \\
    --moves-out backtests/outputs/taiwan_weekly_position_sheet/paper/recent_moves.json
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

PANEL = REPO / "data_lake/markets/yfinance_asia/taiwan_expanded_daily_panel.parquet"
PANEL_PULL = REPO / "data_lake/markets/yfinance_asia/research_pull_20260718/taiwan_expanded_core.parquet"
GROUPS = REPO / "config/markets/taiwan_stock_groups.json"
OUT = REPO / "backtests/outputs/taiwan_weekly_position_sheet"

DEFAULT_MAX_SINGLE = 0.25
DEFAULT_CASH_FLOOR = 0.15


def _load_groups() -> dict[str, Any]:
    return json.loads(GROUPS.read_text(encoding="utf-8"))


def load_close_vol() -> tuple[pd.DataFrame, pd.DataFrame]:
    path = PANEL if PANEL.exists() else PANEL_PULL
    if not path.exists():
        raise SystemExit(f"missing Taiwan panel: {path}")
    df = pd.read_parquet(path)
    cols = {c.lower(): c for c in df.columns}
    if "instrument" in cols:
        inst, date, close, vol = cols["instrument"], cols["date"], cols.get("close") or cols.get("price_close"), cols.get("volume")
        long = pd.DataFrame({
            "symbol": df[inst].astype(str),
            "date": pd.to_datetime(df[date]),
            "close": pd.to_numeric(df[close], errors="coerce"),
            "volume": pd.to_numeric(df[vol], errors="coerce") if vol else np.nan,
        }).dropna(subset=["symbol", "date", "close"])
    elif list(df.index.names) == ["date", "symbol"] or (isinstance(df.index, pd.MultiIndex)):
        long = df.reset_index()
        long = long.rename(columns={c: c.lower() for c in long.columns})
    else:
        raise SystemExit(f"unrecognized panel schema: {list(df.columns)} idx={df.index.names}")
    close = long.pivot_table(index="date", columns="symbol", values="close", aggfunc="last").sort_index()
    vol = long.pivot_table(index="date", columns="symbol", values="volume", aggfunc="last").sort_index()
    return close, vol



def _tw_proof_boost() -> bool:
    proof = REPO / "backtests/outputs/taiwan_alpha_research/latest.json"
    if not proof.exists():
        return False
    try:
        data = json.loads(proof.read_text(encoding="utf-8"))
    except Exception:
        return False
    return str(data.get("verdict") or "").startswith("candidate") and "group_sync" in str(data.get("best_strategy") or "")


def regime_state(bench: pd.Series) -> dict[str, Any]:
    s = bench.dropna()
    if len(s) < 80:
        return {"label": "neutral", "core_sleeve_pct": 0.45, "action": "standard", "dd_63": None, "bounce_20": None}
    last = float(s.iloc[-1])
    dd_63 = last / float(s.iloc[-63:].max()) - 1.0
    bounce_20 = last / float(s.iloc[-20:].min()) - 1.0
    ret_5 = last / float(s.iloc[-6]) - 1.0 if len(s) >= 6 else 0.0
    if dd_63 <= -0.10 and bounce_20 < 0.08:
        label, core, action = "washout", 0.55, "ADD core / semis — washout"
    elif dd_63 <= -0.10 and bounce_20 >= 0.08:
        label, core, action = "recovery", 0.45, "HOLD core — recovery, don't chase"
    elif bounce_20 >= 0.12 and ret_5 >= 0.05:
        label, core, action = "extended", 0.25, "TRIM — extended; raise cash"
    else:
        label, core, action = "neutral", 0.40, "standard"
    return {
        "label": label,
        "core_sleeve_pct": core,
        "action": action,
        "dd_63": round(dd_63 * 100, 2),
        "bounce_20": round(bounce_20 * 100, 2),
        "ret_5d": round(ret_5 * 100, 2),
        "benchmark": str(bench.name) if bench.name else "benchmark",
    }


def momentum_top(close: pd.DataFrame, lookback: int = 63, top_n: int = 5) -> list[str]:
    if len(close) < lookback + 5:
        return []
    window = close.iloc[-lookback:]
    mom = (window.iloc[-1] / window.iloc[0] - 1.0).replace([np.inf, -np.inf], np.nan).dropna()
    return mom.sort_values(ascending=False).head(top_n).index.astype(str).tolist()


def group_sync_hits(close: pd.DataFrame, groups: dict[str, Any], lookback_days: int = 5) -> list[dict]:
    rets = close.pct_change()
    dates = close.index[-lookback_days:]
    hits: list[dict] = []
    for gname, g in (groups.get("groups") or {}).items():
        tickers = [t for t in g.get("tickers", []) if t in close.columns]
        for dt in dates:
            up = []
            for t in tickers:
                if dt not in rets.index or t not in rets.columns:
                    continue
                r = float(rets.loc[dt, t])
                if r >= 0.08:
                    up.append((t, r))
            if len(up) >= 2:
                up = sorted(up, key=lambda x: -x[1])
                hits.append({
                    "date": str(pd.Timestamp(dt).date()),
                    "group": gname,
                    "symbol": up[0][0],
                    "return_pct": round(up[0][1] * 100, 1),
                    "n_peers": len(up),
                })
    return sorted(hits, key=lambda x: (x["date"], x["return_pct"]), reverse=True)


def build_weights(
    close: pd.DataFrame,
    *,
    regime: dict[str, Any],
    groups: dict[str, Any],
    max_single: float,
    cash_floor: float,
) -> tuple[dict[str, float], dict[str, str], str]:
    w: dict[str, float] = {}
    why: dict[str, str] = {}
    core = [t for t in groups.get("liquid_core", []) if t in close.columns]
    semis = [t for t in (groups.get("groups", {}).get("semiconductors", {}) or {}).get("tickers", []) if t in close.columns]
    label = regime["label"]
    core_pct = float(regime["core_sleeve_pct"])
    tilt_pct = 0.25 if label in ("washout", "recovery", "neutral") else 0.12
    sync_pct = (0.15 if _tw_proof_boost() else 0.10) if label != "extended" else 0.0
    cash = max(cash_floor, 1.0 - core_pct - tilt_pct - sync_pct)

    # Core: blend liquid_core + semis on washout/recovery
    if label in ("washout", "recovery"):
        sleeve = list(dict.fromkeys(core[:4] + semis[:3]))
    else:
        sleeve = core[:5] or semis[:4]
    if not sleeve:
        sleeve = list(close.columns[:8])
    per = core_pct / len(sleeve)
    for t in sleeve:
        w[t] = per
        why[t] = f"core:{label}"

    # Momentum tilt
    moms = [t for t in momentum_top(close, 63, 5) if t not in w]
    if moms and tilt_pct > 0:
        per_m = tilt_pct / len(moms)
        for t in moms:
            w[t] = w.get(t, 0.0) + per_m
            why[t] = why.get(t, "") + (" + " if t in why else "") + "mom63_tilt"

    # Group sync tactical
    hits = group_sync_hits(close, groups)
    if hits and sync_pct > 0:
        names = []
        for h in hits:
            if h["symbol"] not in names:
                names.append(h["symbol"])
            if len(names) >= 2:
                break
        per_s = sync_pct / len(names)
        for t in names:
            w[t] = w.get(t, 0.0) + per_s
            why[t] = why.get(t, "") + (" + " if t in why else "") + "group_sync"

    w["CASH"] = cash
    why["CASH"] = regime.get("action", "cash_floor")

    # Cap single name
    for k in list(w):
        if k == "CASH":
            continue
        if w[k] > max_single:
            overflow = w[k] - max_single
            w[k] = max_single
            w["CASH"] = w.get("CASH", 0.0) + overflow
            why[k] = why.get(k, "") + " (capped)"

    # Renormalize
    total = sum(w.values())
    if total > 0:
        w = {k: float(v) / total for k, v in w.items()}
    mode = f"taiwan_{label}"
    return w, why, mode


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--max-single-name-weight", type=float, default=DEFAULT_MAX_SINGLE)
    ap.add_argument("--cash-floor", type=float, default=DEFAULT_CASH_FLOOR)
    args = ap.parse_args()

    close, vol = load_close_vol()
    groups = _load_groups()
    bench_name = groups.get("benchmark_etf", "0050.TW")
    if bench_name in close.columns:
        bench = close[bench_name].copy()
        bench.name = bench_name
    elif "2330.TW" in close.columns:
        bench = close["2330.TW"].copy()
        bench.name = "2330.TW"
    else:
        bench = close.mean(axis=1)
        bench.name = "equal_weight_proxy"

    regime = regime_state(bench)
    weights, rationale, mode = build_weights(
        close,
        regime=regime,
        groups=groups,
        max_single=float(args.max_single_name_weight),
        cash_floor=float(args.cash_floor),
    )
    as_of = str(close.index[-1].date())
    sync = group_sync_hits(close, groups)[:8]
    moms = momentum_top(close, 63, 8)

    report = {
        "strategy": "taiwan_weekly_position_sheet",
        "as_of_week": as_of,
        "as_of": as_of,
        "weight_mode": mode,
        "regime": regime,
        "weights": weights,
        "rationale": rationale,
        "momentum_top": moms,
        "group_sync_hits": sync,
        "max_single_name_weight": float(args.max_single_name_weight),
        "cash_floor": float(args.cash_floor),
        "panel": str(PANEL if PANEL.exists() else PANEL_PULL),
        "n_instruments": int(close.shape[1]),
        "generated_at_utc": datetime.now(UTC).isoformat(),
    }

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "latest_portfolio.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (OUT / "latest.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Taiwan weekly position sheet",
        "",
        f"- as_of: `{as_of}` · mode: `{mode}` · regime: **{regime['label']}**",
        f"- dd63={regime.get('dd_63')}% bounce20={regime.get('bounce_20')}% ret5={regime.get('ret_5d')}%",
        f"- action: {regime.get('action')}",
        "",
        "## Weights",
        "",
        "| Symbol | Weight | Why |",
        "|--------|-------:|-----|",
    ]
    for sym, wt in sorted(weights.items(), key=lambda x: -x[1]):
        lines.append(f"| {sym} | {wt:.1%} | {rationale.get(sym, '')} |")
    lines += ["", "## Momentum top (63d)", ", ".join(moms) or "—", "", "## Recent group_sync", ""]
    if sync:
        for h in sync[:6]:
            lines.append(f"- {h['date']} `{h['symbol']}` {h['group']} +{h['return_pct']}% ({h['n_peers']} peers)")
    else:
        lines.append("- none in lookback")
    lines.append("")
    (OUT / "latest.md").write_text("\n".join(lines), encoding="utf-8")
    print((OUT / "latest.md").read_text(encoding="utf-8"))
    print(f"Wrote {OUT / 'latest_portfolio.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
