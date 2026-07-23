"""Unified fry research frame — merge triggers with all *available* collected lanes.

Single loader for backtest, strategic indicator, actionable, and empirics.
Uses on-disk panels only (no live API).
"""

from __future__ import annotations

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
TRIGGERS = FRY_DIR / "trigger_enriched.parquet"
TRIGGERS_STRUCTURAL = FRY_DIR / "trigger_enriched_structural.parquet"
STRUCTURAL = FRY_DIR / "fry_structural_panel.parquet"
ATTENTION = FRY_DIR / "fry_attention_panel.parquet"
TECHNICAL = FRY_DIR / "fry_technical_panel.parquet"
TECHNICAL_TRIGGERS = FRY_DIR / "fry_technical_trigger_panel.parquet"
BILATERAL = FRY_DIR / "trigger_outcome_bilateral.parquet"
EXTENDED = FRY_DIR / "extended_outcome_labels.parquet"
OOS_START = pd.Timestamp("2024-01-01")


def _structural_cols() -> list[str]:
    return [
        "yahoo_symbol",
        "free_float_pct",
        "listing_board",
        "is_watchlist_board",
        "is_acceleration_board",
        "top_holder_pct",
        "controller_ownership_pct",
        "low_free_float",
        "ultra_low_free_float",
        "structurally_fryable",
        "app_followers",
        "sector",
        "sub_sector",
        "is_trading_limit",
        "is_daytrade",
        "is_idx_liquid",
        "controller_is_foreign",
        "latest_insider_buy",
        "latest_holder_pct_change",
    ]


def _attention_cols() -> list[str]:
    return [
        "yahoo_symbol",
        "trending_rank",
        "trending_pct",
        "attention_score",
        "in_trending_top50",
    ]


def load_base_triggers() -> pd.DataFrame:
    path = TRIGGERS_STRUCTURAL if TRIGGERS_STRUCTURAL.exists() else TRIGGERS
    df = pd.read_parquet(path)
    df["date"] = pd.to_datetime(df["date"])
    return df


def attach_structural(df: pd.DataFrame) -> pd.DataFrame:
    if not STRUCTURAL.exists():
        return df
    cols = [c for c in _structural_cols() if c in pd.read_parquet(STRUCTURAL, columns=None).columns]
    struct = pd.read_parquet(STRUCTURAL, columns=cols).drop_duplicates("yahoo_symbol")
    drop = [c for c in cols if c != "yahoo_symbol" and c in df.columns]
    out = df.drop(columns=drop, errors="ignore").merge(struct, on="yahoo_symbol", how="left")
    return out


def attach_attention(df: pd.DataFrame) -> pd.DataFrame:
    if not ATTENTION.exists():
        return df
    cols = [c for c in _attention_cols() if c in pd.read_parquet(ATTENTION, columns=None).columns]
    att = pd.read_parquet(ATTENTION, columns=cols).drop_duplicates("yahoo_symbol")
    drop = [c for c in cols if c != "yahoo_symbol" and c in df.columns]
    out = df.drop(columns=drop, errors="ignore").merge(att, on="yahoo_symbol", how="left")
    out["low_app_attention"] = out["app_followers"].fillna(0) < 50_000
    out["pre_pop_not_trending"] = out["in_trending_top50"].fillna(False) == False  # noqa: E712
    return out


def _technical_cols() -> list[str]:
    return [
        "yahoo_symbol",
        "rsi",
        "rsi_oversold",
        "rsi_deep_oversold",
        "overall_trend",
        "nearest_support",
        "support_distance_pct",
        "below_vwap",
        "technical_ok",
    ]


def _technical_trigger_cols() -> list[str]:
    return [
        "episode_id",
        "rsi",
        "rsi_oversold",
        "rsi_deep_oversold",
        "overall_trend",
        "nearest_support",
        "support_distance_pct",
        "below_vwap",
        "technical_ok",
        "days_after_trigger",
        "technical_near_trigger",
    ]


