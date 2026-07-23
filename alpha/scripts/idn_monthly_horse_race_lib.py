"""Monthly (~4w) return horse-race helpers for IDX."""

from __future__ import annotations

import math
from typing import Any, Callable

import numpy as np
import pandas as pd

from idn_eval_splits import ERA_OOS, build_eras, time_cutoff
from idn_regime_lib import summarize_returns_pct

# ~1 week and ~1 month on IDX weekly bars
HORIZON_1W_DAYS = 5
HORIZON_4W_DAYS = 20


def era_filter(index: pd.DatetimeIndex, start: str | None, end: str | None) -> pd.DatetimeIndex:
    out = index
    if start:
        out = out[out >= pd.Timestamp(start)]
    if end:
        out = out[out < pd.Timestamp(end)]
    return out


def tstat_pct(vals: list[float] | np.ndarray) -> float | None:
    a = np.asarray(vals, dtype=float)
    if len(a) < 8:
        return None
    sd = float(a.std(ddof=1))
    if sd <= 0:
        return None
    return float(a.mean() / (sd / math.sqrt(len(a))))


def score_series(r: pd.Series) -> dict[str, Any]:
    r = r.dropna()
    if r.empty:
        return {"n": 0}
    pct = r.to_numpy(dtype=float)
    base = summarize_returns_pct(pct)
    base["tstat"] = round(tstat_pct(pct) or 0.0, 3) if len(pct) >= 8 else None
    base["terminal_x"] = round(float((1 + r).prod()), 3)
    return base


def ensure_fwd_4w(panel: pd.DataFrame) -> pd.DataFrame:
    if "fwd_return_4w" in panel.columns and panel["fwd_return_4w"].notna().sum() > 100:
        return panel
    out = panel.sort_values(["yahoo_symbol", "week_end"]).copy()
    out["fwd_return_4w"] = out.groupby("yahoo_symbol")["fwd_return_1w"].transform(
        lambda s: (1 + s).rolling(4, min_periods=4).apply(np.prod, raw=True) - 1
    )
    return out


def quintile_spread_4w(
    df: pd.DataFrame,
    signal: str,
    *,
    min_names: int = 10,
    long_top: bool = True,
) -> dict[str, Any]:
    spreads: list[float] = []
    for _, g in df.groupby("week_end", sort=False):
        g = g[["yahoo_symbol", signal, "fwd_return_4w"]].dropna()
        if len(g) < min_names:
            continue
        g = g.copy()
        g["q"] = pd.qcut(g[signal].rank(method="first"), 5, labels=False, duplicates="drop")
        top = float(g[g["q"] == g["q"].max()]["fwd_return_4w"].mean())
        bot = float(g[g["q"] == g["q"].min()]["fwd_return_4w"].mean())
        spreads.append((top - bot) if long_top else (bot - top))
    if len(spreads) < 8:
        return {"mean_spread_pct": None, "tstat": None, "weeks": len(spreads)}
    a = np.array(spreads) * 100
    return {
        "mean_spread_pct": round(float(a.mean()), 3),
        "tstat": round(tstat_pct(a) or 0.0, 3),
        "weeks": int(len(a)),
        "hit_positive_weeks_pct": round(float((a > 0).mean() * 100), 1),
    }


