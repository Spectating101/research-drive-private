"""Fry trigger outcome certainty — what happens on wins vs non-wins.

Answers: if we watch (not buy) after trigger, what is the full outcome menu?
  - pop win (discrete ARA day)
  - stagnant flat (no pop, small drift)
  - discrete sink before pop
  - slow grind bleed
  - pop then fade

Also: path stats if you *mistakenly* held from trigger close (honest EV).
"""

from __future__ import annotations

import json
import math
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
FRY_DIR = REPO / "data_lake/research_panels/idn_fry_episode"
TURNAROUND = REPO / "data_lake/research_panels/idn_turnaround/daily_features.parquet"
OUT_JSON = FRY_DIR / "fry_outcome_certainty_report.json"

OOS_START = pd.Timestamp("2024-01-01")
PATH_DAYS = 30
STAGNANT_LO = -0.05
STAGNANT_HI = 0.05
MILD_BLEED_LO = -0.15

from idn_fry_bilateral_lib import (  # noqa: E402
    OUTCOME_FLAT,
    OUTCOME_GRIND_NO_POP,
    OUTCOME_POP_FIRST,
    OUTCOME_POP_THEN_FADE,
    OUTCOME_SINK_ONLY,
    POP_RET_MIN,
    SINK_RET_MIN,
    classify_trigger_outcomes,
)
from idn_fry_episode_lib import POP_RET_STRONG  # noqa: E402


def _pct(x: float | None) -> float | None:
    return round(float(x) * 100, 2) if x is not None and np.isfinite(x) else None


def _quantiles(s: pd.Series, ps: tuple[int, ...] = (10, 50, 90)) -> dict[str, float | None]:
    s = s.dropna()
    if s.empty:
        return {f"p{p}": None for p in ps}
    return {f"p{p}": round(float(np.percentile(s, p)), 2) for p in ps}


def _episode_paths(ep: pd.DataFrame, panel: pd.DataFrame) -> pd.DataFrame:
    """Per trigger: forward path from trigger close (close-to-close)."""
    panel = panel.sort_values(["yahoo_symbol", "date"])
    rows: list[dict[str, Any]] = []

    for _, er in ep.iterrows():
        sym = er["yahoo_symbol"]
        t0 = pd.Timestamp(er["trigger_date"])
        g = panel[(panel["yahoo_symbol"] == sym) & (panel["date"] >= t0)].head(PATH_DAYS + 1)
        if len(g) < 2:
            continue
        close = g["close"].to_numpy(dtype=float)
        rets = g["return_1d"].iloc[1:].to_numpy(dtype=float)
        rets = rets[~np.isnan(rets)]
        if len(rets) == 0:
            continue

        cum = np.cumprod(1.0 + rets) - 1.0
        running_max = np.maximum.accumulate(close[: len(rets) + 1])
        dd = (close[1 : len(rets) + 1] / running_max[1 : len(rets) + 1]) - 1.0
        max_dd = float(np.min(dd)) if len(dd) else np.nan

        def _cum_at(day: int) -> float | None:
            if day <= 0 or day > len(cum):
                return None
            return float(cum[day - 1])

        rows.append(
            {
                "episode_id": int(er["episode_id"]),
                "yahoo_symbol": sym,
                "trigger_date": t0,
                "cum_5d_pct": _pct(_cum_at(5)),
                "cum_10d_pct": _pct(_cum_at(10)),
                "cum_30d_pct": _pct(_cum_at(min(30, len(cum)))),
                "max_dd_from_trigger_pct": _pct(max_dd),
                "worst_day_30d_pct": _pct(float(np.min(rets[:30]))),
                "best_day_30d_pct": _pct(float(np.max(rets[:30]))),
            }
        )
    return pd.DataFrame(rows)


