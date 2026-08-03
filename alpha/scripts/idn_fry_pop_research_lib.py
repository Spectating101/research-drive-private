"""Full-timeline fry pop research — episodes, trigger lifts, huge-winner patterns, catalog."""

from __future__ import annotations

import json
import math
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
FRY_DIR = REPO / "data_lake/research_panels/idn_fry_episode"
CATALOG_JSON = FRY_DIR / "fry_pop_pattern_catalog.json"
HUGE_WIN_JSON = FRY_DIR / "fry_huge_winner_patterns.json"
REPORT_JSON = FRY_DIR / "fry_pop_research_report.json"

MIN_TRIGGER_N = 40
MIN_POP_LIFT = 1.15
HUGE_WIN_PCT = 30.0
BIG_WIN_PCT = 20.0


def _pop_rate(g: pd.DataFrame) -> dict[str, Any]:
    if g.empty:
        return {"n": 0, "pop_rate_pct": 0.0}
    return {"n": int(len(g)), "pop_rate_pct": round(float(g["got_pop"].mean() * 100), 1)}


def mine_trigger_pop_patterns(trig: pd.DataFrame) -> list[dict[str, Any]]:
    """Feature lifts for got_pop at fry trigger (multi-year trigger rows)."""
    if trig.empty:
        return []
    base = float(trig["got_pop"].mean())
    if base <= 0:
        return []
    rows: list[dict[str, Any]] = []

    def _add(pattern: str, feature: str, mask: pd.Series) -> None:
        g = trig[mask]
        if len(g) < MIN_TRIGGER_N:
            return
        rate = float(g["got_pop"].mean())
        rows.append(
            {
                "pattern": pattern,
                "feature": feature,
                "n": int(len(g)),
                "pop_rate_pct": round(rate * 100, 1),
                "baseline_pop_rate_pct": round(base * 100, 1),
                "pop_lift": round(rate / base, 3) if base > 0 else None,
                "source": "trigger_anatomy",
            }
        )

    for cause, g in trig.groupby("trigger_cause"):
        _add(f"trigger_cause={cause}", "trigger_cause", trig["trigger_cause"] == cause)

    for regime, g in trig.groupby("ihsg_regime", dropna=False):
        if pd.isna(regime):
            continue
        _add(f"ihsg_regime={regime}", "ihsg_regime", trig["ihsg_regime"] == regime)

    for label, feat, val in (
        ("bandar_lite_label=quiet_volume_build", "bandar_lite_label", "quiet_volume_build"),
        ("bandar_lite_label=squeeze_from_drawdown", "bandar_lite_label", "squeeze_from_drawdown"),
        ("bandar_lite_label=chase_into_spike", "bandar_lite_label", "chase_into_spike"),
    ):
        _add(label, feat, trig["bandar_lite_label"] == val)

    _add("return_5d:x<-0.12", "return_5d", trig["return_5d"] < -0.12)
    _add("return_5d:x<-0.08", "return_5d", trig["return_5d"] < -0.08)
    _add("return_5d:x<-0.04", "return_5d", trig["return_5d"] < -0.04)
    _add("vol_ratio_20d:x>=2.5", "vol_ratio_20d", trig["vol_ratio_20d"] >= 2.5)
    _add("vol_ratio_20d:x>=1.6", "vol_ratio_20d", trig["vol_ratio_20d"] >= 1.6)
    _add("dd_60d:x<-0.2", "dd_60d", trig["dd_60d"] < -0.2)
    _add("dd_60d:x<-0.3", "dd_60d", trig["dd_60d"] < -0.3)
    _add("rsi14:x<30", "rsi14", trig["rsi14"] < 30)
    _add("quiet_acc_score_5d:x>=3", "quiet_acc_score_5d", trig["quiet_acc_score_5d"] >= 3)
    _add("chase_score_5d:x>=2", "chase_score_5d", trig["chase_score_5d"] >= 2)
    _add("drawdown_vol_spike", "composite", (trig["vol_ratio_20d"] >= 1.6) & (trig["return_5d"] <= -0.04))
    _add("deep_dd_vol_spike", "composite", (trig["vol_ratio_20d"] >= 1.6) & (trig["return_5d"] <= -0.12))

    # cs rank at trigger — low rank days pop more
    _add("cs_move_pct_rank:x<0.5", "cs_move_pct_rank", trig["cs_move_pct_rank"] < 0.5)
    _add("cs_move_pct_rank:x<0.3", "cs_move_pct_rank", trig["cs_move_pct_rank"] < 0.3)

    rows.sort(key=lambda x: (-(x.get("pop_lift") or 0), -x["n"]))
    return rows


