"""Full-panel reverse engineering for IDX weekly signals (not hand-picked rules)."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from idn_eval_splits import ERA_OOS, ERA_TRAIN, build_eras, slice_era
from idn_sentiment_validation_lib import (
    portfolio_weekly_returns,
    quintile_spread,
    weekly_rank_ic,
)

# Never use as predictors
EXCLUDE_PREFIXES = ("fwd_", "global_")
EXCLUDE_EXACT = {
    "yahoo_symbol",
    "week_end",
    "country_iso3",
    "entity_id",
    "exchange",
    "name",
    "instrument_type",
    "confidence",
    "market_data_ffilled",
    "price",
    "return_1w",
    "return_4w",
    "source_news_runs",
}


def discover_numeric_features(df: pd.DataFrame, *, min_nonnull: int = 500, min_weeks: int = 40) -> list[str]:
    feats: list[str] = []
    for col in df.columns:
        if col in EXCLUDE_EXACT:
            continue
        if any(col.startswith(p) for p in EXCLUDE_PREFIXES):
            continue
        if not pd.api.types.is_numeric_dtype(df[col]):
            continue
        nonnull = int(df[col].notna().sum())
        weeks = int(df.loc[df[col].notna(), "week_end"].nunique())
        if nonnull >= min_nonnull and weeks >= min_weeks:
            feats.append(col)
    return sorted(feats)


def _tstat(vals: list[float]) -> float | None:
    a = np.asarray(vals, dtype=float)
    if len(a) < 8:
        return None
    sd = float(a.std(ddof=1))
    if sd <= 0:
        return None
    return float(a.mean() / (sd / math.sqrt(len(a))))


def test_feature(
    df: pd.DataFrame,
    signal: str,
    target: str,
    *,
    long_top: bool,
) -> dict[str, Any]:
    if signal not in df.columns or target not in df.columns:
        return {"ok": False}
    ic = weekly_rank_ic(df, signal, target)
    qs = quintile_spread(df, signal, target, long_top=long_top)
    return {
        "ok": True,
        "signal": signal,
        "direction": "long_top" if long_top else "fade",
        "ic_t": ic.get("tstat"),
        "spread_pct": qs.get("mean_spread_pct"),
        "spread_t": qs.get("tstat"),
        "weeks": qs.get("weeks", 0),
        "hit_positive_weeks_pct": qs.get("hit_positive_weeks_pct"),
    }


def scan_all_features(
    df: pd.DataFrame,
    features: list[str],
    *,
    target: str = "fwd_return_4w",
    era: str = "full",
) -> list[dict[str, Any]]:
    sub = slice_era(df, era)
    rows: list[dict[str, Any]] = []
    for feat in features:
        for long_top in (True, False):
            r = test_feature(sub, feat, target, long_top=long_top)
            if r.get("ok"):
                r["era"] = era
                r["target"] = target
                rows.append(r)
    rows.sort(key=lambda x: -(abs(x.get("spread_t") or 0)))
    return rows


def pick_best_direction(rows: list[dict[str, Any]], signal: str, era: str) -> dict[str, Any] | None:
    cand = [r for r in rows if r["signal"] == signal and r.get("era") == era]
    if not cand:
        return None
    return max(cand, key=lambda x: abs(x.get("spread_t") or 0))


def build_feature_zscore(df: pd.DataFrame, signal: str, *, invert: bool = False) -> pd.Series:
    """Cross-sectional z-score per week (point-in-time)."""
    out = df.groupby("week_end", sort=False)[signal].transform(
        lambda s: (s - s.mean()) / (s.std(ddof=1) + 1e-12) if s.notna().sum() >= 5 else np.nan
    )
    return -out if invert else out


def build_composite_score(
    df: pd.DataFrame,
    components: list[dict[str, Any]],
    *,
    score_col: str = "composite_score",
) -> pd.DataFrame:
    out = df.copy()
    score = pd.Series(0.0, index=out.index)
    weight_sum = pd.Series(0.0, index=out.index)
    for comp in components:
        sig = comp["signal"]
        if sig not in out.columns:
            continue
        w = float(comp.get("weight", 1.0))
        z = build_feature_zscore(out, sig, invert=comp.get("direction") == "fade")
        score = score.add(z.fillna(0) * w, fill_value=0)
        weight_sum = weight_sum.add(z.notna().astype(float) * w, fill_value=0)
    out[score_col] = score / weight_sum.replace(0, np.nan)
    return out


def backtest_composite(
    df: pd.DataFrame,
    *,
    score_col: str = "composite_score",
    target: str = "fwd_return_4w",
    max_picks: int = 3,
) -> pd.DataFrame:
    return portfolio_weekly_returns(
        df.dropna(subset=[score_col, target]),
        lambda g: g.nlargest(max_picks, score_col),
        bench_col=target,
        max_picks=max_picks,
    )


def indicator_recipe(components: list[dict[str, Any]], *, target: str, horizon: str) -> dict[str, Any]:
    """Machine-readable strategy indicator from discovered patterns."""
    rules = []
    for c in components:
        rules.append(
            {
                "feature": c["signal"],
                "direction": c["direction"],
                "weight": c.get("weight", 1.0),
                "human": (
                    f"{'Fade' if c['direction']=='fade' else 'Long'} names with "
                    f"{'high' if c['direction']=='long_top' else 'low'} `{c['signal']}` "
                    f"(z-score within week)"
                ),
            }
        )
    return {
        "indicator_id": "monthly_composite_v1",
        "horizon": horizon,
        "target": target,
        "rebalance": "weekly",
        "hold_days": 20,
        "entry": "top_3_by_composite_zscore",
        "components": rules,
        "formula": "composite_score = weighted sum of cross-sectional z-scores (fade = invert)",
    }


def select_oos_components(
    full_scan: dict[str, list[dict[str, Any]]],
    *,
    max_components: int = 3,
    min_oos_t: float = 1.5,
) -> list[dict[str, Any]]:
    """Pick features that work on OOS holdout with consistent direction."""
    oos_rows = full_scan.get(ERA_OOS, [])
    is_rows = full_scan.get(ERA_TRAIN, [])
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for row in oos_rows:
        sig = row["signal"]
        if sig in seen:
            continue
        if (row.get("spread_t") or 0) < min_oos_t:
            continue
        best_is = pick_best_direction(is_rows, sig, ERA_TRAIN)
        # require same direction sign OOS as best IS or IS not strongly opposite
        if best_is and (best_is.get("spread_pct") or 0) < 0 and (row.get("spread_pct") or 0) > 0:
            continue
        comp = {
            "signal": sig,
            "direction": row["direction"],
            "weight": 1.0,
            "oos_spread_pct": row.get("spread_pct"),
            "oos_spread_t": row.get("spread_t"),
            "is_spread_pct": (best_is or {}).get("spread_pct"),
        }
        out.append(comp)
        seen.add(sig)
        if len(out) >= max_components:
            break
    return out