def _merge_frame(ep: pd.DataFrame, trig: pd.DataFrame, outcomes: pd.DataFrame, paths: pd.DataFrame) -> pd.DataFrame:
    df = ep.merge(outcomes, on="episode_id", how="left", suffixes=("", "_oc"))
    df = df.merge(paths, on="episode_id", how="left", suffixes=("", "_path"))
    if not trig.empty:
        tcols = [
            c
            for c in [
                "episode_id",
                "return_5d",
                "vol_ratio_20d",
                "trigger_cause",
                "quiet_acc_score_5d",
                "got_pop",
            ]
            if c in trig.columns
        ]
        df = df.merge(trig[tcols].drop_duplicates("episode_id"), on="episode_id", how="left")
    df["trigger_date"] = pd.to_datetime(df["trigger_date"])
    df["era"] = np.where(df["trigger_date"] >= OOS_START, "oos", "ins")
    df["is_t1"] = (df["return_5d"] <= -0.08) & (df["vol_ratio_20d"] >= 1.6)
    df["is_t2"] = df["return_5d"] <= -0.12
    return df


def _outcome_block(sub: pd.DataFrame) -> dict[str, Any]:
    n = len(sub)
    if n == 0:
        return {"n": 0, "sufficient": False}

    counts = sub["outcome_class"].value_counts().to_dict()
    shares = {k: round(100 * v / n, 2) for k, v in counts.items()}

    pop_any = sub["outcome_class"].isin([OUTCOME_POP_FIRST, OUTCOME_POP_THEN_FADE])
    no_pop = ~pop_any

    stagnant = sub[
        no_pop
        & (
            (sub["outcome_class"] == OUTCOME_FLAT)
            | (sub["cum_30d_pct"].between(STAGNANT_LO * 100, STAGNANT_HI * 100, inclusive="both"))
        )
    ]
    sink = sub[sub["outcome_class"] == OUTCOME_SINK_ONLY]
    grind = sub[sub["outcome_class"] == OUTCOME_GRIND_NO_POP]

    non_pop = sub[no_pop]
    catastrophic = non_pop[non_pop["cum_30d_pct"] <= -25.0] if "cum_30d_pct" in non_pop.columns else pd.DataFrame()

    hold5 = sub["cum_5d_pct"].dropna()
    hold30 = sub["cum_30d_pct"].dropna()
    max_dd = sub["max_dd_from_trigger_pct"].dropna()

    return {
        "n": n,
        "sufficient": n >= 100,
        "outcome_shares_pct": shares,
        "pop_any_rate_pct": round(float(pop_any.mean()) * 100, 2),
        "pop_first_rate_pct": round(float((sub["outcome_class"] == OUTCOME_POP_FIRST).mean()) * 100, 2),
        "pop_then_fade_rate_pct": round(float((sub["outcome_class"] == OUTCOME_POP_THEN_FADE).mean()) * 100, 2),
        "non_pop_breakdown_pct": {
            "stagnant_flat": round(100 * len(stagnant) / n, 2),
            "sink_before_pop": round(100 * len(sink) / n, 2),
            "grind_bleed": round(100 * len(grind) / n, 2),
            "other_non_pop": round(
                100 * (no_pop.sum() - len(stagnant) - len(sink) - len(grind)) / n, 2
            ),
        },
        "catastrophic_non_pop_pct": round(100 * len(catastrophic) / n, 2) if len(non_pop) else None,
        "median_non_pop_cum_30d_pct": round(float(non_pop["cum_30d_pct"].median()), 2)
        if non_pop["cum_30d_pct"].notna().any()
        else None,
        "median_stagnant_cum_30d_pct": round(float(stagnant["cum_30d_pct"].median()), 2)
        if stagnant["cum_30d_pct"].notna().any()
        else None,
        "median_sink_cum_30d_pct": round(float(sink["cum_30d_pct"].median()), 2) if len(sink) else None,
        "if_hold_from_trigger_close": {
            "mean_cum_5d_pct": round(float(hold5.mean()), 2) if len(hold5) else None,
            "mean_cum_30d_pct": round(float(hold30.mean()), 2) if len(hold30) else None,
            "median_cum_30d_pct": round(float(hold30.median()), 2) if len(hold30) else None,
            "max_dd_median_pct": round(float(max_dd.median()), 2) if len(max_dd) else None,
            "max_dd_p90_pct": round(float(np.percentile(max_dd, 90)), 2) if len(max_dd) else None,
            "cum_30d_quantiles": _quantiles(hold30),
        },
        "pop_first_median_pop_day_pct": round(float(sub.loc[sub["outcome_class"] == OUTCOME_POP_FIRST, "pop_return_1d_pct"].median()), 2)
        if (sub["outcome_class"] == OUTCOME_POP_FIRST).any()
        else None,
        "pop_first_median_trigger_to_pop_days": round(
            float(sub.loc[sub["outcome_class"] == OUTCOME_POP_FIRST, "trigger_to_pop_days"].median()), 1
        )
        if (sub["outcome_class"] == OUTCOME_POP_FIRST).any()
        else None,
    }


