#!/usr/bin/env python3
"""OOS alpha horse race for Indonesia liquid 50 — rule-based swing strategies.

Tests pattern hypotheses (group sync, drawdown squeeze, bandar-lite, spike chase)
against equal-weight benchmarks. Uses daily yfinance panels only (no broker API).

Output: backtests/outputs/idn_alpha_proof/latest.json + daily_panel cache parquet
"""

from __future__ import annotations

import json
import math
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
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
    fetch_history,
    load_groups,
    load_universe,
    peer_moves,
    volume_ratio,
)
from idn_eval_splits import time_cutoff  # noqa: E402

OUT = REPO / "backtests/outputs/idn_alpha_proof"
PANEL_CACHE = REPO / "data_lake/markets/yfinance_asia/idn_liquid_daily_panel.parquet"
OOS_FRAC = 0.25
WARMUP_START = "2022-01-01"
HOLD_DAYS = 5
MAX_SLOTS = 5
COST_BPS = 25.0


@dataclass
class StratResult:
    name: str
    n_trades: int
    n_days: int
    mean_daily_pct: float
    ann_return_pct: float
    ann_vol_pct: float
    sharpe: float
    max_dd_pct: float
    terminal_x: float
    beat_eq_pct: float


def load_panel() -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    universe = load_universe()
    groups = load_groups()
    extra = sorted({t for g in groups.values() for t in g.get("tickers", [])})
    syms = sorted(set(universe + extra))
    end = (datetime.now(UTC).date() + timedelta(days=1)).isoformat()
    if PANEL_CACHE.exists():
        raw = pd.read_parquet(PANEL_CACHE)
        close = raw["close"].unstack("symbol").sort_index()
        vol = raw["volume"].unstack("symbol").sort_index()
        return close, vol, universe
    close, vol = fetch_history(syms, WARMUP_START, end)
    if close.empty:
        raise SystemExit("empty price panel")
    long = close.stack().rename("close").to_frame()
    long["volume"] = vol.stack()
    long.index.names = ["date", "symbol"]
    PANEL_CACHE.parent.mkdir(parents=True, exist_ok=True)
    long.to_parquet(PANEL_CACHE)
    return close, vol, universe


def daily_metrics(r: pd.Series) -> dict:
    r = r.dropna()
    if r.empty:
        return {}
    eq = (1 + r).cumprod()
    dd = eq / eq.cummax() - 1.0
    vol = float(r.std(ddof=1))
    ann = float(r.mean() * 252)
    return {
        "n_days": int(len(r)),
        "mean_daily_pct": float(r.mean() * 100),
        "ann_return_pct": ann * 100,
        "ann_vol_pct": vol * math.sqrt(252) * 100 if vol > 0 else float("nan"),
        "sharpe": float(r.mean() / vol * math.sqrt(252)) if vol > 0 else float("nan"),
        "max_dd_pct": float(dd.min() * 100),
        "terminal_x": float(eq.iloc[-1]),
    }



def turnover_cost(prev: dict[str, float], new: dict[str, float], cost_bps: float) -> tuple[float, float]:
    """Half-turnover and cost fraction for a rebalance."""
    keys = set(prev) | set(new)
    turnover = 0.5 * sum(abs(float(new.get(k, 0.0)) - float(prev.get(k, 0.0))) for k in keys)
    return float(turnover), float(turnover * (cost_bps / 10_000.0))

def simulate_slot_portfolio(
    signals: dict[pd.Timestamp, list[str]],
    close: pd.DataFrame,
    *,
    hold_days: int = HOLD_DAYS,
    max_slots: int = MAX_SLOTS,
    cost_bps: float = COST_BPS,
    oos_only: bool = True,
    oos_start: pd.Timestamp,
) -> pd.Series:
    """Enter equal-weight among signal names at close T; exit after hold_days."""
    rets = close.pct_change()
    dates = close.index
    active: list[dict] = []
    daily: list[float] = []
    prev_invested = 0.0

    for i, dt in enumerate(dates):
        # expire positions after hold window (return on exit day not included)
        active = [p for p in active if p["exit_idx"] > i]

        if dt in signals and len(active) < max_slots:
            names = [s for s in signals[dt] if s in close.columns]
            slots_free = max_slots - len(active)
            for sym in names[:slots_free]:
                # Signal at close T; first PnL is return on T+1..T+hold_days
                active.append(
                    {
                        "symbol": sym,
                        "entry_idx": i,
                        "exit_idx": i + hold_days,
                        "weight": 1.0 / max_slots,
                    }
                )

        invested = sum(p["weight"] for p in active)
        port_r = 0.0
        for p in active:
            sym = p["symbol"]
            # No same-day return on entry close (avoid lookahead)
            if p["entry_idx"] >= i:
                continue
            if sym in rets.columns:
                port_r += p["weight"] * float(rets.loc[dt, sym])

        if oos_only and dt < oos_start:
            prev_invested = invested
            continue

        to = abs(invested - prev_invested)
        cost = to * (cost_bps / 10_000.0)
        daily.append(port_r - cost)
        prev_invested = invested

    return pd.Series(daily, index=[d for d in dates if (not oos_only or d >= oos_start)])


