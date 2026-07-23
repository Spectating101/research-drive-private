#!/usr/bin/env python3
"""Mine recurring patterns across IDX +10% spike days (liquid universe).

Classifies each spike session, aggregates pattern frequencies, and tests whether
pattern flags have any *next-week* predictability (usually weak).

Output: backtests/outputs/idn_spike_explainer/pattern_mining_latest.json
"""

from __future__ import annotations

import json
import sys
from collections import Counter
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
sys.path.insert(0, str(REPO / "scripts"))

from idn_bandar_lite import bandar_lite_features  # noqa: E402
from idn_spike_explainer import (  # noqa: E402
    classify_ara,
    fetch_history,
    index_events_for,
    load_groups,
    load_universe,
    peer_moves,
    volume_ratio,
)

OUT = REPO / "backtests/outputs/idn_spike_explainer"
MIN_PCT = 10.0
START = "2022-01-01"


def classify_spike_row(
    symbol: str,
    dt: pd.Timestamp,
    ret: float,
    px: pd.DataFrame,
    vol_px: pd.DataFrame,
) -> dict:
    loc = px.index.get_loc(dt)
    prev = px.index[loc - 1] if loc > 0 else dt
    mom5 = float(px.loc[dt, symbol] / px.loc[px.index[max(0, loc - 5)], symbol] - 1.0) if loc >= 5 else np.nan
    mom20 = float(px.loc[dt, symbol] / px.loc[px.index[max(0, loc - 20)], symbol] - 1.0) if loc >= 20 else np.nan
    vol_today = float(vol_px.loc[dt, symbol]) if symbol in vol_px.columns else np.nan
    vol_hist = vol_px[symbol].iloc[max(0, loc - 20) : loc] if symbol in vol_px.columns else pd.Series(dtype=float)
    vr = volume_ratio(vol_today, vol_hist)

    tags: list[str] = []
    ara = classify_ara(ret)
    if ara:
        tags.append("ara_limit")
    if mom5 < -0.08:
        tags.append("after_5d_drawdown")
    elif mom5 > 0.15:
        tags.append("after_5d_rally")
    if mom20 < -0.15:
        tags.append("after_20d_drawdown")
    if vr >= 3.0:
        tags.append("volume_3x")
    elif vr >= 2.0:
        tags.append("volume_2x")

    peers = peer_moves(symbol, dt, px, min_pct=0.08)
    n_peers = len(peers[0]["peers_up"]) if peers else 0
    if n_peers >= 2:
        tags.append("group_sync_2plus")
    if n_peers >= 1:
        tags.append("group_sync_1plus")

    idx_ev = index_events_for(symbol, dt)
    if any(e.get("symbol_listed_in_event") for e in idx_ev):
        tags.append("index_event_symbol")
    elif idx_ev:
        tags.append("index_event_window")

    bl = bandar_lite_features(px[symbol], vol_px[symbol] if symbol in vol_px.columns else pd.Series(dtype=float), dt)
    if bl.get("available") and bl.get("primary_label"):
        tags.append(f"bandar_lite_{bl['primary_label']}")

    # sector bucket from groups config
    sector = "other"
    for key, g in load_groups().items():
        if symbol in g.get("tickers", []):
            sector = key
            break

    # next week return (label for predictability test)
    next_ret = np.nan
    if loc + 5 < len(px.index):
        next_ret = float(px.loc[px.index[loc + 5], symbol] / px.loc[dt, symbol] - 1.0)

    return {
        "symbol": symbol,
        "date": str(dt.date()),
        "return_pct": round(ret * 100, 2),
        "ara": ara,
        "prior_5d_pct": round(mom5 * 100, 2) if np.isfinite(mom5) else None,
        "prior_20d_pct": round(mom20 * 100, 2) if np.isfinite(mom20) else None,
        "volume_ratio_20d": round(vr, 2) if np.isfinite(vr) else None,
        "n_peers_up": n_peers,
        "sector_group": sector,
        "tags": tags,
        "fwd_5d_return_pct": round(next_ret * 100, 2) if np.isfinite(next_ret) else None,
    }