def _certainty_verdict(t1: dict[str, Any], t1_oos: dict[str, Any]) -> dict[str, Any]:
    """Honest map: is the non-win leg mostly stagnant vs catastrophic?"""
    checks: list[str] = []
    score = 0

    stagnant = (t1.get("non_pop_breakdown_pct") or {}).get("stagnant_flat", 0)
    sink = (t1.get("non_pop_breakdown_pct") or {}).get("sink_before_pop", 0)
    grind = (t1.get("non_pop_breakdown_pct") or {}).get("grind_bleed", 0)
    cat = t1.get("catastrophic_non_pop_pct") or 0
    med_non_pop = t1.get("median_non_pop_cum_30d_pct")
    pop_rate = t1.get("pop_any_rate_pct", 0)

    if stagnant >= 35:
        score += 1
        checks.append(f"PROVEN: {stagnant:.0f}% of T1 triggers end stagnant/flat (no pop, ~0% 30d drift)")
    if sink + grind <= 25:
        score += 1
        checks.append(f"PROVEN: discrete sink+grind only {sink + grind:.0f}% — not a 50% cliff lottery")
    if cat is not None and cat < 8:
        score += 1
        checks.append(f"PROVEN: catastrophic (≤-25% in 30d, no pop) only {cat:.0f}%")
    if med_non_pop is not None and med_non_pop > -8:
        score += 1
        checks.append(f"PROVEN: median non-pop 30d path {med_non_pop:+.1f}% (stale, not bleed)")
    if pop_rate >= 38:
        score += 1
        checks.append(f"SUPPORTED: ~{pop_rate:.0f}% get a pop within 30d on T1 filter")

    oos_pop = t1_oos.get("pop_any_rate_pct", 0)
    if t1_oos.get("sufficient") and oos_pop >= 35:
        score += 1
        checks.append(f"SUPPORTED: OOS T1 pop rate {oos_pop:.0f}% holds")

    risks: list[str] = []
    if sink >= 15:
        risks.append(f"REAL RISK: {sink:.0f}% sink-before-pop — discrete -10% dump days if you hold from trigger")
    if grind >= 4:
        risks.append(f"REAL RISK: {grind:.0f}% slow grind >15% in 30d without pop")
    risks.append("EXECUTION: ARA pop is intraday — daily backtest cannot model fill; watch ≠ buy at trigger")
    risks.append("ASYMMETRY: deep r5<=-12% raises BOTH pop and sink legs — filter matters")

    if score >= 5:
        label = "solid_watchlist_not_hold"
    elif score >= 3:
        label = "understood_with_caveats"
    else:
        label = "insufficient_clarity"

    return {
        "verdict": label,
        "score": score,
        "proven_checks": checks,
        "risks_and_limits": risks,
        "plain_english": (
            f"On T1 watch triggers: ~{pop_rate:.0f}% pop, ~{stagnant:.0f}% go nowhere, "
            f"~{sink:.0f}% dump before pop, ~{grind:.0f}% slow bleed. "
            "Non-wins are mostly stale — not random -50% traps — IF you do not hold from trigger."
        ),
    }


