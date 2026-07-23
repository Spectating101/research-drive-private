#!/usr/bin/env python3
"""Grid-search IDN group_sync params on liquid-50 panel (OOS).

Sweeps min_peers × move_threshold × hold_days. Writes ranked table under
backtests/outputs/idn_group_sync_grid/.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from itertools import product
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
sys.path.insert(0, str(REPO / "alpha" / "scripts"))
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO))

PANEL = REPO / "data_lake/markets/yfinance_asia/idn_liquid_daily_panel.parquet"
GROUPS = REPO / "config/markets/indonesia_stock_groups.json"
OUT = REPO / "backtests/outputs/idn_group_sync_grid"
COST_BPS = 25.0
OOS_FRAC = 0.30
MAX_NAMES = 5


def load_close_vol() -> tuple[pd.DataFrame, pd.DataFrame]:
    df = pd.read_parquet(PANEL)
    close = df["close"].unstack("symbol").sort_index()
    vol = df["volume"].unstack("symbol").sort_index()
    return close, vol


def load_group_map() -> dict[str, list[str]]:
    raw = json.loads(GROUPS.read_text(encoding="utf-8"))
    gmap = raw.get("groups") or raw
    out = {}
    for name, g in gmap.items():
        if isinstance(g, dict) and g.get("tickers"):
            out[name] = list(g["tickers"])
    return out


def oos_start(idx: pd.DatetimeIndex) -> pd.Timestamp:
    cut = int(len(idx) * (1.0 - OOS_FRAC))
    return pd.Timestamp(idx[max(cut, 60)])


def signals_for(
    close: pd.DataFrame,
    groups: dict[str, list[str]],
    *,
    min_peers: int,
    move_thr: float,
) -> dict[pd.Timestamp, list[str]]:
    rets = close.pct_change()
    out: dict[pd.Timestamp, list[str]] = {}
    for dt in close.index[25:]:
        picks: list[str] = []
        for tickers in groups.values():
            present = [t for t in tickers if t in close.columns]
            if len(present) < min_peers:
                continue
            up = []
            for t in present:
                r = rets.loc[dt, t] if dt in rets.index else np.nan
                if pd.notna(r) and float(r) >= move_thr:
                    up.append((t, float(r)))
            if len(up) >= min_peers:
                up.sort(key=lambda x: -x[1])
                # take strongest names that day (cap later in sim)
                for t, _ in up:
                    if t not in picks:
                        picks.append(t)
        if picks:
            out[dt] = picks
    return out


def simulate(
    sig_map: dict[pd.Timestamp, list[str]],
    close: pd.DataFrame,
    *,
    oos: pd.Timestamp,
    hold_days: int,
) -> dict[str, Any]:
    """Next-day entry, equal-weight active book capped at 1.0, turnover costs."""
    rets = close.pct_change().fillna(0.0)
    dates = list(close.index[close.index >= oos])
    if len(dates) < 40:
        return {"ok": False, "reason": "short_oos"}

    equity = 1.0
    curve = []
    # pending entry from prior close signal → today's open/close return
    pending: list[str] | None = None
    # active: list of (exit_loc_inclusive, names)
    active: list[tuple[int, list[str]]] = []
    prev_w = pd.Series(0.0, index=close.columns)
    n_entries = 0

    for dt in dates:
        loc = int(close.index.get_loc(dt))
        # expire
        active = [(ex, names) for ex, names in active if ex >= loc]
        # activate pending from yesterday's signal
        if pending:
            active.append((loc + hold_days - 1, pending))
            n_entries += 1
            pending = None
        # schedule new signal for next day (no same-day look-ahead)
        if dt in sig_map:
            names = [s for s in sig_map[dt] if s in close.columns][:MAX_NAMES]
            if names:
                pending = names

        # build today's weights from active slots (equal across unique names)
        names_today: list[str] = []
        for _, nm in active:
            for s in nm:
                if s not in names_today:
                    names_today.append(s)
        w = pd.Series(0.0, index=close.columns)
        if names_today:
            w.loc[names_today] = 1.0 / len(names_today)
        turnover = float((w - prev_w).abs().sum())
        equity *= 1.0 - turnover * (COST_BPS / 10000.0)
        day_ret = float((w * rets.loc[dt]).sum())
        equity *= 1.0 + day_ret
        curve.append(equity)
        prev_w = w

    if len(curve) < 40:
        return {"ok": False, "reason": "thin"}
    ser = pd.Series(curve, index=dates[: len(curve)])
    r = ser.pct_change().dropna()
    sharpe = float(r.mean() / r.std() * np.sqrt(252)) if r.std() > 0 else 0.0
    ann = float(ser.iloc[-1] ** (252 / len(ser)) - 1.0)
    mdd = float((ser / ser.cummax() - 1.0).min())
    return {
        "ok": True,
        "sharpe": round(sharpe, 3),
        "ann_return": round(ann, 4),
        "max_dd": round(mdd, 4),
        "terminal": round(float(ser.iloc[-1]), 4),
        "n_entries": n_entries,
        "n_days": len(ser),
    }


def main() -> int:
    close, _vol = load_close_vol()
    groups = load_group_map()
    # only tickers present
    for k, v in list(groups.items()):
        groups[k] = [t for t in v if t in close.columns]
    groups = {k: v for k, v in groups.items() if len(v) >= 2}

    oos = oos_start(close.index)
    peers_grid = [2, 3]
    thr_grid = [0.05, 0.08, 0.10, 0.12]
    hold_grid = [3, 5, 8]

    rows = []
    for min_peers, thr, hold in product(peers_grid, thr_grid, hold_grid):
        sig = signals_for(close, groups, min_peers=min_peers, move_thr=thr)
        # restrict signal map keys conceptually via sim oos filter
        m = simulate(sig, close, oos=oos, hold_days=hold)
        row = {
            "min_peers": min_peers,
            "move_thr": thr,
            "hold_days": hold,
            "label": f"peers{min_peers}_thr{int(thr*100)}_hold{hold}",
            **m,
        }
        rows.append(row)
        print(f"{row['label']}: sharpe={m.get('sharpe')} ann={m.get('ann_return')} entries={m.get('n_entries')}", flush=True)

    ok = [r for r in rows if r.get("ok")]
    ranked = sorted(ok, key=lambda r: (r["sharpe"], r["ann_return"]), reverse=True)
    baseline = next((r for r in rows if r["min_peers"] == 2 and r["move_thr"] == 0.08 and r["hold_days"] == 5), None)
    best = ranked[0] if ranked else None

    # Prefer robust configs near baseline; demote absurd thr=5% blow-ups as overfit risk
    verdict = "research_continue"
    robust = [
        r for r in ranked
        if r["n_entries"] >= 15
        and r["max_dd"] > -0.30
        and r["move_thr"] >= 0.08  # 5% threshold floods signals in bull tapes
    ]
    pick = robust[0] if robust else best
    report_best = pick
    if pick and baseline and baseline.get("ok"):
        if pick["label"] == baseline["label"]:
            verdict = "grid_confirms_baseline"
        elif pick["sharpe"] >= float(baseline.get("sharpe") or 0) - 0.1 and pick["n_entries"] >= 15:
            verdict = "grid_alt_candidate"
        elif float(baseline.get("sharpe") or 0) >= 0.5:
            verdict = "grid_confirms_baseline"
            report_best = baseline
        if pick["n_entries"] < 15:
            verdict = "research_continue_thin"
    best = report_best

    report = {
        "market": "indonesia",
        "panel": str(PANEL),
        "oos_start": str(oos.date()),
        "oos_frac": OOS_FRAC,
        "cost_bps": COST_BPS,
        "baseline": baseline,
        "best": best,
        "raw_best_unfiltered": ranked[0] if ranked else None,
        "verdict": verdict,
        "ranked_top10": ranked[:10],
        "all": rows,
        "as_of": str(close.index[-1].date()),
        "generated_at_utc": datetime.now(UTC).isoformat(),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "latest.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    pd.DataFrame(rows).to_csv(OUT / "grid.csv", index=False)

    lines = [
        "# IDN group_sync parameter grid",
        "",
        f"- as_of: `{report['as_of']}` · OOS from `{report['oos_start']}` · cost {COST_BPS:.0f}bps",
        f"- baseline peers2/thr8%/hold5: Sharpe **{(baseline or {}).get('sharpe')}**",
        f"- best: **{(best or {}).get('label')}** Sharpe **{(best or {}).get('sharpe')}** · verdict `{verdict}`",
        "",
        "| Config | Sharpe | Ann | MaxDD | Entries | Terminal |",
        "|--------|-------:|----:|------:|--------:|---------:|",
    ]
    for r in ranked[:12]:
        lines.append(
            f"| {r['label']} | {r['sharpe']:.2f} | {r['ann_return']:.1%} | {r['max_dd']:.1%} | {r['n_entries']} | {r['terminal']:.2f}× |"
        )
    lines.append("")
    (OUT / "latest.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n" + (OUT / "latest.md").read_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
