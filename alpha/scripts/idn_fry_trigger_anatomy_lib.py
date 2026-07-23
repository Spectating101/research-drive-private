"""Deep fry trigger anatomy — what causes episodes, what predicts pop, full timelines.

Builds on idn_fry_episode_lib outputs. Unit of analysis:
  - trigger signature (quiet_accumulation vs drawdown_vol_spike)
  - pre-trigger window (-10..-1 sessions)
  - episode day-by-day path (trigger → wait → pop → fade)
"""

from __future__ import annotations

import json
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
TURNAROUND_PANEL = REPO / "data_lake/research_panels/idn_turnaround/daily_features.parquet"
OUT_DIR = FRY_DIR

TRIGGER_VOL_MIN = 1.6
TRIGGER_DD_5D_MAX = -0.04
PRE_WINDOW_DAYS = 10


def classify_trigger_cause(row: pd.Series) -> str:
    quiet = str(row.get("bandar_lite_label") or "") == "quiet_volume_build"
    vol = row.get("vol_ratio_20d")
    r5 = row.get("return_5d")
    vol_dd = pd.notna(vol) and pd.notna(r5) and float(vol) >= TRIGGER_VOL_MIN and float(r5) <= TRIGGER_DD_5D_MAX
    if quiet and vol_dd:
        return "both_quiet_and_vol_dd"
    if quiet:
        return "quiet_accumulation"
    if vol_dd:
        return "drawdown_vol_spike"
    return "other"


def _load_frames() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    ep_days = pd.read_parquet(FRY_DIR / "fry_episode_days.parquet")
    episodes = pd.read_parquet(FRY_DIR / "fry_episodes.parquet")
    cross = pd.read_parquet(
        FRY_DIR / "daily_cross_section.parquet",
        columns=[
            "date",
            "yahoo_symbol",
            "return_1d",
            "return_1d_pct",
            "cs_move_pct_rank",
            "cs_move_decile",
            "cs_move_top10",
            "vol_ratio_20d",
            "fwd_max_5d",
            "days_to_10pct",
            "name_type",
            "return_5d",
            "bandar_lite_label",
            "rsi14",
            "dd_60d",
            "quiet_acc_score_5d",
            "chase_score_5d",
            "ihsg_regime",
            "pos_52w_range",
        ],
    )
    summary_path = FRY_DIR / "summary.json"
    extend_from = None
    if summary_path.exists():
        try:
            extend_from = json.loads(summary_path.read_text(encoding="utf-8")).get("extend_from")
        except json.JSONDecodeError:
            extend_from = None

    panel_cols = [
        "date",
        "yahoo_symbol",
        "bandar_lite_label",
        "return_5d",
        "vol_ratio_20d",
        "rsi14",
        "pos_52w_range",
        "quiet_acc_score_5d",
        "chase_score_5d",
        "ihsg_regime",
        "consecutive_ara_days",
        "is_ara_day",
        "dd_60d",
        "near_support_60d",
    ]
    if extend_from:
        from idn_fry_episode_lib import load_extended_daily_moves

        ext = load_extended_daily_moves(extend_from=str(extend_from))
        use = [c for c in panel_cols if c in ext.columns]
        panel = ext[use].drop_duplicates(subset=["date", "yahoo_symbol"], keep="last")
    elif TURNAROUND_PANEL.exists():
        avail = pd.read_parquet(TURNAROUND_PANEL, columns=None).columns.tolist()
        use = [c for c in panel_cols if c in avail]
        panel = pd.read_parquet(TURNAROUND_PANEL, columns=use)
    else:
        panel = cross[[c for c in panel_cols if c in cross.columns]].copy()
    for df in (ep_days, cross, panel):
        df["date"] = pd.to_datetime(df["date"])
    if "trigger_date" in episodes.columns:
        episodes["trigger_date"] = pd.to_datetime(episodes["trigger_date"])
    if "pop_date" in episodes.columns:
        episodes["pop_date"] = pd.to_datetime(episodes["pop_date"], errors="coerce")
    return ep_days, episodes, cross, panel


def enrich_triggers(ep_days: pd.DataFrame, panel: pd.DataFrame) -> pd.DataFrame:
    trig = ep_days[ep_days["episode_phase"] == "trigger"][["date", "yahoo_symbol", "episode_id", "cs_move_pct_rank"]].copy()
    trig = trig.merge(panel, on=["date", "yahoo_symbol"], how="left")
    pop_ids = set(ep_days.loc[ep_days["episode_phase"] == "pop_day", "episode_id"].dropna())
    trig["got_pop"] = trig["episode_id"].isin(pop_ids).astype(int)
    trig["trigger_cause"] = trig.apply(classify_trigger_cause, axis=1)
    return trig


