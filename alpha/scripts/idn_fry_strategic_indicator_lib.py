"""Strategic fry indicator research — gap audit, outcome relabeling, tier stack.

Answers: why is pop rate ~22% and what data are we missing to make this actionable?
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
TURNAROUND = REPO / "data_lake/research_panels/idn_turnaround/daily_features.parquet"
BROKER_CACHE = REPO / "data_lake/markets/idx_broker_summary/cache"
BROKER_MANIFEST = REPO / "data_lake/markets/idx_broker_summary/backfill_manifest.json"
SENTIMENT_PANEL = REPO / "data_lake/sentiment/idn_public_sentiment_panel.parquet"
STRUCTURAL_PANEL = FRY_DIR / "fry_structural_panel.parquet"
ATTENTION_PANEL = FRY_DIR / "fry_attention_panel.parquet"
OUT_DIR = FRY_DIR
OOS_START = pd.Timestamp("2024-01-01")

POP_RET_MIN = 0.08


def wilson_ci(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n <= 0:
        return (float("nan"), float("nan"))
    p = successes / n
    denom = 1 + z**2 / n
    centre = p + z**2 / (2 * n)
    margin = z * ((p * (1 - p) + z**2 / (4 * n)) / n) ** 0.5
    lo = (centre - margin) / denom
    hi = (centre + margin) / denom
    return (max(0.0, lo), min(1.0, hi))


def proportion_stats(success: pd.Series, *, label: str = "") -> dict[str, Any]:
    s = success.dropna().astype(bool)
    n = int(len(s))
    k = int(s.sum())
    if n == 0:
        return {"label": label, "n": 0, "sufficient": False}
    lo, hi = wilson_ci(k, n)
    return {
        "label": label,
        "n": n,
        "successes": k,
        "rate_pct": round(k / n * 100, 2),
        "wilson_ci_95_low_pct": round(lo * 100, 2),
        "wilson_ci_95_high_pct": round(hi * 100, 2),
        "sufficient": n >= 30,
    }


def _load_frames() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    trig = pd.read_parquet(FRY_DIR / "trigger_enriched.parquet")
    ep = pd.read_parquet(FRY_DIR / "fry_episodes.parquet")
    panel = pd.read_parquet(
        TURNAROUND,
        columns=[
            "date",
            "yahoo_symbol",
            "return_1d",
            "is_ara_day",
            "bandar_lite_label",
            "chase_score_5d",
            "quiet_acc_score_5d",
            "consecutive_ara_days",
            "name_type",
        ],
    )
    trig["date"] = pd.to_datetime(trig["date"])
    ep["trigger_date"] = pd.to_datetime(ep["trigger_date"])
    ep["pop_date"] = pd.to_datetime(ep["pop_date"], errors="coerce")
    panel["date"] = pd.to_datetime(panel["date"])
    return trig, ep, panel


def _pop_mask(sub: pd.DataFrame) -> pd.Series:
    return (sub["return_1d"] >= POP_RET_MIN) | (sub["is_ara_day"] == 1)


def extended_outcome_labels(ep: pd.DataFrame, panel: pd.DataFrame) -> pd.DataFrame:
    """Relabel episodes with pop-within-N-day outcomes (vectorized per symbol)."""
    panel = panel.sort_values(["yahoo_symbol", "date"]).copy()
    panel["is_pop_day"] = _pop_mask(panel).astype(int)

    rows: list[dict[str, Any]] = []
    for sym, g in panel.groupby("yahoo_symbol", sort=False):
        g = g.set_index("date")
        pop_dates = g.index[g["is_pop_day"] == 1]
        sym_eps = ep[ep["yahoo_symbol"] == sym]
        for _, er in sym_eps.iterrows():
            t0 = pd.Timestamp(er["trigger_date"])
            fsm_pop = pd.notna(er["pop_date"])
            rec: dict[str, Any] = {
                "episode_id": int(er["episode_id"]),
                "yahoo_symbol": sym,
                "trigger_date": t0,
                "fsm_pop_12d": bool(fsm_pop),
            }
            future = pop_dates[pop_dates > t0]
            for horizon in (15, 20, 30):
                cutoff = t0 + pd.Timedelta(days=horizon)
                hit = future[future <= cutoff]
                rec[f"pop_within_{horizon}d"] = bool(len(hit))
                if len(hit):
                    rec[f"days_to_pop_{horizon}d_cap"] = int((hit[0] - t0).days)
                else:
                    rec[f"days_to_pop_{horizon}d_cap"] = None
            if len(future):
                rec["days_to_any_pop"] = int((future[0] - t0).days)
            else:
                rec["days_to_any_pop"] = None
            rec["late_pop_13_30d"] = bool((not fsm_pop) and rec["pop_within_30d"])
            rows.append(rec)
    return pd.DataFrame(rows)


def outcome_window_sensitivity(ext: pd.DataFrame) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for col in ("fsm_pop_12d", "pop_within_15d", "pop_within_20d", "pop_within_30d", "late_pop_13_30d"):
        if col not in ext.columns:
            continue
        out[col] = proportion_stats(ext[col], label=col)
    never = ~ext["pop_within_30d"]
    out["never_pop_30d"] = proportion_stats(never, label="never_pop_30d")
    out["interpretation"] = (
        "Headline 22% uses 12-day FSM window. ~19% of all triggers pop only after day 12 "
        "(slow-cook bandar). True 30-day pop rate ~41%; ~59% never pop within 30 days."
    )
    return out


def data_gap_inventory(trig: pd.DataFrame) -> dict[str, Any]:
    gaps: list[dict[str, Any]] = []

    broker_files = list(BROKER_CACHE.glob("*.json")) if BROKER_CACHE.exists() else []
    broker_keys: set[tuple[str, str]] = set()
    broker_syms: set[str] = set()
    broker_dates: list[str] = []
    for f in broker_files:
        parts = f.stem.split("_", 1)
        if len(parts) == 2:
            sym = parts[0] + ".JK"
            d = parts[1]
            broker_keys.add((sym, d))
            broker_syms.add(sym)
            broker_dates.append(d)

    trig_keys = list(zip(trig["yahoo_symbol"], trig["date"].dt.strftime("%Y-%m-%d")))
    trig_broker = sum(1 for k in trig_keys if k in broker_keys)
    gaps.append(
        {
            "lane": "broker_summary_rapidapi",
            "status": "critical_gap",
            "coverage_on_triggers_pct": round(100 * trig_broker / max(len(trig), 1), 2),
            "n_cached_files": len(broker_files),
            "n_unique_symbols": len(broker_syms),
            "date_range": [min(broker_dates), max(broker_dates)] if broker_dates else None,
            "missing_features": [
                "broker_accdist Acc/Dist",
                "foreign_buy_share / foreign_sell_share",
                "top_buy_broker / top_sell_broker codes",
                "buyer_seller_broker_ratio",
                "number_broker_buysell",
            ],
            "why_it_matters": (
                "Bandarmology is broker-code flow. Price/volume proxies miss who is accumulating. "
                "Broker pattern_alpha lane exists but backfill targets liquid spike sessions, not fry triggers."
            ),
            "collection_action": "Backfill fry trigger sessions (see fry_trigger_broker_queue.json)",
        }
    )

    gdelt_path = FRY_DIR / "gdelt_literature_crossref.json"
    if gdelt_path.exists():
        g = json.loads(gdelt_path.read_text(encoding="utf-8"))
        meta = g.get("meta", {})
        gaps.append(
            {
                "lane": "gdelt_entity_ticker_dots",
                "status": "partial_gap",
                "coverage_on_triggers_pct": round(
                    100 * meta.get("triggers_with_entity_window", 0) / max(len(trig), 1), 2
                ),
                "entity_panel_max": meta.get("entity_panel_max"),
                "triggers_after_entity_panel": meta.get("triggers_after_entity_panel"),
                "missing_features": ["pre_entity_mentions", "entity_burst_days_pre"],
                "why_it_matters": (
                    "Entity dots sparse by design (bandar off-radar). Inverse signal: pops have fewer "
                    "pre-mentions. Post-2025-04 triggers lack entity panel."
                ),
                "collection_action": "Extend entity GDELT panel; keep inverse-absence as feature not headline",
            }
        )

    gaps.append(
        {
            "lane": "free_float_ownership",
            "status": "not_integrated",
            "coverage_on_triggers_pct": 0.0,
            "missing_features": ["free_float_pct", "controller_ownership_pct", "msic_investable_flag"],
            "why_it_matters": (
                "MSCI stock-frying narrative: low free float enables discrete ARA pops. "
                "No float data in turnaround panel — cannot separate structural fry from dead names."
            ),
            "collection_action": "IDX emiten info / KSEI / RapidAPI company profile scrape",
        }
    )
    if STRUCTURAL_PANEL.exists():
        try:
            struct = pd.read_parquet(STRUCTURAL_PANEL)
            sym_cov = trig["yahoo_symbol"].isin(struct["yahoo_symbol"]).mean() * 100
            ff_cov = (
                trig.merge(struct[["yahoo_symbol", "free_float_pct"]], on="yahoo_symbol", how="left")["free_float_pct"]
                .notna()
                .mean()
                * 100
            )
            for g in gaps:
                if g["lane"] == "free_float_ownership":
                    g["status"] = "available" if ff_cov > 50 else "partial_gap"
                    g["coverage_on_triggers_pct"] = round(float(sym_cov), 2)
                    g["free_float_field_coverage_pct"] = round(float(ff_cov), 2)
                    g["n_symbols"] = int(len(struct))
                    g["collection_action"] = "run_idn_fry_data_collection.py --lane structural"
                    break
        except Exception:
            pass

    sent_cov = 0.0
    if SENTIMENT_PANEL.exists():
        try:
            sent_cols = pd.read_parquet(SENTIMENT_PANEL, columns=None).columns.tolist()
            if "date" in sent_cols:
                sent = pd.read_parquet(SENTIMENT_PANEL, columns=["date", "yahoo_symbol"])
                sent["date"] = pd.to_datetime(sent["date"])
                m = trig.merge(sent, on=["date", "yahoo_symbol"], how="inner")
                sent_cov = 100 * len(m) / max(len(trig), 1)
            elif "yahoo_symbol" in sent_cols:
                sent_syms = set(pd.read_parquet(SENTIMENT_PANEL, columns=["yahoo_symbol"])["yahoo_symbol"])
                sent_cov = 100 * trig["yahoo_symbol"].isin(sent_syms).mean()
        except Exception:
            sent_cov = 0.0
    gaps.append(
        {
            "lane": "retail_social_attention",
            "status": "partial_gap" if sent_cov > 0 else "not_integrated",
            "coverage_on_triggers_pct": round(sent_cov, 2),
            "missing_features": ["idx_app_trending_rank", "reddit_mention_count", "stocktwits_bull_bear"],
            "why_it_matters": "Pop day is attention shock; pre-pop should be low attention. Social panel is liquid-universe biased.",
            "collection_action": "Expand idn_social_sentiment_collector to full fry universe",
        }
    )
    if ATTENTION_PANEL.exists():
        try:
            att = pd.read_parquet(ATTENTION_PANEL)
            if "yahoo_symbol" in att.columns:
                fry_att = att[att["yahoo_symbol"].isin(trig["yahoo_symbol"].unique())]
                att_cov = 100 * trig["yahoo_symbol"].isin(fry_att["yahoo_symbol"]).mean()
                trending_cov = 0.0
                if "in_trending_top50" in fry_att.columns:
                    m = trig.merge(
                        fry_att[["yahoo_symbol", "in_trending_top50", "trending_rank", "app_followers"]],
                        on="yahoo_symbol",
                        how="left",
                    )
                    trending_cov = 100 * m["trending_rank"].notna().mean()
                for g in gaps:
                    if g["lane"] == "retail_social_attention":
                        g["status"] = "partial_gap" if att_cov < 90 else "available"
                        g["coverage_on_triggers_pct"] = round(max(sent_cov, att_cov), 2)
                        g["fry_attention_symbols"] = int(len(fry_att))
                        g["trending_rank_coverage_pct"] = round(trending_cov, 2)
                        g["collection_action"] = "run_idn_fry_data_collection.py --lane attention"
                        break
        except Exception:
            pass

    gaps.append(
        {
            "lane": "price_volume_panel",
            "status": "available",
            "coverage_on_triggers_pct": 100.0,
            "features_present": [
                "return_5d",
                "vol_ratio_20d",
                "dd_60d",
                "bandar_lite_label",
                "quiet_acc_score_5d",
                "consecutive_ara_days",
                "ihsg_regime",
            ],
            "limitations": [
                "No raw volume column in daily_features.parquet (only vol_ratio)",
                "bandar_lite is proxy not broker truth",
            ],
        }
    )

    return {
        "gaps": gaps,
        "headline": "22% pop rate is not mainly missing math — it is (1) 12d label window, (2) 0% broker flow, (3) no free-float filter, (4) pooled across heterogeneous symbols.",
        "priority_order": [
            "broker_summary_rapidapi",
            "free_float_ownership",
            "outcome_window_relabel_30d",
            "symbol_walkforward_prior",
            "gdelt_entity_ticker_dots",
            "retail_social_attention",
        ],
    }


def walkforward_symbol_prior(trig: pd.DataFrame) -> pd.Series:
    """Expanding prior pop rate per symbol using only past triggers (no lookahead)."""
    trig = trig.sort_values("date").copy()
    prior_map: dict[int, float] = {}
    hist: dict[str, list[int]] = {}
    for i, row in trig.iterrows():
        sym = row["yahoo_symbol"]
        past = hist.get(sym, [])
        prior_map[int(row["episode_id"])] = float(np.mean(past)) if past else np.nan
        past.append(int(row["got_pop"]))
        hist[sym] = past
    return pd.Series(prior_map)


def false_trigger_taxonomy(trig: pd.DataFrame, ext: pd.DataFrame) -> dict[str, Any]:
    df = trig.merge(ext.drop(columns=["yahoo_symbol", "trigger_date"], errors="ignore"), on="episode_id", how="left")
    sym_stats = (
        df.groupby("yahoo_symbol")
        .agg(n=("got_pop", "count"), pops=("got_pop", "sum"))
        .assign(rate=lambda x: x["pops"] / x["n"])
    )
    dead_syms = sym_stats[(sym_stats["n"] >= 20) & (sym_stats["pops"] == 0)].index.tolist()
    hot_syms = sym_stats[(sym_stats["n"] >= 15) & (sym_stats["rate"] >= 0.45)].index.tolist()

    shallow = df["return_5d"] > -0.04
    deep = df["return_5d"] <= -0.08
    quiet_only = df.get("trigger_cause", pd.Series(dtype=str)) == "quiet_accumulation"

    buckets: list[dict[str, Any]] = []
    specs: list[tuple[str, pd.Series, str]] = [
        ("dead_name_repeated_triggers", df["yahoo_symbol"].isin(dead_syms), "got_pop"),
        ("shallow_drawdown_noise", shallow, "got_pop"),
        ("quiet_accumulation_only", quiet_only, "got_pop"),
        ("slow_cook_late_pop", df["late_pop_13_30d"].fillna(False), "pop_within_30d"),
        ("true_miss_never_30d", ~df["pop_within_30d"].fillna(True), "pop_within_30d"),
        ("deep_drawdown_quality", deep, "got_pop"),
        ("hot_symbol_prior", df["yahoo_symbol"].isin(hot_syms), "got_pop"),
    ]
    for label, mask, outcome_col in specs:
        sub = df[mask.fillna(False)]
        buckets.append(
            {
                "bucket": label,
                **proportion_stats(sub[outcome_col], label=label),
                "share_of_all_triggers_pct": round(100 * len(sub) / max(len(df), 1), 2),
            }
        )

    return {
        "buckets": buckets,
        "dead_symbols_n20plus": dead_syms,
        "hot_symbols_rate45plus": hot_syms,
        "interpretation": [
            "False triggers are heterogeneous: dead names (never pop), shallow DD noise, and slow-cook (pop after day 12).",
            "Quiet-accumulation-only triggers are low base rate (~12%) — mostly false positives.",
            "Filtering dead names + requiring deep DD removes a large share of noise without broker data.",
        ],
    }


def strategic_indicator_tiers(trig: pd.DataFrame, ext: pd.DataFrame) -> dict[str, Any]:
    df = trig.merge(ext.drop(columns=["yahoo_symbol", "trigger_date"], errors="ignore"), on="episode_id", how="left")
    df["sym_prior_wf"] = walkforward_symbol_prior(trig)
    df["era"] = np.where(df["date"] >= OOS_START, "oos", "ins")

    rules = [
        {
            "tier": "T0_baseline",
            "description": "Any fry trigger (current FSM)",
            "mask": pd.Series(True, index=df.index),
            "outcome_col": "fsm_pop_12d",
        },
        {
            "tier": "T1_deep_dd_vol",
            "description": "return_5d <= -8% AND vol_ratio >= 1.6",
            "mask": (df["return_5d"] <= -0.08) & (df["vol_ratio_20d"] >= 1.6),
            "outcome_col": "fsm_pop_12d",
        },
        {
            "tier": "T2_very_deep_dd",
            "description": "return_5d <= -12%",
            "mask": df["return_5d"] <= -0.12,
            "outcome_col": "fsm_pop_12d",
        },
        {
            "tier": "T3_hot_symbol_prior",
            "description": "T1 + walk-forward symbol prior >= 25%",
            "mask": (df["return_5d"] <= -0.08)
            & (df["vol_ratio_20d"] >= 1.6)
            & (df["sym_prior_wf"] >= 0.25),
            "outcome_col": "fsm_pop_12d",
        },
        {
            "tier": "T4_exclude_dead",
            "description": "T1 + symbol not in dead-name list (n>=20, 0 pops before trigger)",
            "mask": None,  # filled below
            "outcome_col": "fsm_pop_12d",
        },
        {
            "tier": "T1_30d_outcome",
            "description": "T1 rule but outcome = pop within 30d (label fix)",
            "mask": (df["return_5d"] <= -0.08) & (df["vol_ratio_20d"] >= 1.6),
            "outcome_col": "pop_within_30d",
        },
    ]

    # Dead-name exclusion uses walk-forward dead list
    dead_flags: list[bool] = []
    sym_hist: dict[str, list[int]] = {}
    for _, row in df.sort_values("date").iterrows():
        sym = row["yahoo_symbol"]
        past = sym_hist.get(sym, [])
        is_dead = len(past) >= 20 and sum(past) == 0
        dead_flags.append(is_dead)
        past.append(int(row["fsm_pop_12d"]))
        sym_hist[sym] = past
    df["is_dead_name_wf"] = dead_flags
    rules[4]["mask"] = (
        (df["return_5d"] <= -0.08) & (df["vol_ratio_20d"] >= 1.6) & (~df["is_dead_name_wf"])
    )

    tier_rows: list[dict[str, Any]] = []
    for spec in rules:
        mask = spec["mask"]
        sub = df[mask.fillna(False)]
        oc = spec["outcome_col"]
        overall = proportion_stats(sub[oc], label=spec["tier"])
        is_rows = sub[sub["era"] == "ins"]
        oos_rows = sub[sub["era"] == "oos"]
        tier_rows.append(
            {
                "tier": spec["tier"],
                "description": spec["description"],
                "outcome": oc,
                "overall": overall,
                "insample": proportion_stats(is_rows[oc], label="ins"),
                "oos": proportion_stats(oos_rows[oc], label="oos"),
            }
        )

    return {"tiers": tier_rows, "recommended_operational": "T3_hot_symbol_prior or T4_exclude_dead for watchlist; T1_30d_outcome for calibration"}


def fry_trigger_broker_queue(trig: pd.DataFrame, *, max_rows: int = 2500) -> list[dict[str, str]]:
    """Sessions to backfill: fry triggers prioritized by deep drawdown (not yet cached)."""
    rows: list[dict[str, str]] = []
    for _, r in trig.sort_values(["return_5d", "vol_ratio_20d"]).iterrows():
        sym = r["yahoo_symbol"]
        date = pd.Timestamp(r["date"]).strftime("%Y-%m-%d")
        path = BROKER_CACHE / f"{sym.replace('.JK', '')}_{date}.json"
        if path.exists():
            continue
        rows.append(
            {
                "yahoo_symbol": sym,
                "date": date,
                "return_5d_pct": round(float(r["return_5d"]) * 100, 2) if pd.notna(r["return_5d"]) else None,
                "vol_ratio_20d": round(float(r["vol_ratio_20d"]), 2) if pd.notna(r["vol_ratio_20d"]) else None,
                "got_pop": int(r["got_pop"]),
                "priority": "high" if pd.notna(r["return_5d"]) and r["return_5d"] <= -0.08 else "normal",
            }
        )
        if len(rows) >= max_rows:
            break
    return rows


def build_strategic_indicator_report() -> dict[str, Any]:
    trig, ep, panel = _load_frames()
    ext = extended_outcome_labels(ep, panel)
    ext.to_parquet(OUT_DIR / "extended_outcome_labels.parquet", index=False)

    gaps = data_gap_inventory(trig)
    windows = outcome_window_sensitivity(ext)
    taxonomy = false_trigger_taxonomy(trig, ext)
    tiers = strategic_indicator_tiers(trig, ext)
    queue = fry_trigger_broker_queue(trig)

    broker_report: dict[str, Any] = {}
    try:
        from idn_fry_broker_lib import build_fry_broker_report

        broker_report = build_fry_broker_report()
    except Exception as exc:
        broker_report = {"error": str(exc)}

    # Scorecard: what explains the 22% vs 78% split
    df = trig.merge(ext.drop(columns=["yahoo_symbol", "trigger_date"], errors="ignore"), on="episode_id")
    explained = {
        "late_pop_missed_by_fsm_pct": round(float(df["late_pop_13_30d"].mean()) * 100, 2),
        "never_pop_30d_pct": round(float((~df["pop_within_30d"]).mean()) * 100, 2),
        "fsm_pop_12d_pct": round(float(df["fsm_pop_12d"].mean()) * 100, 2),
        "pop_within_30d_pct": round(float(df["pop_within_30d"].mean()) * 100, 2),
    }

    report: dict[str, Any] = {
        "meta": {
            "n_triggers": int(len(trig)),
            "n_symbols": int(trig["yahoo_symbol"].nunique()),
            "date_min": str(trig["date"].min().date()),
            "date_max": str(trig["date"].max().date()),
            "oos_start": str(OOS_START.date()),
        },
        "pop_rate_reconciliation": explained,
        "outcome_window_sensitivity": windows,
        "data_gap_inventory": gaps,
        "false_trigger_taxonomy": taxonomy,
        "strategic_indicator_tiers": tiers,
        "broker_backfill_queue_size": len(queue),
        "broker_lift_analysis": broker_report.get("broker_lift_analysis"),
        "collection_roadmap": [
            {
                "step": 1,
                "action": "Relabel outcomes to 30d pop for calibration; keep 12d FSM for live episode tracking",
                "expected_lift": "Apparent pop rate 22% → 41% on same triggers (not new alpha, fixes censoring)",
            },
            {
                "step": 2,
                "action": "Backfill broker-summary on fry trigger dates (queue emitted)",
                "expected_lift": "Separate Acc vs Dist; foreign flow — hypothesized +10-15pp on T1 subset",
                "budget": "500 RapidAPI calls/mo → ~2-3 months for top 1500 deep-DD triggers",
            },
            {
                "step": 3,
                "action": "Integrate free-float / MSCI investable flag; exclude structurally dead low-float traps",
                "expected_lift": "Remove dead-name bucket (~5-8% of triggers at 0% pop)",
            },
            {
                "step": 4,
                "action": "Walk-forward symbol prior in watchlist scorer (already in tier T3)",
                "expected_lift": "T3 OOS ~45-50% vs 22% baseline on 12d label",
            },
            {
                "step": 5,
                "action": "Extend GDELT entity panel past 2025-04; use inverse mention as confirmatory",
                "expected_lift": "Modest; entity absence already associated with pop",
            },
        ],
        "strategic_indicator_definition": {
            "type": "watch_only_event_risk",
            "horizon": "0-30 calendar days to discrete ARA pop day",
            "not": "hold_5d_return_strategy",
            "core_stack": [
                "name_type == fry",
                "drawdown_vol_spike trigger",
                "return_5d <= -8% (elevated) or <= -12% (high)",
                "walkforward_symbol_prior >= 25%",
                "exclude walkforward dead names",
                "optional: broker Acc + foreign_buy_heavy when cached",
                "optional: pre_entity_mentions == 0",
            ],
            "output_tiers": {
                "low": "quiet_accumulation only or shallow DD",
                "monitor": "deep DD without hot prior",
                "elevated": "deep DD + vol + hot prior or squeeze_from_drawdown label",
            },
        },
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "strategic_indicator_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (OUT_DIR / "fry_trigger_broker_queue.json").write_text(json.dumps(queue[:500], indent=2), encoding="utf-8")
    tier_df = trig.merge(ext.drop(columns=["yahoo_symbol", "trigger_date"], errors="ignore"), on="episode_id")
    tier_df["sym_prior_wf"] = walkforward_symbol_prior(trig)
    tier_df.to_parquet(OUT_DIR / "strategic_indicator_frame.parquet", index=False)
    return report
