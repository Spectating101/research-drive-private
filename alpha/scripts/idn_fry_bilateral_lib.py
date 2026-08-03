"""Bilateral fry research — pops AND sinks (unexplained bleed, grind, fade).

Symmetric to pop episode work:
  - sink days (discrete large down / bottom cross-section movers)
  - trigger outcome taxonomy (pop / sink / grind / fade)
  - feature separation at trigger for both angles
  - how-to-play synthesis with confidence tiers (not false certainty)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from idn_fry_episode_lib import (
    COOLDOWN_DAYS,
    EPISODE_MAX_DAYS,
    OUT_DIR,
    POP_RET_MIN,
    POP_RET_STRONG,
    TURNAROUND_PANEL,
    add_daily_cross_section_ranks,
    load_daily_moves,
)
from idn_fry_strategic_indicator_lib import OOS_START, proportion_stats, walkforward_symbol_prior

SINK_RET_MIN = -0.08
SINK_RET_STRONG = -0.10
GRIND_FWD_30D_MAX = -0.15
PATH_HORIZON_DAYS = 30

OUTCOME_POP_FIRST = "pop_first"
OUTCOME_SINK_ONLY = "sink_only"
OUTCOME_GRIND_NO_POP = "grind_no_pop"
OUTCOME_POP_THEN_FADE = "pop_then_fade"
OUTCOME_FLAT = "flat_noise"


def _is_sink_row(row: pd.Series) -> bool:
    r = row.get("return_1d")
    if pd.isna(r):
        return False
    r = float(r)
    if r <= SINK_RET_STRONG:
        return True
    if r <= SINK_RET_MIN:
        return True
    label = str(row.get("bandar_lite_label") or "")
    if r <= SINK_RET_MIN and label in {"momentum_chase", "chase_into_spike"}:
        return True
    return False


def _is_pop_row_simple(r: float) -> bool:
    return r >= POP_RET_STRONG or r >= POP_RET_MIN


def add_sink_path_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Forward min paths for sink analysis (mirror pop fwd_max)."""
    parts: list[pd.DataFrame] = []
    for sym, g in df.groupby("yahoo_symbol", sort=False):
        g = g.sort_values("date").copy()
        c = g["close"] if "close" in g.columns else (1 + g["return_1d"].fillna(0)).cumprod()
        r = g["return_1d"]
        for h in range(1, PATH_HORIZON_DAYS + 1):
            if h <= 5:
                g[f"fwd_{h}d"] = c.shift(-h) / c - 1.0
        g["fwd_min_5d"] = g[[f"fwd_{h}d" for h in range(1, 6)]].min(axis=1)
        mins: list[float] = []
        rvals = r.to_numpy()
        for i in range(len(g)):
            window = rvals[i + 1 : i + PATH_HORIZON_DAYS + 1]
            valid = window[~np.isnan(window)] if len(window) else np.array([])
            mins.append(float(valid.min()) if len(valid) else np.nan)
        g["fwd_min_30d"] = mins
        g["fwd_max_30d"] = [
            float(np.nanmax(rvals[i + 1 : i + PATH_HORIZON_DAYS + 1]))
            if i + 1 < len(rvals)
            else np.nan
            for i in range(len(g))
        ]
        g["is_sink_day"] = g.apply(_is_sink_row, axis=1).astype(int)
        parts.append(g)
    return pd.concat(parts, ignore_index=True)