def attach_technical(df: pd.DataFrame) -> pd.DataFrame:
    """Join symbol-level technical; overlay episode-level snapshots when available."""
    out = df
    if TECHNICAL_TRIGGERS.exists() and "episode_id" in out.columns:
        ttr = pd.read_parquet(TECHNICAL_TRIGGERS).drop_duplicates("episode_id")
        skip = {"episode_id", "yahoo_symbol", "trigger_date", "fetched_at_utc", "technical_reason", "symbol"}
        trig_cols = [c for c in ttr.columns if c not in skip]
        add = ttr[["episode_id"] + trig_cols].rename(columns={c: f"trig_{c}" for c in trig_cols})
        drop = [c for c in add.columns if c != "episode_id" and c in out.columns]
        out = out.drop(columns=drop, errors="ignore").merge(add, on="episode_id", how="left")
    if TECHNICAL.exists():
        cols = [c for c in _technical_cols() if c in pd.read_parquet(TECHNICAL, columns=None).columns]
        tech = pd.read_parquet(TECHNICAL, columns=cols).drop_duplicates("yahoo_symbol")
        drop = [c for c in cols if c != "yahoo_symbol" and c in out.columns]
        out = out.drop(columns=drop, errors="ignore").merge(tech, on="yahoo_symbol", how="left")
    if "trig_technical_ok" in out.columns:
        out["has_technical_trigger"] = out["trig_technical_ok"].fillna(False)
        out["rsi_at_trigger"] = out["trig_rsi"].combine_first(out.get("rsi"))
        out["rsi_oversold_at_trigger"] = out["trig_rsi_oversold"].combine_first(out.get("rsi_oversold"))
    else:
        out["has_technical_trigger"] = False
        out["rsi_at_trigger"] = out.get("rsi")
        out["rsi_oversold_at_trigger"] = out.get("rsi_oversold")
    return out


def attach_broker(df: pd.DataFrame) -> pd.DataFrame:
    try:
        from idn_fry_broker_lib import join_triggers_with_broker

        bro = join_triggers_with_broker()
        skip = set(df.columns) - {"episode_id"}
        add_cols = ["episode_id"] + [c for c in bro.columns if c not in skip and c != "episode_id"]
        return df.merge(bro[add_cols], on="episode_id", how="left")
    except Exception:
        return df


def attach_outcomes(df: pd.DataFrame) -> pd.DataFrame:
    if BILATERAL.exists():
        out = pd.read_parquet(BILATERAL)
        df = df.merge(out.drop(columns=["yahoo_symbol", "trigger_date"], errors="ignore"), on="episode_id", how="left")
    if EXTENDED.exists():
        ext = pd.read_parquet(EXTENDED)
        df = df.merge(ext.drop(columns=["yahoo_symbol", "trigger_date"], errors="ignore"), on="episode_id", how="left")
    return df


def load_fry_research_frame(*, with_broker: bool = True) -> pd.DataFrame:
    """Full fry episode table with structural, attention, outcomes, walk-forward priors."""
    df = load_base_triggers()
    df = attach_structural(df)
    df = attach_attention(df)
    df = attach_technical(df)
    df = attach_outcomes(df)
    if with_broker:
        df = attach_broker(df)

    from idn_fry_strategic_indicator_lib import walkforward_symbol_prior

    pri = walkforward_symbol_prior(load_base_triggers())
    df["sym_prior_wf"] = df["episode_id"].map(pri)

    dead_flags: list[bool] = []
    sym_hist: dict[str, list[int]] = {}
    for _, row in df.sort_values("date").iterrows():
        sym = row["yahoo_symbol"]
        past = sym_hist.get(sym, [])
        dead_flags.append(len(past) >= 20 and sum(past) == 0)
        past.append(int(row.get("got_pop", 0)))
        sym_hist[sym] = past
    df["is_dead_name_wf"] = dead_flags

    df["era"] = np.where(df["date"] >= OOS_START, "oos", "ins")
    df["year"] = df["date"].dt.year

    df["label_pop_12d"] = df["got_pop"].astype(int)
    if "pop_within_30d" in df.columns:
        df["label_pop_30d"] = df["pop_within_30d"].fillna(0).astype(int)
    else:
        df["label_pop_30d"] = df["got_pop"].astype(int)
    if "outcome_class" in df.columns:
        df["label_pop_first"] = (df["outcome_class"] == "pop_first").astype(int)
        df["label_bad_down"] = df["outcome_class"].isin(["sink_only", "grind_no_pop"]).astype(int)
    else:
        df["label_pop_first"] = df["got_pop"].astype(int)
        df["label_bad_down"] = 0

    df["composite_rank_score"] = _composite_rank_score(df)
    return df