def build_outcome_certainty_report() -> dict[str, Any]:
    FRY_DIR.mkdir(parents=True, exist_ok=True)
    ep = pd.read_parquet(FRY_DIR / "fry_episodes.parquet")
    ep["trigger_date"] = pd.to_datetime(ep["trigger_date"])

    cols = ["date", "yahoo_symbol", "close", "return_1d", "name_type"]
    panel = pd.read_parquet(TURNAROUND, columns=cols)
    panel["date"] = pd.to_datetime(panel["date"])
    syms = set(ep["yahoo_symbol"].unique())
    panel = panel[panel["yahoo_symbol"].isin(syms)]

    outcomes = classify_trigger_outcomes(ep, panel)
    paths = _episode_paths(ep, panel)

    trig = pd.DataFrame()
    trig_path = FRY_DIR / "trigger_enriched.parquet"
    if trig_path.exists():
        trig = pd.read_parquet(trig_path)
        trig["date"] = pd.to_datetime(trig["date"])

    df = _merge_frame(ep, trig, outcomes, paths)

    t1 = df[df["is_t1"].fillna(False)]
    t2 = df[df["is_t2"].fillna(False)]
    quiet_only = df[df.get("trigger_cause", pd.Series(dtype=str)) == "quiet_accumulation"]

    report: dict[str, Any] = {
        "meta": {
            "n_episodes": int(len(df)),
            "date_min": str(df["trigger_date"].min().date()),
            "date_max": str(df["trigger_date"].max().date()),
            "oos_start": str(OOS_START.date()),
            "path_horizon_days": PATH_DAYS,
            "stagnant_band_pct": [STAGNANT_LO * 100, STAGNANT_HI * 100],
        },
        "all_triggers": _outcome_block(df),
        "t1_deep_dd_vol": _outcome_block(t1),
        "t2_return5d_lte_neg12": _outcome_block(t2),
        "quiet_only_triggers": _outcome_block(quiet_only),
        "oos": {
            "t1_deep_dd_vol": _outcome_block(t1[t1["era"] == "oos"]),
            "all": _outcome_block(df[df["era"] == "oos"]),
        },
        "ins": {
            "t1_deep_dd_vol": _outcome_block(t1[t1["era"] == "ins"]),
        },
        "mechanism_menu": [
            {
                "outcome": OUTCOME_POP_FIRST,
                "meaning": "Pop (+8% day) before any sink — the ARA watch target",
            },
            {
                "outcome": OUTCOME_POP_THEN_FADE,
                "meaning": "Pop then distribution sink — exit on pop, do not hold",
            },
            {
                "outcome": OUTCOME_FLAT,
                "meaning": "No pop, no sink — stagnant chop (~0% 30d). Safe to ignore.",
            },
            {
                "outcome": OUTCOME_SINK_ONLY,
                "meaning": "Discrete dump (≤-8% day) before pop — hold-from-trigger risk",
            },
            {
                "outcome": OUTCOME_GRIND_NO_POP,
                "meaning": "Slow bleed >15% in 30d without pop — worst non-win leg",
            },
        ],
    }
    report["certainty_verdict"] = _certainty_verdict(
        report["t1_deep_dd_vol"],
        report["oos"]["t1_deep_dd_vol"],
    )

    outcomes.to_parquet(FRY_DIR / "trigger_outcome_bilateral.parquet", index=False)
    OUT_JSON.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def certainty_blurb_for_tier(*, t1: bool = True) -> str:
    """One-line prior for watchlist UI."""
    if not OUT_JSON.exists():
        return "Outcome certainty report not built."
    rep = json.loads(OUT_JSON.read_text(encoding="utf-8"))
    block = rep.get("t1_deep_dd_vol" if t1 else "all_triggers", {})
    nb = block.get("non_pop_breakdown_pct") or {}
    return (
        f"~{block.get('pop_any_rate_pct', '?')}% pop | "
        f"~{nb.get('stagnant_flat', '?')}% stagnant | "
        f"~{nb.get('sink_before_pop', '?')}% sink | "
        f"~{nb.get('grind_bleed', '?')}% grind"
    )
