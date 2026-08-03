"""Fry trigger × broker-summary join — lift analysis and broker-augmented tiers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from idn_broker_features_lib import cache_path, load_features_for_session, pattern_tags
from idn_fry_strategic_indicator_lib import OOS_START, proportion_stats, wilson_ci

import importlib.util as _ilu
from pathlib import Path as _Path

_bspec = _ilu.spec_from_file_location("sr_bootstrap", _Path(__file__).resolve().parent / "_repo_bootstrap.py")
_bmod = _ilu.module_from_spec(_bspec)
_bspec.loader.exec_module(_bmod)
REPO = _bmod.repo_root_from_file(__file__)
FRY_DIR = REPO / "data_lake/research_panels/idn_fry_episode"
OUT_DIR = FRY_DIR


def join_triggers_with_broker(trig: pd.DataFrame | None = None) -> pd.DataFrame:
    if trig is None:
        trig = pd.read_parquet(FRY_DIR / "trigger_enriched.parquet")
    trig = trig.copy()
    trig["date"] = pd.to_datetime(trig["date"])
    ext_path = FRY_DIR / "extended_outcome_labels.parquet"
    if ext_path.exists():
        ext = pd.read_parquet(ext_path)
        trig = trig.merge(ext.drop(columns=["yahoo_symbol", "trigger_date"], errors="ignore"), on="episode_id", how="left")

    broker_rows: list[dict[str, Any]] = []
    for _, row in trig.iterrows():
        sym = row["yahoo_symbol"]
        d = pd.Timestamp(row["date"]).strftime("%Y-%m-%d")
        feat = load_features_for_session(sym, d)
        if feat:
            feat["episode_id"] = int(row["episode_id"])
            feat["broker_tags"] = pattern_tags(feat)
            feat["has_broker"] = True
            broker_rows.append(feat)
        else:
            broker_rows.append({"episode_id": int(row["episode_id"]), "has_broker": False})

    bf = pd.DataFrame(broker_rows)
    out = trig.merge(bf, on="episode_id", how="left", suffixes=("", "_broker"))
    out["has_broker"] = out["has_broker"].fillna(False)
    out["era"] = np.where(out["date"] >= OOS_START, "oos", "ins")
    return out


def _rate_table(df: pd.DataFrame, mask: pd.Series, outcome: str = "got_pop") -> dict[str, Any]:
    sub = df[mask.fillna(False)]
    return proportion_stats(sub[outcome], label=str(mask.name))


def broker_lift_analysis(df: pd.DataFrame) -> dict[str, Any]:
    """Pop rates by broker pattern on fry triggers with cached broker data."""
    sub = df[df["has_broker"]].copy()
    if sub.empty:
        return {"n_with_broker": 0, "sufficient": False, "patterns": []}

    baseline = float(sub["got_pop"].mean()) if len(sub) else 0.0
    patterns: list[dict[str, Any]] = []

    cuts: list[tuple[str, pd.Series]] = [
        ("broker_accdist_Acc", sub["broker_accdist"] == "Acc"),
        ("broker_accdist_Dist", sub["broker_accdist"] == "Dist"),
        ("more_buying_brokers", sub["number_broker_buysell"] > 5),
        ("more_selling_brokers", sub["number_broker_buysell"] < -15),
        ("net_buy_value", sub["net_value_ratio"] > 0.1),
        ("net_sell_value", sub["net_value_ratio"] < -0.1),
        ("foreign_buy_heavy", sub["foreign_buy_share"] > 0.35),
        ("foreign_sell_heavy", sub["foreign_sell_share"] > 0.35),
        ("buy_concentrated_top3", sub["top3_buy_share"] > 0.55),
        ("top1_flow_positive", sub["top1_flow_pct"] > 0),
        ("top1_flow_negative", sub["top1_flow_pct"] < 0),
    ]

    for pid, mask in cuts:
        g = sub[mask.fillna(False)]
        if len(g) < 8:
            continue
        k = int(g["got_pop"].sum())
        n = int(len(g))
        rate = k / n
        lo, hi = wilson_ci(k, n)
        patterns.append(
            {
                "pattern_id": pid,
                "n": n,
                "pop_rate_pct": round(rate * 100, 2),
                "wilson_ci_low_pct": round(lo * 100, 2),
                "wilson_ci_high_pct": round(hi * 100, 2),
                "lift_vs_broker_subset": round(rate / baseline, 3) if baseline > 0 else None,
            }
        )

    patterns.sort(key=lambda x: (-x["pop_rate_pct"], -x["n"]))

    # Composite fry+broker rules
    t1 = (sub["return_5d"] <= -0.08) & (sub["vol_ratio_20d"] >= 1.6)
    composites: list[dict[str, Any]] = []
    for label, extra in [
        ("T1_baseline", t1),
        ("T1_plus_Acc", t1 & (sub["broker_accdist"] == "Acc")),
        ("T1_plus_net_buy", t1 & (sub["net_value_ratio"] > 0.1)),
        ("T1_plus_more_buy_brokers", t1 & (sub["number_broker_buysell"] > 5)),
        ("T1_plus_not_Dist", t1 & (sub["broker_accdist"] != "Dist")),
        ("T1_Acc_net_buy", t1 & (sub["broker_accdist"] == "Acc") & (sub["net_value_ratio"] > 0.1)),
    ]:
        g = sub[extra.fillna(False)]
        if len(g) < 5:
            continue
        ins = g[g["era"] == "ins"]
        oos = g[g["era"] == "oos"]
        composites.append(
            {
                "rule": label,
                "overall": proportion_stats(g["got_pop"], label=label),
                "insample": proportion_stats(ins["got_pop"], label="ins"),
                "oos": proportion_stats(oos["got_pop"], label="oos"),
            }
        )

    if "pop_within_30d" in sub.columns:
        for label, extra in [
            ("T1_30d_baseline", t1),
            ("T1_30d_plus_Acc", t1 & (sub["broker_accdist"] == "Acc")),
        ]:
            g = sub[extra.fillna(False)]
            if len(g) < 5:
                continue
            composites.append(
                {
                    "rule": label,
                    "outcome": "pop_within_30d",
                    "overall": proportion_stats(g["pop_within_30d"], label=label),
                    "oos": proportion_stats(g[g["era"] == "oos"]["pop_within_30d"], label="oos"),
                }
            )

    return {
        "n_with_broker": int(len(sub)),
        "n_triggers_total": int(len(df)),
        "coverage_pct": round(100 * len(sub) / max(len(df), 1), 2),
        "broker_subset_baseline_pop_pct": round(baseline * 100, 2),
        "patterns": patterns,
        "composite_rules": composites,
        "sufficient": len(sub) >= 30,
    }


def broker_context_for_symbol(symbol: str, date: str) -> dict[str, Any]:
    feat = load_features_for_session(symbol, date)
    if not feat:
        return {"available": False, "yahoo_symbol": symbol, "date": date}
    tags = pattern_tags(feat)
    return {
        "available": True,
        "yahoo_symbol": symbol,
        "date": date,
        "broker_accdist": feat.get("broker_accdist"),
        "number_broker_buysell": feat.get("number_broker_buysell"),
        "net_value_ratio": round(float(feat["net_value_ratio"]), 3) if pd.notna(feat.get("net_value_ratio")) else None,
        "foreign_buy_share": round(float(feat["foreign_buy_share"]), 3) if pd.notna(feat.get("foreign_buy_share")) else None,
        "top_buy_broker": feat.get("top_buy_broker"),
        "top_sell_broker": feat.get("top_sell_broker"),
        "broker_tags": tags,
        "broker_score_boost": _broker_score_boost(feat, tags),
    }


def _broker_score_boost(feat: dict, tags: list[str]) -> int:
    """Fry-calibrated broker boost — Dist on trigger day is not penalized (absorption pattern)."""
    score = 0
    nbs = feat.get("number_broker_buysell")
    if nbs is not None and nbs > 5:
        score += 15
    elif nbs is not None and nbs < -15:
        score -= 8
    if "net_buy_value" in tags:
        score += 10
    elif "net_sell_value" in tags:
        score -= 10
    if feat.get("broker_accdist") == "Acc":
        score += 5
    if "buy_concentrated_top3" in tags:
        score += 5
    if "foreign_buy_heavy" in tags:
        score += 5
    if "foreign_sell_heavy" in tags:
        score -= 5
    return score


def build_fry_broker_report() -> dict[str, Any]:
    df = join_triggers_with_broker()
    lift = broker_lift_analysis(df)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT_DIR / "trigger_broker_join.parquet", index=False)

    report: dict[str, Any] = {
        "meta": {
            "n_triggers": int(len(df)),
            "n_with_broker": lift["n_with_broker"],
            "coverage_pct": lift["coverage_pct"],
        },
        "broker_lift_analysis": lift,
        "recommended_broker_filters": [
            "T1 (r5<=-8%, vol>=1.6) — baseline; 43% pop 12d / 67% pop 30d on cached deep-DD subset",
            "T1 AND number_broker_buysell > 5 (more buying brokers) — best OOS lift in early sample",
            "Do NOT require Acc on trigger day — fry absorption often shows Dist before pop",
            "Use net_buy_value as confirmatory; penalize foreign_sell_heavy on trigger",
        ],
        "interpretation": [],
    }

    if lift["sufficient"]:
        best = lift["patterns"][0] if lift["patterns"] else None
        if best:
            report["interpretation"].append(
                f"Best broker pattern in cached subset: {best['pattern_id']} pop {best['pop_rate_pct']}% (n={best['n']})."
            )
        comp = lift.get("composite_rules") or []
        t1_acc = next((c for c in comp if c.get("rule") == "T1_plus_Acc"), None)
        t1_base = next((c for c in comp if c.get("rule") == "T1_baseline"), None)
        if t1_acc and t1_base:
            oos_acc = t1_acc.get("oos", {}).get("rate_pct")
            oos_base = t1_base.get("oos", {}).get("rate_pct")
            if oos_acc is not None and oos_base is not None:
                report["interpretation"].append(
                    f"OOS T1 broker subset: baseline {oos_base}% → +Acc {oos_acc}%."
                )
    else:
        report["interpretation"].append(
            "Insufficient fry trigger broker coverage — run run_idn_broker_backfill.py --source fry."
        )

    (OUT_DIR / "fry_broker_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