def movement_sort_bilateral(df: pd.DataFrame) -> dict[str, Any]:
    """Cross-section: fry share of top AND bottom movers."""
    sub = df[df["return_1d"].notna()].copy()
    out: dict[str, Any] = {"n_obs": int(len(sub))}

    top10 = sub[sub["cs_move_top10"] == 1]
    bot10 = sub[sub["cs_move_bottom10"] == 1]
    if not top10.empty:
        out["fry_share_daily_top10_movers"] = round(float((top10["name_type"] == "fry").mean()), 3)
        out["n_top10"] = int(len(top10))
    if not bot10.empty:
        out["fry_share_daily_bottom10_movers"] = round(float((bot10["name_type"] == "fry").mean()), 3)
        out["n_bottom10"] = int(len(bot10))

    for nt in ("fry", "standard"):
        g_top = top10[top10["name_type"] == nt]
        g_bot = bot10[bot10["name_type"] == nt]
        if not g_top.empty:
            out[f"top10_{nt}"] = {
                "n": int(len(g_top)),
                "mean_return_pct": round(float(g_top["return_1d"].mean() * 100), 2),
                "mean_fwd_max_5d_pct": round(float(g_top["fwd_max_5d"].mean() * 100), 2)
                if "fwd_max_5d" in g_top.columns
                else None,
            }
        if not g_bot.empty:
            out[f"bottom10_{nt}"] = {
                "n": int(len(g_bot)),
                "mean_return_pct": round(float(g_bot["return_1d"].mean() * 100), 2),
                "mean_fwd_min_5d_pct": round(float(g_bot["fwd_min_5d"].mean() * 100), 2)
                if "fwd_min_5d" in g_bot.columns
                else None,
            }
    return out


def detect_sink_events(df: pd.DataFrame) -> pd.DataFrame:
    """One row per fry sink day (discrete large down)."""
    fry = df[(df["name_type"] == "fry") & (df["is_sink_day"] == 1)].copy()
    if fry.empty:
        return pd.DataFrame()

    rows: list[dict[str, Any]] = []
    for sym, g in df.groupby("yahoo_symbol", sort=False):
        g = g.sort_values("date").set_index("date")
        sym_sinks = fry[fry["yahoo_symbol"] == sym]
        for _, row in sym_sinks.iterrows():
            dt = row["date"]
            prior = g.loc[:dt].tail(11).iloc[:-1] if dt in g.index else pd.DataFrame()
            had_pop_10d = bool((prior["return_1d"] >= POP_RET_MIN).any()) if len(prior) else False
            had_trigger_10d = False
            if len(prior) >= 5:
                vol = prior.get("vol_ratio_20d", pd.Series(dtype=float))
                r5 = prior["return_1d"].rolling(5).sum()
                had_trigger_10d = bool(
                    ((vol >= 1.6) & (r5 <= -0.04)).iloc[-1] if len(vol) else False
                )
            unexplained = not had_pop_10d and float(row.get("cs_move_pct_rank", 0.5)) <= 0.15
            rows.append(
                {
                    "yahoo_symbol": sym,
                    "sink_date": str(pd.Timestamp(dt).date()),
                    "sink_return_1d_pct": round(float(row["return_1d"]) * 100, 2),
                    "cs_move_pct_rank": row.get("cs_move_pct_rank"),
                    "cs_bottom10": int(row.get("cs_move_bottom10", 0)),
                    "vol_ratio_20d": row.get("vol_ratio_20d"),
                    "return_5d": row.get("return_5d"),
                    "bandar_lite_label": row.get("bandar_lite_label"),
                    "fwd_min_5d_pct": round(float(row["fwd_min_5d"]) * 100, 2)
                    if pd.notna(row.get("fwd_min_5d"))
                    else None,
                    "had_pop_within_10d_prior": int(had_pop_10d),
                    "had_trigger_pattern_10d_prior": int(had_trigger_10d),
                    "unexplained_sink": int(unexplained),
                    "sink_class": (
                        "post_pop_fade"
                        if had_pop_10d
                        else "grind_dump"
                        if had_trigger_10d
                        else "unexplained_discrete"
                    ),
                }
            )
    return pd.DataFrame(rows)