def build_signals(close: pd.DataFrame, vol: pd.DataFrame, universe: list[str]) -> dict[str, dict[pd.Timestamp, list[str]]]:
    rets = close.pct_change()
    groups = load_groups()
    out: dict[str, dict[pd.Timestamp, list[str]]] = {
        "group_sync_2plus": {},
        "drawdown_squeeze": {},
        "quiet_volume_build": {},
        "spike_chase_10pct": {},
        "fade_spike_10pct": {},
        "mom20_breakout": {},
    }

    for dt in close.index[25:]:
        day_sigs: dict[str, list[str]] = {k: [] for k in out}

        for sym in universe:
            if sym not in close.columns or dt not in close.index:
                continue
            loc = close.index.get_loc(dt)
            if loc < 21:
                continue
            r1 = float(rets.loc[dt, sym])
            if not np.isfinite(r1):
                continue

            mom5 = float(close.loc[dt, sym] / close.loc[close.index[loc - 5], sym] - 1.0)
            mom20 = float(close.loc[dt, sym] / close.loc[close.index[loc - 20], sym] - 1.0)
            vol_today = float(vol.loc[dt, sym]) if sym in vol.columns else np.nan
            vol_hist = vol[sym].iloc[loc - 20 : loc] if sym in vol.columns else pd.Series(dtype=float)
            vr = volume_ratio(vol_today, vol_hist)

            peers = peer_moves(sym, dt, close, min_pct=0.08)
            n_peers = len(peers[0]["peers_up"]) if peers else 0
            if n_peers >= 2:
                day_sigs["group_sync_2plus"].append(sym)

            if mom5 <= -0.08 and np.isfinite(vr) and vr >= 1.4:
                day_sigs["drawdown_squeeze"].append(sym)

            bl = bandar_lite_features(close[sym], vol[sym] if sym in vol.columns else pd.Series(dtype=float), dt)
            if bl.get("available") and bl.get("primary_label") == "quiet_volume_build":
                day_sigs["quiet_volume_build"].append(sym)

            if r1 >= 0.10:
                day_sigs["spike_chase_10pct"].append(sym)

            if r1 >= 0.10:
                day_sigs["fade_spike_10pct"].append(sym)  # short proxy handled separately

            if mom20 >= 0.15 and r1 >= 0.02:
                day_sigs["mom20_breakout"].append(sym)

        for k, v in day_sigs.items():
            if v:
                out[k][dt] = sorted(set(v))

    return out


def simulate_equal_weight_monthly(
    close: pd.DataFrame, universe: list[str], *, cost_bps: float = COST_BPS, oos_start: pd.Timestamp
) -> pd.Series:
    sub = close[universe].dropna(how="all", axis=1)
    rets = sub.pct_change()
    month_end = sub.resample("ME").last().index
    weights: dict[str, float] = {}
    daily_r: list[tuple[pd.Timestamp, float]] = []
    prev_w: dict[str, float] = {}

    for dt in sub.index:
        if dt in month_end:
            cols = [c for c in sub.columns if pd.notna(sub.loc[dt, c])]
            w = 1.0 / len(cols) if cols else 0.0
            weights = {c: w for c in cols}
        if dt < oos_start:
            prev_w = weights.copy()
            continue
        r = float(sum(weights.get(c, 0) * rets.loc[dt, c] for c in weights if pd.notna(rets.loc[dt, c])))
        _, cost = turnover_cost(prev_w, weights, cost_bps)
        daily_r.append((dt, r - cost))
        prev_w = weights.copy()

    return pd.Series({d: r for d, r in daily_r})


def simulate_fade_spike(
    close: pd.DataFrame,
    universe: list[str],
    signals: dict[pd.Timestamp, list[str]],
    *,
    oos_start: pd.Timestamp,
) -> pd.Series:
    """Go cash on spike days (avoid chase); benchmark is what spike_chase would lose."""
    rets = close[universe].mean(axis=1).pct_change()
    daily = []
    for dt in rets.index:
        if dt < oos_start:
            continue
        if dt in signals and signals[dt]:
            daily.append(0.0)
        else:
            daily.append(float(rets.loc[dt]) if pd.notna(rets.loc[dt]) else 0.0)
    return pd.Series(daily)


def strat_result(name: str, r: pd.Series, eq: pd.Series, n_trades: int) -> StratResult:
    m = daily_metrics(r)
    beat = float((r > eq.reindex(r.index)).mean() * 100) if len(eq) == len(r) else float("nan")
    return StratResult(
        name=name,
        n_trades=n_trades,
        n_days=m.get("n_days", 0),
        mean_daily_pct=m.get("mean_daily_pct", float("nan")),
        ann_return_pct=m.get("ann_return_pct", float("nan")),
        ann_vol_pct=m.get("ann_vol_pct", float("nan")),
        sharpe=m.get("sharpe", float("nan")),
        max_dd_pct=m.get("max_dd_pct", float("nan")),
        terminal_x=m.get("terminal_x", float("nan")),
        beat_eq_pct=beat,
    )