def tag_stats(rows: list[dict]) -> list[dict]:
    n = len(rows)
    out = []
    all_tags = sorted({t for r in rows for t in r["tags"]})
    for tag in all_tags:
        sub = [r for r in rows if tag in r["tags"]]
        fwd = pd.Series([r["fwd_5d_return_pct"] for r in sub], dtype=float).dropna()
        out.append(
            {
                "tag": tag,
                "count": len(sub),
                "pct_of_spikes": round(100 * len(sub) / n, 1) if n else 0,
                "mean_spike_day_pct": round(float(np.mean([r["return_pct"] for r in sub])), 2),
                "mean_fwd_5d_pct": round(float(fwd.mean()), 2) if len(fwd) else None,
                "fwd_5d_hit_rate_pct": round(float((fwd > 0).mean() * 100), 1) if len(fwd) else None,
            }
        )
    return sorted(out, key=lambda x: x["count"], reverse=True)


def main() -> int:
    universe = load_universe()
    groups = load_groups()
    extra = sorted({t for g in groups.values() for t in g.get("tickers", [])})
    syms = sorted(set(universe + extra))
    px, vol_px = fetch_history(syms, START, datetime.now(UTC).strftime("%Y-%m-%d"))

    rows: list[dict] = []
    for sym in universe:
        if sym not in px.columns:
            continue
        rets = px[sym].pct_change().dropna()
        for dt, r in rets.items():
            if r * 100 < MIN_PCT:
                continue
            rows.append(classify_spike_row(sym, pd.Timestamp(dt), float(r), px, vol_px))

    # repeat spiker profile
    by_sym = (
        pd.DataFrame(rows)
        .groupby("symbol")
        .agg(n_spikes=("return_pct", "count"), mean_spike=("return_pct", "mean"), sector=("sector_group", "first"))
        .sort_values("n_spikes", ascending=False)
    )

    report = {
        "min_pct": MIN_PCT,
        "start": START,
        "n_spike_sessions": len(rows),
        "n_symbols_with_spikes": int(pd.DataFrame(rows)["symbol"].nunique()) if rows else 0,
        "tag_stats": tag_stats(rows),
        "top_repeat_spikers": by_sym.head(15).reset_index().to_dict(orient="records"),
        "sector_spike_counts": Counter(r["sector_group"] for r in rows),
        "sample_rows": sorted(rows, key=lambda x: x["return_pct"], reverse=True)[:25],
        "generated_at_utc": datetime.now(UTC).isoformat(),
    }
    report["sector_spike_counts"] = dict(report["sector_spike_counts"])

    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "pattern_mining_latest.json"
    path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    print(f"Spike sessions >= {MIN_PCT}% since {START}: {len(rows)}")
    print("\n=== Pattern tags (how often they appear on spike days) ===")
    print(f"{'tag':22} | {'count':>5} | {'%spikes':>7} | {'fwd5d%':>7} | {'fwd hit':>7}")
    print("-" * 60)
    for t in report["tag_stats"]:
        print(
            f"{t['tag']:22} | {t['count']:5} | {t['pct_of_spikes']:6.1f}% | "
            f"{t.get('mean_fwd_5d_pct') or 0:6.1f}% | {t.get('fwd_5d_hit_rate_pct') or 0:6.1f}%"
        )

    print("\n=== Repeat spikers ===")
    for r in report["top_repeat_spikers"][:10]:
        print(f"  {r['symbol']:10} {r['n_spikes']:2} spikes  sector={r['sector']}  avg spike={r['mean_spike']:.1f}%")

    print("\n=== Sector buckets (spike-day count) ===")
    for k, v in sorted(report["sector_spike_counts"].items(), key=lambda x: -x[1]):
        print(f"  {k:20} {v}")

    print(f"\nWrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