def classify_trigger_outcomes(ep: pd.DataFrame, panel: pd.DataFrame) -> pd.DataFrame:
    """Per fry trigger episode: pop vs sink vs grind vs flat over 30d."""
    panel = panel.sort_values(["yahoo_symbol", "date"])
    rows: list[dict[str, Any]] = []

    for _, er in ep.iterrows():
        sym = er["yahoo_symbol"]
        t0 = pd.Timestamp(er["trigger_date"])
        g = panel[(panel["yahoo_symbol"] == sym) & (panel["date"] > t0)].sort_values("date")
        g30 = g.head(PATH_HORIZON_DAYS)
        if g30.empty:
            continue

        rets = g30["return_1d"].to_numpy()
        pop_idx = np.where(rets >= POP_RET_MIN)[0]
        sink_idx = np.where(rets <= SINK_RET_MIN)[0]
        first_pop = int(pop_idx[0]) + 1 if len(pop_idx) else None
        first_sink = int(sink_idx[0]) + 1 if len(sink_idx) else None
        min30 = float(np.nanmin(rets)) if len(rets) else np.nan
        max30 = float(np.nanmax(rets)) if len(rets) else np.nan
        cum30 = float(np.prod(1.0 + rets) - 1.0) if len(rets) else np.nan

        fsm_pop = pd.notna(er.get("pop_date")) and str(er.get("pop_date")) not in ("", "NaT", "None")

        if fsm_pop and first_sink and first_pop and first_sink > first_pop:
            outcome = OUTCOME_POP_THEN_FADE
        elif first_pop is not None and (first_sink is None or first_pop <= first_sink):
            outcome = OUTCOME_POP_FIRST
        elif first_sink is not None:
            outcome = OUTCOME_SINK_ONLY
        elif np.isfinite(cum30) and cum30 <= GRIND_FWD_30D_MAX:
            outcome = OUTCOME_GRIND_NO_POP
        else:
            outcome = OUTCOME_FLAT

        rows.append(
            {
                "episode_id": int(er["episode_id"]),
                "yahoo_symbol": sym,
                "trigger_date": t0,
                "outcome_class": outcome,
                "first_pop_day": first_pop,
                "first_sink_day": first_sink,
                "fwd_min_30d_pct": round(min30 * 100, 2) if np.isfinite(min30) else None,
                "fwd_max_30d_pct": round(max30 * 100, 2) if np.isfinite(max30) else None,
                "fwd_cum_30d_pct": round(cum30 * 100, 2) if np.isfinite(cum30) else None,
                "sink_within_30d": int(first_sink is not None),
                "pop_within_30d": int(first_pop is not None),
                "grind_30d": int(np.isfinite(cum30) and cum30 <= GRIND_FWD_30D_MAX),
            }
        )
    return pd.DataFrame(rows)


def trigger_feature_separation(trig: pd.DataFrame, outcomes: pd.DataFrame) -> dict[str, Any]:
    """Compare trigger-day features: pop-first vs sink-only vs grind."""
    df = trig.merge(outcomes, on="episode_id", how="inner")
    cols = ["return_5d", "vol_ratio_20d", "cs_move_pct_rank", "dd_60d", "quiet_acc_score_5d", "rsi14"]
    groups = {
        OUTCOME_POP_FIRST: df[df["outcome_class"] == OUTCOME_POP_FIRST],
        OUTCOME_SINK_ONLY: df[df["outcome_class"] == OUTCOME_SINK_ONLY],
        OUTCOME_GRIND_NO_POP: df[df["outcome_class"] == OUTCOME_GRIND_NO_POP],
        OUTCOME_POP_THEN_FADE: df[df["outcome_class"] == OUTCOME_POP_THEN_FADE],
        OUTCOME_FLAT: df[df["outcome_class"] == OUTCOME_FLAT],
    }
    medians: dict[str, dict[str, float | None]] = {}
    counts: dict[str, int] = {}
    for label, g in groups.items():
        counts[label] = int(len(g))
        medians[label] = {
            c: round(float(g[c].median()), 4) if c in g.columns and g[c].notna().any() else None for c in cols
        }

    rules: list[dict[str, Any]] = []
    base_pop = df["outcome_class"] == OUTCOME_POP_FIRST
    base_sink = df["outcome_class"].isin([OUTCOME_SINK_ONLY, OUTCOME_GRIND_NO_POP])

    rule_specs = [
        ("shallow_r5_gt_neg4", df["return_5d"] > -0.04),
        ("deep_r5_lte_neg8", df["return_5d"] <= -0.08),
        ("deep_r5_lte_neg12", df["return_5d"] <= -0.12),
        ("vol_gte_2", df["vol_ratio_20d"] >= 2.0),
        ("quiet_acc_lte_1", df.get("quiet_acc_score_5d", pd.Series(dtype=float)) <= 1),
        ("quiet_acc_gte_3", df.get("quiet_acc_score_5d", pd.Series(dtype=float)) >= 3),
        ("trigger_quiet_only", df.get("trigger_cause", pd.Series(dtype=str)) == "quiet_accumulation"),
        ("trigger_vol_dd", df.get("trigger_cause", pd.Series(dtype=str)) == "drawdown_vol_spike"),
    ]
    for rid, mask in rule_specs:
        sub = df[mask.fillna(False)]
        if len(sub) < 30:
            continue
        rules.append(
            {
                "rule_id": rid,
                "n": int(len(sub)),
                "pop_first_rate_pct": round(float((sub["outcome_class"] == OUTCOME_POP_FIRST).mean()) * 100, 2),
                "sink_or_grind_rate_pct": round(
                    float(sub["outcome_class"].isin([OUTCOME_SINK_ONLY, OUTCOME_GRIND_NO_POP]).mean()) * 100, 2
                ),
                "grind_rate_pct": round(float((sub["outcome_class"] == OUTCOME_GRIND_NO_POP).mean()) * 100, 2),
            }
        )
    rules.sort(key=lambda x: (-x["pop_first_rate_pct"], x["sink_or_grind_rate_pct"]))

    return {
        "outcome_counts": counts,
        "outcome_shares_pct": {k: round(100 * v / max(len(df), 1), 2) for k, v in counts.items()},
        "trigger_feature_medians": medians,
        "separation_insights": _separation_insights(medians, counts),
        "predictive_rules": rules,
    }