def main() -> int:
    close, vol, universe = load_panel()
    oos_start = time_cutoff(close.index, oos_frac=OOS_FRAC)
    signals = build_signals(close, vol, universe)

    eq_monthly = simulate_equal_weight_monthly(close, universe, oos_start=oos_start)
    eq_daily = close[universe].mean(axis=1).pct_change()
    eq_daily = eq_daily[eq_daily.index >= oos_start]

    results: list[dict] = []
    trade_counts: dict[str, int] = {}

    for name, sig_map in signals.items():
        if name == "fade_spike_10pct":
            r = simulate_fade_spike(close, universe, sig_map, oos_start=oos_start)
            n_trades = sum(len(v) for v in sig_map.values())
        else:
            r = simulate_slot_portfolio(sig_map, close, oos_start=oos_start)
            n_trades = sum(len(v) for v in sig_map.values())
        trade_counts[name] = n_trades
        sr = strat_result(name, r, eq_daily.reindex(r.index).fillna(0), n_trades)
        results.append(asdict(sr))

    eq_sr = strat_result("liquid_eq_monthly", eq_monthly, eq_daily.reindex(eq_monthly.index).fillna(0), 0)
    results.insert(0, asdict(eq_sr))

    # Event-study: non-overlapping mean fwd 5d per signal (diagnostic)
    rets = close.pct_change()
    event_rows = []
    for name, sig_map in signals.items():
        fwd = []
        for dt, syms in sig_map.items():
            loc = close.index.get_loc(dt)
            if loc + HOLD_DAYS >= len(close.index):
                continue
            for sym in syms:
                if sym not in close.columns:
                    continue
                f = float(close.iloc[loc + HOLD_DAYS][sym] / close.loc[dt, sym] - 1.0)
                if dt >= oos_start:
                    fwd.append(f)
        event_rows.append(
            {
                "strategy": name,
                "n_events_oos": len(fwd),
                "mean_fwd_5d_pct": round(float(np.mean(fwd)) * 100, 2) if fwd else None,
                "hit_rate_5d_pct": round(float((np.array(fwd) > 0).mean()) * 100, 1) if fwd else None,
            }
        )

    verdict = "no_alpha"
    best = max((x for x in results if x["name"] != "liquid_eq_monthly"), key=lambda x: x.get("sharpe") or -999)
    eq_sharpe = eq_sr.sharpe
    if best.get("sharpe") and eq_sharpe and best["sharpe"] > eq_sharpe + 0.15 and best["terminal_x"] > eq_sr.terminal_x:
        verdict = "candidate_alpha"
    elif best.get("terminal_x", 1) > eq_sr.terminal_x * 1.05:
        verdict = "marginal_outperformance"

    report = {
        "oos_frac": OOS_FRAC,
        "oos_start": str(oos_start.date()),
        "hold_days": HOLD_DAYS,
        "max_slots": MAX_SLOTS,
        "cost_bps": COST_BPS,
        "panel_cache": str(PANEL_CACHE),
        "universe_size": len(universe),
        "portfolio_results": results,
        "event_study_fwd5d": event_rows,
        "trade_counts_oos": trade_counts,
        "verdict": verdict,
        "best_strategy": best["name"],
        "generated_at_utc": datetime.now(UTC).isoformat(),
    }

    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "latest.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"OOS from {oos_start.date()} (last {int(OOS_FRAC*100)}% of panel) | hold {HOLD_DAYS}d | cost {COST_BPS}bps")
    print(f"{'strategy':22} | {'trades':>6} | {'ann%':>7} | {'Sharpe':>6} | {'maxDD%':>7} | {'terminal':>8}")
    print("-" * 72)
    for row in sorted(results, key=lambda x: x.get("sharpe") or -99, reverse=True):
        print(
            f"{row['name']:22} | {row['n_trades']:6} | {row.get('ann_return_pct') or 0:6.1f}% | "
            f"{row.get('sharpe') or 0:5.2f} | {row.get('max_dd_pct') or 0:6.1f}% | {row.get('terminal_x') or 1:7.3f}x"
        )
    print(f"\nVerdict: {verdict} (best={best['name']})")
    print(f"\nEvent study (mean fwd 5d after signal, OOS):")
    for e in sorted(event_rows, key=lambda x: x.get("mean_fwd_5d_pct") or -999, reverse=True):
        print(f"  {e['strategy']:22} n={e['n_events_oos']:4}  fwd5d={e.get('mean_fwd_5d_pct')}%  hit={e.get('hit_rate_5d_pct')}%")
    print(f"\nWrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