def _composite_rank_score(df: pd.DataFrame) -> pd.Series:
    """Rank score from fields we actually have on disk (no lookahead)."""
    score = pd.Series(0.0, index=df.index)
    if "sym_prior_wf" in df.columns:
        score += df["sym_prior_wf"].fillna(0) * 40
    if "return_5d" in df.columns:
        score += (-df["return_5d"]).clip(0, 0.2) * 100
    if "vol_ratio_20d" in df.columns:
        score += np.log1p(df["vol_ratio_20d"].fillna(1)) * 5
    if "free_float_pct" in df.columns:
        score += np.where(df["free_float_pct"].fillna(50) < 5, 8, 0)
        score += np.where(df["free_float_pct"].fillna(50) < 1, 5, 0)
    if "is_watchlist_board" in df.columns:
        score += df["is_watchlist_board"].fillna(False).astype(int) * 5
    if "is_trading_limit" in df.columns:
        score += df["is_trading_limit"].fillna(False).astype(int) * 4
    if "latest_insider_buy" in df.columns:
        score += df["latest_insider_buy"].fillna(False).astype(int) * 3
    if "controller_is_foreign" in df.columns:
        score += df["controller_is_foreign"].fillna(False).astype(int) * 2
    if "rsi_oversold_at_trigger" in df.columns:
        score += df["rsi_oversold_at_trigger"].fillna(False).astype(int) * 4
    if "low_app_attention" in df.columns:
        score += df["low_app_attention"].fillna(True).astype(int) * 3
    if "has_broker" in df.columns and "number_broker_buysell" in df.columns:
        score += np.where(df["number_broker_buysell"].fillna(0) > 5, 5, 0)
    if "foreign_sell_share" in df.columns:
        score -= np.where(df["foreign_sell_share"].fillna(0) > 0.35, 5, 0)
    return score.round(2)


def structural_signal_rules() -> dict[str, Any]:
    """Extra classification rules using structural + attention fields."""
    return {
        "T5_low_free_float": lambda d: (d["return_5d"] <= -0.08)
        & (d["vol_ratio_20d"] >= 1.6)
        & (d.get("free_float_pct", pd.Series(dtype=float)) < 10),
        "T6_structurally_fryable": lambda d: (d["return_5d"] <= -0.08)
        & (d["vol_ratio_20d"] >= 1.6)
        & (d.get("structurally_fryable", pd.Series(dtype=bool)).fillna(False)),
        "T7_hot_prior_low_float": lambda d: (d["return_5d"] <= -0.08)
        & (d["vol_ratio_20d"] >= 1.6)
        & (d["sym_prior_wf"] >= 0.25)
        & (d.get("free_float_pct", pd.Series(dtype=float)) < 15),
        "T8_not_trending_pre": lambda d: (d["return_5d"] <= -0.08)
        & (d["vol_ratio_20d"] >= 1.6)
        & (d.get("pre_pop_not_trending", pd.Series(dtype=bool)).fillna(True)),
        "T9_broker_dist_t1": lambda d: (d["return_5d"] <= -0.08)
        & (d["vol_ratio_20d"] >= 1.6)
        & (d.get("has_broker", pd.Series(dtype=bool)).fillna(False))
        & (d.get("broker_accdist", pd.Series(dtype=str)) == "Dist"),
        "T10_rsi_oversold_t1": lambda d: (d["return_5d"] <= -0.08)
        & (d["vol_ratio_20d"] >= 1.6)
        & (d.get("rsi_oversold_at_trigger", pd.Series(dtype=bool)).fillna(False)),
        "T11_trading_limit_t1": lambda d: (d["return_5d"] <= -0.08)
        & (d["vol_ratio_20d"] >= 1.6)
        & (d.get("is_trading_limit", pd.Series(dtype=bool)).fillna(False)),
        "T12_insider_buy_low_float": lambda d: (d["return_5d"] <= -0.08)
        & (d["vol_ratio_20d"] >= 1.6)
        & (d.get("latest_insider_buy", pd.Series(dtype=bool)).fillna(False))
        & (d.get("free_float_pct", pd.Series(dtype=float)) < 15),
    }