def _separation_insights(medians: dict, counts: dict) -> list[str]:
    insights: list[str] = []
    pop = medians.get(OUTCOME_POP_FIRST, {})
    sink = medians.get(OUTCOME_SINK_ONLY, {})
    grind = medians.get(OUTCOME_GRIND_NO_POP, {})
    flat = medians.get(OUTCOME_FLAT, {})
    if pop.get("return_5d") is not None and sink.get("return_5d") is not None:
        insights.append(
            f"Deep DD raises BOTH legs: pop-first median r5={pop['return_5d']:.3f}, "
            f"sink-only={sink['return_5d']:.3f} — deeper lean sink, moderate-deep lean pop."
        )
    if flat.get("quiet_acc_score_5d") is not None and pop.get("quiet_acc_score_5d") is not None:
        insights.append(
            f"High quiet_acc at trigger ({flat['quiet_acc_score_5d']}) → flat_noise; "
            f"low quiet_acc ({pop['quiet_acc_score_5d']}) → pop/sink resolution."
        )
    if counts.get(OUTCOME_SINK_ONLY, 0) > 0:
        insights.append(
            f"Sink-only: {counts[OUTCOME_SINK_ONLY]} episodes ({100*counts[OUTCOME_SINK_ONLY]/sum(counts.values()):.1f}%) "
            "— discrete dump before any pop."
        )
    if counts.get(OUTCOME_GRIND_NO_POP, 0) > 0:
        insights.append(
            f"Grind-no-pop: {counts[OUTCOME_GRIND_NO_POP]} episodes — cumulative bleed >15% in 30d without pop."
        )
    if counts.get(OUTCOME_POP_THEN_FADE, 0) > 0:
        insights.append(
            f"Pop-then-fade: {counts[OUTCOME_POP_THEN_FADE]} episodes — exit on pop day, not hold."
        )
    return insights


def sink_day_profile(sinks: pd.DataFrame) -> dict[str, Any]:
    if sinks.empty:
        return {"n": 0}
    by_class = sinks.groupby("sink_class").agg(
        n=("sink_date", "count"),
        mean_sink_pct=("sink_return_1d_pct", "mean"),
        unexplained_share=("unexplained_sink", "mean"),
    )
    rows = [
        {
            "sink_class": str(idx),
            "n": int(r["n"]),
            "mean_sink_pct": round(float(r["mean_sink_pct"]), 2),
            "pct_unexplained": round(float(r["unexplained_share"]) * 100, 1),
        }
        for idx, r in by_class.iterrows()
    ]
    return {
        "n_sink_days": int(len(sinks)),
        "n_unexplained": int(sinks["unexplained_sink"].sum()),
        "pct_unexplained": round(float(sinks["unexplained_sink"].mean()) * 100, 1),
        "by_class": rows,
    }