def portfolio_4w_returns(
    df: pd.DataFrame,
    pick_fn: Callable[[pd.DataFrame], pd.DataFrame],
    *,
    max_picks: int = 3,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for wk, g in df.groupby("week_end", sort=False):
        picks = pick_fn(g)
        if picks is None or len(picks) == 0:
            continue
        picks = picks.head(max_picks)
        rows.append(
            {
                "week_end": wk,
                "pick_ret": float(picks["fwd_return_4w"].mean()),
                "bench_ret": float(g["fwd_return_4w"].mean()),
            }
        )
    out = pd.DataFrame(rows)
    if not out.empty:
        out["excess_ret"] = out["pick_ret"] - out["bench_ret"]
    return out


def regime_timed_returns(
    tape: pd.DataFrame,
    price: pd.Series,
    *,
    allow_regimes: set[str],
    label: str,
) -> pd.Series:
    """Weekly entries: 4w forward return when regime at week-end is allowed."""
    px = price.dropna().sort_index()
    weekly = px.resample("W-FRI").last().dropna()
    from idn_regime_lib import _fwd_return

    rows: list[tuple[pd.Timestamp, float]] = []
    for dt in weekly.index:
        hist = tape.loc[:dt]
        if len(hist) < 63:
            continue
        reg = str(hist.iloc[-1]["label"])
        if reg not in allow_regimes:
            continue
        r = _fwd_return(px, dt, HORIZON_4W_DAYS)
        if r is not None:
            rows.append((dt, r))
    if not rows:
        return pd.Series(dtype=float)
    s = pd.Series({d: v for d, v in rows}).sort_index()
    s.name = label
    return s


def hybrid_monthly_rotation(tape: pd.DataFrame, ihsg: pd.Series, bank_ew: pd.Series) -> pd.Series:
    """Actionable monthly rule: washout→banks, recovery→ihsg, neutral→half ihsg, extended→flat."""
    from idn_regime_lib import _fwd_return

    ih = ihsg.dropna().sort_index()
    bk = bank_ew.dropna().sort_index()
    weekly = ih.resample("W-FRI").last().dropna()
    rows: list[tuple[pd.Timestamp, float]] = []
    for dt in weekly.index:
        hist = tape.loc[:dt]
        if len(hist) < 63:
            continue
        reg = str(hist.iloc[-1]["label"])
        i4 = _fwd_return(ih, dt, HORIZON_4W_DAYS)
        b4 = _fwd_return(bk, dt, HORIZON_4W_DAYS)
        if i4 is None or b4 is None:
            continue
        if reg == "washout":
            r = b4
        elif reg == "recovery":
            r = i4
        elif reg == "neutral":
            r = 0.5 * i4
        else:
            r = 0.0
        rows.append((dt, r))
    return pd.Series({d: v for d, v in rows}).sort_index()


def retail_event_stats_from_validation(path) -> list[dict[str, Any]]:
    import json
    from pathlib import Path

    p = Path(path)
    if not p.exists():
        return []
    raw = json.loads(p.read_text(encoding="utf-8"))
    rp = raw.get("retail_playbook") or {}
    strategies = rp.get("strategies") or {}
    rows: list[dict[str, Any]] = []
    for sid, body in strategies.items():
        es = body.get("event_study") or {}
        bh = es.get("by_horizon") or {}
        for horizon_key, prefer in (("oos_20d", "oos_20d"), ("all_20d", "all_20d"), ("oos_10d", "oos_10d"), ("oos_5d", "oos_5d")):
            h = bh.get(prefer)
            if h and h.get("n", 0) >= 15:
                rows.append(
                    {
                        "strategy_id": sid,
                        "jargon": body.get("jargon", sid),
                        "horizon": prefer.replace("oos_", "").replace("all_", ""),
                        "scope": "oos" if prefer.startswith("oos_") else "all",
                        "n": h.get("n"),
                        "mean_pct": h.get("mean_pct"),
                        "tstat": h.get("tstat"),
                        "hit_rate_pct": h.get("hit_rate_pct"),
                    }
                )
                break
    return rows


def rank_strategies(rows: list[dict[str, Any]], era: str = ERA_OOS) -> list[dict[str, Any]]:
    ranked = []
    for r in rows:
        era_stats = (r.get("eras") or {}).get(era) or {}
        if not era_stats.get("n"):
            continue
        ranked.append(
            {
                **r,
                "era": era,
                "mean_pct": era_stats.get("mean_pct"),
                "tstat": era_stats.get("tstat"),
                "hit_positive_pct": era_stats.get("hit_positive_pct"),
            }
        )
    return sorted(
        ranked,
        key=lambda x: (x.get("tstat") or 0, x.get("mean_pct") or 0),
        reverse=True,
    )


def build_playbook(ranked: list[dict[str, Any]], ihsg_monthly_mean: float) -> dict[str, str]:
    lines = {
        "horizon": "~4 week (20 trading day) holds. No year-long pray trades.",
        "ihsg_baseline": f"IHSG calendar month mean ~{ihsg_monthly_mean:+.2f}% — you need to beat this actively.",
    }
    if not ranked:
        lines["action"] = "Insufficient OOS monthly winners; stay tactical and small."
        return lines
    top = ranked[0]
    lines["best_oos"] = (
        f"Best OOS monthly lane: {top.get('name')} "
        f"({top.get('mean_pct'):+.2f}% mean, t={top.get('tstat')})"
    )
    top_names = [r.get("name") or "" for r in ranked[:6]]
    if any("fade" in n for n in top_names):
        lines["reversal"] = "4w reversal (fade last week's losers) beats chase on OOS holdout."
    if any("mom" in n for n in top_names[:3]):
        lines["momentum"] = "4w momentum picks in top OOS bucket — check rank table."
    if any("retail" in (r.get("category") or "") for r in ranked[:8]):
        lines["retail"] = "Retail event rules (5–20d) remain the sniper lane — trade when they fire, flat otherwise."
    if any("regime" in (r.get("category") or "") for r in ranked[:8]):
        lines["regime"] = "Regime is a filter/sizer for monthly bets, not a year-hold sleeve."
    lines["avoid"] = "Kill year-hold framing; rebalance weekly/monthly on what wins now."
    return lines