def mine_fry_huge_winner_patterns(*, extend_from: str = "2019-07-01") -> dict[str, Any]:
    """Fry-only huge 20d/30d winner pattern mining on full extended panel."""
    from idn_big_winner_reverse_lib import (
        BIG_WIN_PCT,
        HUGE_WIN_PCT,
        build_extended_panel,
        dedupe_winner_entries,
        label_big_winners,
        mine_patterns,
        split_meta,
        top_winner_episodes,
    )

    panel = build_extended_panel(min_date=extend_from)
    fry = panel[panel["name_type"] == "fry"].copy()
    if fry.empty:
        return {"error": "empty fry panel"}

    labeled = label_big_winners(fry)
    split = split_meta(labeled.groupby("date", as_index=False).first(), time_col="date", oos_frac=0.25)

    huge_entries = dedupe_winner_entries(labeled, flag_col="huge_win_20")
    big_entries = dedupe_winner_entries(labeled, flag_col="big_win_20")

    huge_patterns = mine_patterns(labeled, target="huge_win_20")
    big_patterns = mine_patterns(labeled, target="big_win_20")

    return {
        "extend_from": extend_from,
        "fry_panel_rows": int(len(fry)),
        "fry_symbols": int(fry["yahoo_symbol"].nunique()),
        "date_min": str(fry["date"].min().date()),
        "date_max": str(fry["date"].max().date()),
        "baseline_huge_win_rate_pct": round(float(labeled["huge_win_20"].mean() * 100), 2),
        "baseline_big_win_rate_pct": round(float(labeled["big_win_20"].mean() * 100), 2),
        "n_huge_episodes": int(len(huge_entries)),
        "n_big_episodes": int(len(big_entries)),
        "split_meta": split,
        "huge_win_threshold_pct": HUGE_WIN_PCT,
        "big_win_threshold_pct": BIG_WIN_PCT,
        "top_huge_episodes": top_winner_episodes(huge_entries, n=30),
        "huge_win_patterns": huge_patterns,
        "big_win_patterns": big_patterns,
    }