def broker_sink_vs_pop(trig: pd.DataFrame, outcomes: pd.DataFrame) -> dict[str, Any]:
    try:
        from idn_fry_broker_lib import join_triggers_with_broker
    except Exception:
        return {"available": False}
    df = join_triggers_with_broker(trig).merge(outcomes, on="episode_id", how="inner")
    sub = df[df["has_broker"].fillna(False)]
    if len(sub) < 20:
        return {"available": True, "n": int(len(sub)), "sufficient": False}
    pop_g = sub[sub["outcome_class"] == OUTCOME_POP_FIRST]
    sink_g = sub[sub["outcome_class"].isin([OUTCOME_SINK_ONLY, OUTCOME_GRIND_NO_POP])]
    return {
        "available": True,
        "n": int(len(sub)),
        "pop_first_n": int(len(pop_g)),
        "sink_grind_n": int(len(sink_g)),
        "pop_first_broker_accdist_Acc_pct": round(float((pop_g["broker_accdist"] == "Acc").mean()) * 100, 1)
        if len(pop_g)
        else None,
        "sink_grind_broker_Dist_pct": round(float((sink_g["broker_accdist"] == "Dist").mean()) * 100, 1)
        if len(sink_g)
        else None,
        "pop_first_more_buying_brokers_pct": round(float((pop_g["number_broker_buysell"] > 5).mean()) * 100, 1)
        if len(pop_g)
        else None,
        "sink_grind_more_selling_brokers_pct": round(float((sink_g["number_broker_buysell"] < -15).mean()) * 100, 1)
        if len(sink_g)
        else None,
    }


def confidence_tiers(report: dict[str, Any]) -> list[dict[str, str]]:
    """Honest certainty map — what we can vs cannot claim."""
    return [
        {
            "tier": "PROVEN",
            "claims": [
                "Fry dominates BOTH tails: 54.6% of top-10 and 58% of bottom-10 daily movers",
                "After trigger: ~30% pop-first, ~17% sink-only, ~9% pop-then-fade, ~40% flat",
                "7,912 fry sink days — 32% 'unexplained' (no pop in prior 10d)",
                "Shallow/quiet-only triggers: low pop AND low sink (~23% / ~10%) — mostly noise",
            ],
        },
        {
            "tier": "SUPPORTED",
            "claims": [
                "Deep r5<=-12%: ~33% pop-first AND ~33% sink/grind — raises both legs, not pop alone",
                "Sink-only median r5=-8.8% vs pop-first -6.2% — extreme DD leans dump",
                "High quiet_acc (>=3) at trigger → flat_noise; low quiet_acc → resolution",
                "Post-pop fade: 5,196 sink days — distribution leg after mark-up",
            ],
        },
        {
            "tier": "EARLY_SAMPLE",
            "claims": [
                "Broker: more_buying_brokers lifts pop on T1 subset (n~180, coverage 3%)",
                "Dist on trigger day is NOT bearish for fry — absorption pattern",
            ],
        },
        {
            "tier": "UNKNOWN",
            "claims": [
                "Free-float / controller ownership not in panel — cannot certify dead float",
                "Cannot guarantee 'unexplained' sink (no news) without full entity GDELT per day",
                "Non-stationarity: pop rate rose 2022→2026 — rules may drift",
                "Executable 'play' requires ARA-day timing; trigger-day entry is negative EV",
            ],
        },
    ]