def proportion_by_cut(df: pd.DataFrame, mask: pd.Series, label: str = "pop_30d") -> dict[str, Any]:
    from idn_fry_strategic_indicator_lib import proportion_stats

    col = "label_pop_30d" if label == "pop_30d" else "label_pop_12d"
    m = mask.reindex(df.index, fill_value=False)
    sub = df.loc[m]
    return proportion_stats(sub[col], label=label) if len(sub) else {"n": 0, "sufficient": False}


def build_available_data_report() -> dict[str, Any]:
    """Empirics on what we can test *now* with collected lanes."""
    df = load_fry_research_frame()
    oos = df[df["era"] == "oos"]

    structural_cuts: list[dict[str, Any]] = []
    if "free_float_pct" in df.columns and df["free_float_pct"].notna().any():
        for name, mask in [
            ("ff_lt_5pct", df["free_float_pct"] < 5),
            ("ff_5_15pct", (df["free_float_pct"] >= 5) & (df["free_float_pct"] < 15)),
            ("ff_gte_15pct", df["free_float_pct"] >= 15),
            ("watchlist_board", df["is_watchlist_board"].fillna(False)),
            ("ultra_low_ff", df["ultra_low_free_float"].fillna(False)),
            ("controller_gt_90", df["top_holder_pct"].fillna(0) > 90),
        ]:
            structural_cuts.append(
                {
                    "cut": name,
                    "all": proportion_by_cut(df, mask),
                    "oos": proportion_by_cut(oos, mask),
                }
            )

    attention_cuts: list[dict[str, Any]] = []
    if "app_followers" in df.columns:
        for name, mask in [
            ("followers_lt_50k", df["app_followers"].fillna(0) < 50_000),
            ("followers_gte_500k", df["app_followers"].fillna(0) >= 500_000),
            ("not_in_trending_top50", ~df["in_trending_top50"].fillna(False)),
        ]:
            attention_cuts.append({"cut": name, "oos": proportion_by_cut(oos, mask)})

    broker_cov = float(df["has_broker"].mean()) if "has_broker" in df.columns else 0.0
    tech_cov = float(df["has_technical_trigger"].mean()) if "has_technical_trigger" in df.columns else 0.0
    sym_tech_cov = float(df["technical_ok"].mean()) if "technical_ok" in df.columns else 0.0
    broker_cuts: list[dict[str, Any]] = []
    if broker_cov > 0.01:
        bro = df[df["has_broker"].fillna(False)]
        for name, mask in [
            ("broker_dist", bro["broker_accdist"] == "Dist"),
            ("broker_more_buyers", bro["number_broker_buysell"] > 5),
            ("broker_foreign_sell", bro["foreign_sell_share"].fillna(0) > 0.35),
        ]:
            broker_cuts.append({"cut": name, "subset": proportion_by_cut(bro, mask)})

    technical_cuts: list[dict[str, Any]] = []
    if sym_tech_cov > 0.01:
        for name, mask in [
            ("rsi_oversold", df["rsi_oversold_at_trigger"].fillna(False)),
            ("rsi_deep_oversold", df.get("rsi_deep_oversold", pd.Series(False, index=df.index)).fillna(False)),
            ("below_vwap", df.get("below_vwap", pd.Series(False, index=df.index)).fillna(False)),
            ("trading_limit", df.get("is_trading_limit", pd.Series(False, index=df.index)).fillna(False)),
            ("insider_buy", df.get("latest_insider_buy", pd.Series(False, index=df.index)).fillna(False)),
        ]:
            technical_cuts.append({"cut": name, "oos": proportion_by_cut(oos, mask)})
    if tech_cov > 0.005:
        near_mask = df.get("has_technical_trigger", pd.Series(False, index=df.index)) & df.get(
            "trig_technical_near_trigger", pd.Series(False, index=df.index)
        )
        if near_mask.any():
            technical_cuts.append({"cut": "technical_near_trigger_7d", "oos": proportion_by_cut(oos, near_mask.reindex(oos.index, fill_value=False))})

    rank_deciles: list[dict[str, Any]] = []
    if "composite_rank_score" in oos.columns and len(oos) > 100:
        oos = oos.copy()
        oos["rank_decile"] = pd.qcut(oos["composite_rank_score"], 5, labels=False, duplicates="drop")
        for dec in sorted(oos["rank_decile"].dropna().unique()):
            sub = oos[oos["rank_decile"] == dec]
            rank_deciles.append(
                {
                    "decile": int(dec),
                    "n": len(sub),
                    "pop_30d_pct": round(float(sub["label_pop_30d"].mean()) * 100, 2),
                    "score_min": float(sub["composite_rank_score"].min()),
                    "score_max": float(sub["composite_rank_score"].max()),
                }
            )

    live_watch: list[dict[str, Any]] = []
    try:
        from idn_fry_actionable_lib import build_watchlist

        for row in build_watchlist()[:8]:
            live_watch.append(
                {
                    k: row.get(k)
                    for k in (
                        "yahoo_symbol",
                        "tier",
                        "action_score",
                        "free_float_pct",
                        "symbol_pop_prior_wf",
                        "structural_flags",
                        "sink_risk_tier",
                        "broker_data_available",
                    )
                }
            )
    except Exception:
        pass

    report: dict[str, Any] = {
        "meta": {
            "n_triggers": int(len(df)),
            "n_oos": int(len(oos)),
            "n_symbols": int(df["yahoo_symbol"].nunique()),
            "structural_coverage_pct": round(100 * df["free_float_pct"].notna().mean(), 2)
            if "free_float_pct" in df.columns
            else 0,
            "broker_coverage_pct": round(100 * broker_cov, 2),
            "technical_symbol_coverage_pct": round(100 * sym_tech_cov, 2),
            "technical_trigger_coverage_pct": round(100 * tech_cov, 2),
            "generated_from": "on_disk_panels_only",
        },
        "structural_cuts": structural_cuts,
        "attention_cuts": attention_cuts,
        "broker_cuts": broker_cuts,
        "technical_cuts": technical_cuts,
        "rank_deciles_oos": rank_deciles,
        "live_watchlist_top": live_watch,
        "playbook_with_available_data": [
            "Gate: T1 (r5<=-8%, vol>=1.6) — baseline ~42% pop-30d OOS.",
            "Structural filter: free_float < 10% or watchlist board — higher fryability per theory; verify in structural_cuts.",
            "Attention: prefer NOT in trending top-50 pre-trigger (pop is attention shock, not chase).",
            "Rank: composite_rank_score top quintile — use rank_deciles_oos for calibrated pick rate.",
            "Technical (live API): RSI oversold + near support on watchlist; episode snapshots only for recent triggers.",
            "Index flags: TRADINGLIMIT board aligns with watchlist-board fryability.",
            "Insider: recent controller BUY + low float is a setup flag (not sink).",
            "Broker (where cached): Dist on trigger is OK for fry; foreign_sell heavy → sink risk.",
            "Execution: watchlist only until ARA pop day — do not buy trigger day.",
        ],
    }
    out = FRY_DIR / "fry_available_data_report.json"
    out.write_text(__import__("json").dumps(report, indent=2), encoding="utf-8")
    return report