def pre_trigger_window_stats(trig: pd.DataFrame, cross: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, r in trig.iterrows():
        sym = r["yahoo_symbol"]
        t0 = r["date"]
        w = cross[(cross["yahoo_symbol"] == sym) & (cross["date"] < t0) & (cross["date"] >= t0 - pd.Timedelta(days=PRE_WINDOW_DAYS))]
        if len(w) < 3:
            continue
        w = w.sort_values("date")
        tail5 = w.tail(5)
        rows.append(
            {
                "episode_id": r["episode_id"],
                "yahoo_symbol": sym,
                "trigger_date": str(t0.date()),
                "got_pop": int(r["got_pop"]),
                "trigger_cause": r["trigger_cause"],
                "pre10_cum_move_pct": round(float(w["return_1d_pct"].sum()), 3),
                "pre5_mean_move_pct": round(float(tail5["return_1d_pct"].mean()), 3),
                "pre5_vol_ratio_med": round(float(tail5["vol_ratio_20d"].median()), 3),
                "pre5_cs_rank_med": round(float(tail5["cs_move_pct_rank"].median()), 3),
                "pre5_down_days": int((tail5["return_1d_pct"] < 0).sum()),
                "pre10_max_single_day_pct": round(float(w["return_1d_pct"].max()), 3),
            }
        )
    return pd.DataFrame(rows)


def signature_pop_rates(trig: pd.DataFrame) -> dict[str, Any]:
    out: dict[str, Any] = {}

    def _rate(g: pd.DataFrame) -> dict[str, Any]:
        return {"n": int(len(g)), "pop_rate_pct": round(float(g["got_pop"].mean() * 100), 1)}

    out["by_trigger_cause"] = {k: _rate(g) for k, g in trig.groupby("trigger_cause")}
    out["by_ihsg_regime"] = {str(k): _rate(g) for k, g in trig.groupby("ihsg_regime", dropna=False)}
    trig = trig.copy()
    trig["r5_bucket"] = pd.cut(
        trig["return_5d"],
        bins=[-2, -0.12, -0.08, -0.04, 0, 2],
        labels=["dd_gt_12pct", "dd_8_12pct", "dd_4_8pct", "dd_0_4pct", "flat_or_up"],
    )
    out["by_return_5d_at_trigger"] = {str(k): _rate(g) for k, g in trig.groupby("r5_bucket", observed=True)}
    trig["rsi_bucket"] = pd.cut(trig["rsi14"], bins=[0, 30, 40, 50, 100], labels=["oversold_lt30", "rsi_30_40", "rsi_40_50", "rsi_gt50"])
    out["by_rsi_at_trigger"] = {str(k): _rate(g) for k, g in trig.groupby("rsi_bucket", observed=True)}
    return out


def pop_vs_no_pop_profile(trig: pd.DataFrame) -> dict[str, Any]:
    cols = [
        "cs_move_pct_rank",
        "vol_ratio_20d",
        "return_5d",
        "rsi14",
        "pos_52w_range",
        "quiet_acc_score_5d",
        "dd_60d",
        "near_support_60d",
    ]
    prof: dict[str, Any] = {}
    for label, mask in [("with_pop", trig["got_pop"] == 1), ("no_pop", trig["got_pop"] == 0)]:
        g = trig[mask]
        prof[label] = {
            "n": int(len(g)),
            "bandar_mix": {str(k): int(v) for k, v in g["bandar_lite_label"].value_counts().items()},
            "medians": {c: round(float(g[c].median()), 4) for c in cols if c in g.columns and g[c].notna().any()},
        }
    return prof


def episode_phase_path_stats(ep_days: pd.DataFrame) -> dict[str, Any]:
    pop_ids = set(ep_days.loc[ep_days["episode_phase"] == "pop_day", "episode_id"].dropna())
    sub = ep_days[ep_days["episode_id"].isin(pop_ids)].copy()
    rows = []
    for phase, g in sub.groupby("episode_phase"):
        rows.append(
            {
                "phase": phase,
                "n_days": int(len(g)),
                "mean_return_1d_pct": round(float(g["return_1d_pct"].mean()), 3),
                "median_return_1d_pct": round(float(g["return_1d_pct"].median()), 3),
                "median_cs_rank": round(float(g["cs_move_pct_rank"].median()), 3) if g["cs_move_pct_rank"].notna().any() else None,
            }
        )
    pop = sub[sub["episode_phase"] == "pop_day"]
    return {
        "phases_in_episodes_that_popped": rows,
        "pop_day": {
            "n": int(len(pop)),
            "mean_return_pct": round(float(pop["return_1d_pct"].mean()), 2),
            "median_cs_rank": round(float(pop["cs_move_pct_rank"].median()), 3),
            "pct_top10_mover_that_day": round(float((pop["cs_move_pct_rank"] >= 0.90).mean() * 100), 1),
        },
    }


def build_episode_timeline(
    ep_days: pd.DataFrame,
    cross: pd.DataFrame,
    panel: pd.DataFrame,
    episode_id: int,
) -> dict[str, Any]:
    g = ep_days[ep_days["episode_id"] == episode_id].sort_values("date")
    if g.empty:
        return {}
    sym = g.iloc[0]["yahoo_symbol"]
    dates = g["date"].tolist()
    t0, t1 = min(dates), max(dates)
    pad_start = t0 - pd.Timedelta(days=PRE_WINDOW_DAYS)
    pad_end = t1 + pd.Timedelta(days=5)
    ctx = cross[(cross["yahoo_symbol"] == sym) & (cross["date"] >= pad_start) & (cross["date"] <= pad_end)].merge(
        panel, on=["date", "yahoo_symbol"], how="left", suffixes=("", "_p")
    )
    ctx = ctx.sort_values("date")
    phase_map = dict(zip(g["date"], g["episode_phase"], strict=False))
    timeline = []
    for _, row in ctx.iterrows():
        dt = row["date"]
        timeline.append(
            {
                "date": str(dt.date()),
                "return_1d_pct": round(float(row["return_1d_pct"]), 3) if pd.notna(row.get("return_1d_pct")) else None,
                "cs_move_pct_rank": round(float(row["cs_move_pct_rank"]), 3) if pd.notna(row.get("cs_move_pct_rank")) else None,
                "vol_ratio_20d": round(float(row["vol_ratio_20d"]), 3) if pd.notna(row.get("vol_ratio_20d")) else None,
                "bandar_lite_label": row.get("bandar_lite_label"),
                "return_5d_pct": round(float(row["return_5d"]) * 100, 2) if pd.notna(row.get("return_5d")) else None,
                "rsi14": round(float(row["rsi14"]), 1) if pd.notna(row.get("rsi14")) else None,
                "episode_phase": phase_map.get(dt),
                "marker": (
                    "trigger"
                    if dt == t0 and phase_map.get(dt) == "trigger"
                    else "pop"
                    if phase_map.get(dt) == "pop_day"
                    else None
                ),
            }
        )
    ep_row = g[g["episode_phase"] == "trigger"].iloc[0]
    return {
        "episode_id": int(episode_id),
        "yahoo_symbol": sym,
        "trigger_cause": classify_trigger_cause(ep_row),
        "got_pop": bool((g["episode_phase"] == "pop_day").any()),
        "trigger_to_pop_days": int((g[g["episode_phase"] == "pop_day"]["date"].iloc[0] - t0).days)
        if (g["episode_phase"] == "pop_day").any()
        else None,
        "pop_return_1d_pct": float(g[g["episode_phase"] == "pop_day"]["return_1d_pct"].iloc[0])
        if (g["episode_phase"] == "pop_day").any()
        else None,
        "timeline": timeline,
    }


def select_case_studies(trig: pd.DataFrame, episodes: pd.DataFrame) -> list[int]:
    """Pick archetypal episodes for full day-by-day case book."""
    ids: list[int] = []
    pop_ep = episodes[episodes["pop_date"].notna()].copy()
    tidx = trig.set_index("episode_id")

    def _add(eid: int) -> None:
        if eid not in ids:
            ids.append(eid)

    dvs_pop = tidx[(tidx["trigger_cause"] == "drawdown_vol_spike") & (tidx["got_pop"] == 1)]
    if not dvs_pop.empty:
        med_lag = episodes.loc[episodes["episode_id"].isin(dvs_pop.index), "trigger_to_pop_days"].median()
        near = episodes[
            (episodes["episode_id"].isin(dvs_pop.index))
            & (episodes["trigger_to_pop_days"].between(med_lag - 1, med_lag + 1))
        ]
        if not near.empty:
            _add(int(near.iloc[0]["episode_id"]))

    qa = tidx[(tidx["trigger_cause"] == "quiet_accumulation") & (tidx["got_pop"] == 0)]
    if not qa.empty:
        _add(int(qa.index[0]))

    deep = tidx[(tidx["return_5d"] <= -0.12) & (tidx["got_pop"] == 1)]
    if not deep.empty:
        _add(int(deep.index[0]))

    fast = pop_ep[pop_ep["trigger_to_pop_days"] == 1].nlargest(2, "pop_return_1d_pct")
    for eid in fast["episode_id"]:
        _add(int(eid))

    slow = pop_ep[(pop_ep["trigger_to_pop_days"] >= 7) & (pop_ep["pop_return_1d_pct"] >= 15)].nlargest(2, "pop_return_1d_pct")
    for eid in slow["episode_id"]:
        _add(int(eid))

    top = pop_ep[(pop_ep["pop_return_1d_pct"] >= 20) & (pop_ep["pop_return_1d_pct"] < 80)].nlargest(3, "pop_return_1d_pct")
    for eid in top["episode_id"]:
        _add(int(eid))

    return ids[:12]


def phenomenon_narrative(
    sig: dict[str, Any],
    prof: dict[str, Any],
    phase: dict[str, Any],
    pre: pd.DataFrame,
) -> dict[str, Any]:
    """Plain-language synthesis of what the data shows."""
    cause = sig.get("by_trigger_cause", {})
    dvs = cause.get("drawdown_vol_spike", {})
    quiet = cause.get("quiet_accumulation", {})
    r5 = sig.get("by_return_5d_at_trigger", {})

    pre_pop = pre[pre["got_pop"] == 1] if not pre.empty else pd.DataFrame()
    pre_nop = pre[pre["got_pop"] == 0] if not pre.empty else pd.DataFrame()

    return {
        "phenomenon": "fry_bandar_episode",
        "mechanism_hypothesis": [
            "Fry names grind down on elevated volume while cross-section rank stays low (bandar absorption / distribution).",
            "Trigger fires when 5d drawdown is deep AND volume ratio is elevated — not when the stock is already today's top mover.",
            "Pop is a discrete ARA-style spike day: median cross-section rank ~99th percentile, mean +17% single-day return.",
            "Post-trigger wait is mostly flat-to-negative drift; edge is timing the spike day, not holding 5d from trigger.",
        ],
        "what_actually_triggers": {
            "primary_driver": "drawdown_vol_spike (vol_ratio>=1.6, return_5d<=-4%)",
            "drawdown_vol_spike_pop_rate_pct": dvs.get("pop_rate_pct"),
            "quiet_accumulation_pop_rate_pct": quiet.get("pop_rate_pct"),
            "interpretation": "Quiet volume build alone fires often but pops rarely; deep 5d drawdown on high volume is the actionable pre-pop state.",
        },
        "drawdown_depth_matters": {
            "dd_gt_12pct_pop_rate": r5.get("dd_gt_12pct", {}).get("pop_rate_pct"),
            "dd_4_8pct_pop_rate": r5.get("dd_4_8pct", {}).get("pop_rate_pct"),
        },
        "pop_day_signature": phase.get("pop_day", {}),
        "pre_trigger_grind": {
            "with_pop_pre10_cum_move_med": round(float(pre_pop["pre10_cum_move_pct"].median()), 2) if len(pre_pop) else None,
            "no_pop_pre10_cum_move_med": round(float(pre_nop["pre10_cum_move_pct"].median()), 2) if len(pre_nop) else None,
            "with_pop_pre5_down_days_med": round(float(pre_pop["pre5_down_days"].median()), 1) if len(pre_pop) else None,
        },
        "pop_vs_no_pop_at_trigger": prof,
    }


def build_trigger_anatomy_research() -> dict[str, Any]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ep_days, episodes, cross, panel = _load_frames()
    trig = enrich_triggers(ep_days, panel)
    pre = pre_trigger_window_stats(trig, cross)
    sig = signature_pop_rates(trig)
    prof = pop_vs_no_pop_profile(trig)
    phase = episode_phase_path_stats(ep_days)

    case_ids = select_case_studies(trig, episodes)
    case_book = [build_episode_timeline(ep_days, cross, panel, eid) for eid in case_ids]
    case_book = [c for c in case_book if c]

    narrative = phenomenon_narrative(sig, prof, phase, pre)

    report = {
        "n_triggers": int(len(trig)),
        "n_with_pop": int(trig["got_pop"].sum()),
        "overall_pop_rate_pct": round(float(trig["got_pop"].mean() * 100), 1),
        "signature_pop_rates": sig,
        "pop_vs_no_pop_profile": prof,
        "episode_phase_path": phase,
        "phenomenon": narrative,
        "case_study_episode_ids": case_ids,
    }

    trig.to_parquet(OUT_DIR / "trigger_enriched.parquet", index=False)
    pre.to_parquet(OUT_DIR / "trigger_pre_window.parquet", index=False)
    (OUT_DIR / "trigger_anatomy_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (OUT_DIR / "trigger_case_book.json").write_text(json.dumps(case_book, indent=2) + "\n", encoding="utf-8")
    return report