def build_pop_pattern_catalog(
    trig_patterns: list[dict[str, Any]],
    huge_report: dict[str, Any],
    anatomy_report: dict[str, Any],
    episode_summary: dict[str, Any],
) -> dict[str, Any]:
    """Unified catalog for live fry-pop scoring."""
    stable_trig = [p for p in trig_patterns if (p.get("pop_lift") or 0) >= MIN_POP_LIFT and p["n"] >= MIN_TRIGGER_N]

    huge_ranked = (huge_report.get("huge_win_patterns") or {}).get("ranked_stable") or []
    fry_huge = [p for p in huge_ranked if (p.get("oos_lift") or 0) >= 1.2][:20]

    big_ranked = (huge_report.get("big_win_patterns") or {}).get("ranked_stable") or []
    fry_big = [p for p in big_ranked if (p.get("oos_lift") or 0) >= 1.2][:15]

    scoring_patterns: list[dict[str, Any]] = []
    for p in stable_trig:
        scoring_patterns.append(
            {
                "pattern": p["pattern"],
                "weight": round(math.log(max(p["pop_lift"], 1.01)), 4),
                "pop_lift": p["pop_lift"],
                "pop_rate_pct": p["pop_rate_pct"],
                "n": p["n"],
                "source": "trigger_pop",
                "sleeve": "fry_pre_pop",
            }
        )

    for p in fry_huge:
        scoring_patterns.append(
            {
                "pattern": p["pattern"],
                "weight": round(math.log(max(p.get("oos_lift") or 1.0, 1.01)), 4),
                "oos_lift": p.get("oos_lift"),
                "oos_mean_reward_20d_pct": p.get("oos_mean_reward_20d_pct"),
                "n": p.get("n"),
                "source": "fry_huge_winner",
                "sleeve": "fry_event",
            }
        )

    anti_patterns = [
        p
        for p in trig_patterns
        if p["n"] >= MIN_TRIGGER_N and (p.get("pop_lift") or 0) < 0.85
    ]

    return {
        "version": 1,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "timeline": {
            "extend_from": huge_report.get("extend_from"),
            "date_min": episode_summary.get("date_min"),
            "date_max": episode_summary.get("date_max"),
            "panel_rows": episode_summary.get("panel_rows"),
            "panel_tiers": episode_summary.get("panel_tiers"),
        },
        "episode_stats": episode_summary.get("trigger_pop"),
        "anatomy_summary": {
            "n_triggers": anatomy_report.get("n_triggers"),
            "overall_pop_rate_pct": anatomy_report.get("overall_pop_rate_pct"),
            "by_trigger_cause": anatomy_report.get("signature_pop_rates", {}).get("by_trigger_cause"),
            "by_return_5d": anatomy_report.get("signature_pop_rates", {}).get("by_return_5d_at_trigger"),
        },
        "huge_winner_stats": {
            "n_huge_episodes": huge_report.get("n_huge_episodes"),
            "n_big_episodes": huge_report.get("n_big_episodes"),
            "baseline_huge_win_rate_pct": huge_report.get("baseline_huge_win_rate_pct"),
            "top_huge_episodes": huge_report.get("top_huge_episodes", [])[:10],
        },
        "scoring_patterns": scoring_patterns,
        "stable_trigger_patterns": stable_trig,
        "fry_huge_winner_patterns": fry_huge,
        "fry_big_winner_patterns": fry_big,
        "anti_patterns": anti_patterns[:10],
        "mechanism_summary": anatomy_report.get("phenomenon", {}).get("what_actually_triggers"),
    }


def run_full_fry_pop_research(*, extend_from: str = "2019-07-01", skip_episode: bool = False) -> dict[str, Any]:
    """End-to-end: extended episodes → anatomy → huge-winner mine → catalog."""
    from idn_fry_episode_lib import build_fry_episode_research
    from idn_fry_trigger_anatomy_lib import build_trigger_anatomy_research, enrich_triggers, _load_frames

    FRY_DIR.mkdir(parents=True, exist_ok=True)

    if skip_episode and (FRY_DIR / "fry_episodes.parquet").exists():
        episode_summary = json.loads((FRY_DIR / "summary.json").read_text(encoding="utf-8"))
    else:
        episode_summary = build_fry_episode_research(extend_from=extend_from)

    anatomy_report = build_trigger_anatomy_research()
    huge_report = mine_fry_huge_winner_patterns(extend_from=extend_from)

    ep_days, _, _, panel = _load_frames()
    trig = enrich_triggers(ep_days, panel)
    trig_patterns = mine_trigger_pop_patterns(trig)

    catalog = build_pop_pattern_catalog(trig_patterns, huge_report, anatomy_report, episode_summary)

    (HUGE_WIN_JSON).write_text(json.dumps(huge_report, indent=2, default=str) + "\n", encoding="utf-8")
    (CATALOG_JSON).write_text(json.dumps(catalog, indent=2, default=str) + "\n", encoding="utf-8")

    report = {
        "generated_at_utc": catalog["generated_at_utc"],
        "extend_from": extend_from,
        "episode_summary": episode_summary,
        "anatomy": {
            "n_triggers": anatomy_report.get("n_triggers"),
            "overall_pop_rate_pct": anatomy_report.get("overall_pop_rate_pct"),
            "top_trigger_patterns": trig_patterns[:8],
        },
        "huge_winner": {
            "n_huge_episodes": huge_report.get("n_huge_episodes"),
            "top_episodes": huge_report.get("top_huge_episodes", [])[:5],
        },
        "catalog_patterns": len(catalog.get("scoring_patterns", [])),
        "catalog_path": str(CATALOG_JSON),
    }
    (REPORT_JSON).write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    return report


def load_fry_pop_catalog() -> dict[str, Any]:
    if not CATALOG_JSON.exists():
        return {}
    try:
        return json.loads(CATALOG_JSON.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
