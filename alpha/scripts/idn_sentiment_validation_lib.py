"""Empirical validation helpers for IDX public sentiment / operator signals."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from idn_eval_splits import (  # noqa: F401
    ERA_FULL,
    ERA_NAMES,
    ERA_OOS,
    ERA_TRAIN,
    build_eras,
    era_slice,
    min_weeks_for_era,
    slice_era,
    split_meta,
    time_cutoff,
)


def weekly_rank_ic(df: pd.DataFrame, x: str, y: str, *, min_names: int = 8) -> dict[str, Any]:
    sub = df[["week_end", "yahoo_symbol", x, y]].dropna()
    if len(sub) < 80:
        return {"mean_ic": None, "tstat": None, "weeks": 0}
    sub = sub.copy()
    sub["rx"] = sub.groupby("week_end", sort=False)[x].rank()
    sub["ry"] = sub.groupby("week_end", sort=False)[y].rank()
    ics = sub.groupby("week_end", sort=False).apply(
        lambda g: float(g["rx"].corr(g["ry"])) if len(g) >= min_names and g["rx"].std() > 0 else np.nan,
        include_groups=False,
    ).dropna()
    if len(ics) < 10:
        return {"mean_ic": None, "tstat": None, "weeks": int(len(ics))}
    a = ics.to_numpy(dtype=float)
    mu = float(a.mean())
    sd = float(a.std(ddof=1))
    t = mu / (sd / math.sqrt(len(a)) + 1e-12)
    return {"mean_ic": round(mu, 4), "tstat": round(t, 3), "weeks": int(len(a))}


def quintile_spread(
    df: pd.DataFrame,
    signal: str,
    target: str = "fwd_return_1w",
    *,
    min_names: int = 10,
    long_top: bool = True,
) -> dict[str, Any]:
    """Mean weekly top-quintile minus bottom-quintile forward return."""
    spreads: list[float] = []
    for _, g in df.groupby("week_end", sort=False):
        g = g[["yahoo_symbol", signal, target]].dropna()
        if len(g) < min_names:
            continue
        g = g.copy()
        g["q"] = pd.qcut(g[signal].rank(method="first"), 5, labels=False, duplicates="drop")
        top = float(g[g["q"] == g["q"].max()][target].mean())
        bot = float(g[g["q"] == g["q"].min()][target].mean())
        spreads.append((top - bot) if long_top else (bot - top))
    if len(spreads) < 8:
        return {"mean_spread_pct": None, "tstat": None, "weeks": len(spreads)}
    a = np.array(spreads, dtype=float) * 100
    mu = float(a.mean())
    sd = float(a.std(ddof=1))
    t = mu / (sd / math.sqrt(len(a)) + 1e-12) if sd > 0 else None
    return {
        "mean_spread_pct": round(mu, 3),
        "tstat": round(t, 3) if t is not None else None,
        "weeks": int(len(a)),
        "hit_positive_weeks_pct": round(float((a > 0).mean() * 100), 1),
    }


def portfolio_weekly_returns(
    df: pd.DataFrame,
    pick_fn,
    *,
    bench_col: str = "fwd_return_1w",
    max_picks: int = 3,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for wk, g in df.groupby("week_end", sort=False):
        g = g.copy()
        picks = pick_fn(g)
        if picks is None or len(picks) == 0:
            continue
        picks = picks.head(max_picks)
        rows.append(
            {
                "week_end": wk,
                "n_picks": len(picks),
                "pick_ret": float(picks[bench_col].mean()),
                "bench_ret": float(g[bench_col].mean()),
                "excess_ret": float(picks[bench_col].mean() - g[bench_col].mean()),
                "tickers": picks["yahoo_symbol"].tolist(),
            }
        )
    return pd.DataFrame(rows)


def summarize_returns(r: pd.Series) -> dict[str, Any]:
    r = r.dropna()
    if r.empty:
        return {}
    eq = (1 + r).cumprod()
    vol = float(r.std(ddof=1))
    return {
        "weeks": int(len(r)),
        "mean_weekly_pct": round(float(r.mean() * 100), 3),
        "cum_return_pct": round(float((eq.iloc[-1] - 1) * 100), 2),
        "sharpe_weekly": round(float(r.mean() / vol * math.sqrt(52)), 3) if vol > 0 else None,
        "hit_rate_pct": round(float((r > 0).mean() * 100), 1),
        "terminal_x": round(float(eq.iloc[-1]), 3),
    }


def verdict_from_stats(
    *,
    tstat: float | None,
    weeks: int,
    mean_spread_pct: float | None = None,
    sharpe: float | None = None,
    min_weeks: int = 40,
) -> str:
    if weeks < min_weeks:
        return "insufficient_sample"
    if tstat is not None and abs(tstat) >= 2.0 and (mean_spread_pct or 0) > 0 and (sharpe or 0) > 0.3:
        return "reliable"
    if tstat is not None and abs(tstat) >= 1.0:
        return "conditional"
    return "unreliable"


def prepare_liquid_weekly(broadcast_path, entity_path, liquid: list[str]) -> pd.DataFrame:
    b = pd.read_parquet(broadcast_path)
    b["week_end"] = pd.to_datetime(b["week_end"])
    bl = b[(b["country_iso3"] == "IDN") & (b["yahoo_symbol"].isin(liquid))].copy()
    bl = bl.sort_values(["yahoo_symbol", "week_end"])
    bl["mom_4w"] = (
        bl.groupby("yahoo_symbol")["return_1w"]
        .rolling(4, min_periods=2)
        .sum()
        .reset_index(level=0, drop=True)
        .shift(1)
    )
    bl["prior_return_1w"] = bl.groupby("yahoo_symbol")["return_1w"].shift(1)
    bl["trending_proxy_rank"] = bl.groupby("week_end")["prior_return_1w"].rank(ascending=False, pct=True)

    if entity_path.exists():
        e = pd.read_parquet(entity_path)
        e["week_end"] = pd.to_datetime(e["week_end"])
        ent = e[(e["country_iso3"] == "IDN") & (e["yahoo_symbol"].isin(liquid))][
            ["week_end", "yahoo_symbol", "entity_mention_rows", "mean_tone_avg"]
        ]
        bl = bl.merge(ent, on=["week_end", "yahoo_symbol"], how="left")
    else:
        bl["entity_mention_rows"] = np.nan

    bl["mention_rank_pct"] = bl.groupby("week_end")["entity_mention_rows"].rank(ascending=False, pct=True)
    return bl