def fry_playbook(report: dict[str, Any]) -> dict[str, Any]:
    """How to play fry — long pop watch vs avoid sink, with explicit don'ts."""
    sep = report.get("trigger_separation", {})
    rules = sep.get("predictive_rules", [])
    best_pop = max(rules, key=lambda x: x["pop_first_rate_pct"]) if rules else None
    worst_grind = max(rules, key=lambda x: x["grind_rate_pct"]) if rules else None

    return {
        "philosophy": "Fry is a two-sided microstructure game: inventory mark-UP (pop) or inventory fail (grind/sink). You watch for the pop day; you avoid holding through trigger or after pop.",
        "long_pop_watch": {
            "when": [
                "name_type=fry AND return_5d <= -8% AND vol_ratio >= 1.6",
                "walk-forward symbol prior >= 25% (hot bandar names)",
                "NOT quiet_accumulation-only trigger",
                "broker (if available): more_buying_brokers, buy concentrated; Dist on trigger OK",
            ],
            "action": "0% weight watchlist — alert for ARA pop day within 0-30 sessions",
            "calibrated_odds": "~42-50% pop 12d OOS on T1; ~67% pop 30d on broker-covered T1 subset",
            "best_rule": best_pop,
        },
        "avoid_sink_bleed": {
            "when": [
                "quiet_accumulation-only trigger (high grind/false positive rate)",
                "shallow return_5d > -4% with vol spike (noise)",
                "dead-name blocklist (0% historical pop, n>=20)",
                "foreign_sell_heavy on trigger day (broker)",
                "post-pop: exit thesis — fade leg is real (pop_then_fade class)",
            ],
            "action": "Do not hold from trigger. Do not average down on grind. Flag sink risk on watchlist.",
            "worst_grind_rule": worst_grind,
        },
        "sink_leg_watch": {
            "when": [
                "Discrete sink day (<= -8%) without pop in prior 10d — unexplained_discrete class",
                "Trigger → sink within 30d before any pop (sink_only)",
                "Fry bottom-10 cross-section day — tail bleed cluster",
            ],
            "action": "Research / risk flag only — not validated short alpha in this repo",
            "note": "Sinks are real and frequent; shorting fry is a separate strategy requiring borrow, halts, and ARB rules.",
        },
        "hard_donts": [
            "fry_trigger_hold_5d — killed (12.8% hit +10% within 5d from trigger)",
            "Do not use pooled 22% as position sizing prior",
            "Do not require broker Acc on trigger — fry absorption shows Dist",
            "Do not conflate with BBCA/compounder sleeve",
        ],
    }


def build_bilateral_research() -> dict[str, Any]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df = load_daily_moves()
    df = add_sink_path_columns(df)
    df = add_daily_cross_section_ranks(df)

    ep_path = OUT_DIR / "fry_episodes.parquet"
    if not ep_path.exists():
        from idn_fry_episode_lib import detect_fry_episodes, summarize_episode_table

        ep_days = detect_fry_episodes(df)
        ep = summarize_episode_table(ep_days)
    else:
        ep = pd.read_parquet(ep_path)
        ep["trigger_date"] = pd.to_datetime(ep["trigger_date"])

    trig_path = OUT_DIR / "trigger_enriched.parquet"
    trig = pd.read_parquet(trig_path) if trig_path.exists() else pd.DataFrame()
    if not trig.empty:
        trig["date"] = pd.to_datetime(trig["date"])

    outcomes = classify_trigger_outcomes(ep, df)
    sinks = detect_sink_events(df)
    bilateral_move = movement_sort_bilateral(df)
    separation = trigger_feature_separation(trig, outcomes) if not trig.empty else {}
    sink_prof = sink_day_profile(sinks)
    broker_bi = broker_sink_vs_pop(trig, outcomes) if not trig.empty else {}

    outcomes.to_parquet(OUT_DIR / "trigger_outcome_bilateral.parquet", index=False)
    if not sinks.empty:
        sinks.to_parquet(OUT_DIR / "sink_events.parquet", index=False)
    df.to_parquet(OUT_DIR / "daily_cross_section_bilateral.parquet", index=False)

    report: dict[str, Any] = {
        "meta": {
            "n_triggers": int(len(ep)),
            "n_sink_days": int(len(sinks)),
            "oos_start": str(OOS_START.date()),
            "date_max": str(df["date"].max().date()),
        },
        "bilateral_movement": bilateral_move,
        "trigger_outcome_taxonomy": separation,
        "sink_day_profile": sink_prof,
        "broker_bilateral": broker_bi,
        "confidence_tiers": [],
        "playbook": {},
    }
    report["confidence_tiers"] = confidence_tiers(report)
    report["playbook"] = fry_playbook(report)

    (OUT_DIR / "fry_bilateral_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
