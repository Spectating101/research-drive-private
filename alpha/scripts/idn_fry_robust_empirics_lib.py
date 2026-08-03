"""Robust empirical analysis for fry trigger → pop phenomenon.

Statistical layers:
  - Wilson + cluster-bootstrap CIs on pop rates
  - Indicator threshold scan with BH-FDR
  - Time-split OOS validation (pre-registered rule families)
  - Logistic model with symbol-grouped CV
  - Placebo baselines (matched fry non-triggers, standard-name vol/dd)
  - Era / regime stability tables
  - Survival curves (days-to-pop) by covariate bucket
  - Path-outcome inference (pop-day return, fwd_max from trigger)
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
TURNAROUND_PANEL = REPO / "data_lake/research_panels/idn_turnaround/daily_features.parquet"
OUT_DIR = FRY_DIR

OOS_START = pd.Timestamp("2024-01-01")
PRE_WINDOW_DAYS = 10


def wilson_ci(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n <= 0:
        return (float("nan"), float("nan"))
    p = successes / n
    denom = 1 + z**2 / n
    centre = p + z**2 / (2 * n)
    margin = z * math.sqrt((p * (1 - p) + z**2 / (4 * n)) / n)
    lo = (centre - margin) / denom
    hi = (centre + margin) / denom
    return (max(0.0, lo), min(1.0, hi))


def proportion_inference(success: pd.Series, *, label: str = "") -> dict[str, Any]:
    s = success.dropna().astype(int)
    n = int(len(s))
    k = int(s.sum())
    if n == 0:
        return {"label": label, "n": 0, "sufficient": False}
    rate = k / n
    lo, hi = wilson_ci(k, n)
    # binomial test vs 50% not right - vs baseline 22.4% overall
    try:
        from scipy import stats

        p_vs_half = float(stats.binomtest(k, n, 0.5, alternative="two-sided").pvalue)
    except Exception:
        p_vs_half = None
    return {
        "label": label,
        "n": n,
        "successes": k,
        "rate_pct": round(rate * 100, 2),
        "wilson_ci_95_low_pct": round(lo * 100, 2),
        "wilson_ci_95_high_pct": round(hi * 100, 2),
        "sufficient": n >= 30,
    }


def cluster_bootstrap_rate(
    df: pd.DataFrame,
    success_col: str,
    cluster_col: str = "yahoo_symbol",
    *,
    n_boot: int = 2000,
    seed: int = 42,
) -> dict[str, Any]:
    """Bootstrap pop rate resampling symbols (episodes clustered by name)."""
    if df.empty or cluster_col not in df.columns:
        prop = proportion_inference(df[success_col]) if not df.empty else {"sufficient": False}
        return {"n": int(len(df)), "sufficient": prop.get("sufficient", False), "rate_pct": prop.get("rate_pct")}
    clusters = df.groupby(cluster_col, sort=False)
    cluster_ids = list(clusters.groups.keys())
    cluster_rates = []
    cluster_weights = []
    for cid, g in clusters:
        cluster_rates.append(float(g[success_col].mean()))
        cluster_weights.append(len(g))
    cluster_rates = np.array(cluster_rates)
    cluster_weights = np.array(cluster_weights)
    overall = float(df[success_col].mean())
    rng = np.random.default_rng(seed)
    boots: list[float] = []
    for _ in range(n_boot):
        idx = rng.choice(len(cluster_ids), size=len(cluster_ids), replace=True)
        w = cluster_weights[idx]
        r = cluster_rates[idx]
        boots.append(float(np.average(r, weights=w)))
    lo, hi = np.percentile(boots, [2.5, 97.5])
    return {
        "n": int(len(df)),
        "n_clusters": len(cluster_ids),
        "rate_pct": round(overall * 100, 2),
        "cluster_boot_ci_95_low_pct": round(float(lo) * 100, 2),
        "cluster_boot_ci_95_high_pct": round(float(hi) * 100, 2),
        "sufficient": len(df) >= 30,
    }


def _binom_vs_baseline(k: int, n: int, p0: float) -> float:
    try:
        from scipy import stats

        return float(stats.binomtest(k, n, p0, alternative="greater").pvalue)
    except Exception:
        return 1.0


def load_research_frame() -> pd.DataFrame:
    trig = pd.read_parquet(FRY_DIR / "trigger_enriched.parquet")
    pre = pd.read_parquet(FRY_DIR / "trigger_pre_window.parquet")
    ep = pd.read_parquet(FRY_DIR / "fry_episodes.parquet")
    trig["date"] = pd.to_datetime(trig["date"])
    ep["trigger_date"] = pd.to_datetime(ep["trigger_date"])
    df = trig.merge(pre.drop(columns=["got_pop", "trigger_cause", "yahoo_symbol"], errors="ignore"), on="episode_id", how="left")
    df = df.merge(
        ep[
            [
                "episode_id",
                "pop_return_1d_pct",
                "trigger_to_pop_days",
                "max_fwd_5d_from_trigger_pct",
                "days_to_10pct_from_trigger",
                "hit_10pct_within_5d",
            ]
        ],
        on="episode_id",
        how="left",
    )
    df["era"] = np.where(df["date"] >= OOS_START, "oos_holdout", "insample")
    df["year"] = df["date"].dt.year
    df["quarter"] = df["date"].dt.to_period("Q").astype(str)
    return df


def indicator_definitions() -> list[dict[str, Any]]:
    """Pre-registered indicator cuts for pop prediction at trigger."""
    return [
        {"id": "return_5d_lte_neg12", "col": "return_5d", "op": "le", "thr": -0.12},
        {"id": "return_5d_lte_neg8", "col": "return_5d", "op": "le", "thr": -0.08},
        {"id": "return_5d_lte_neg4", "col": "return_5d", "op": "le", "thr": -0.04},
        {"id": "vol_ratio_gte_2", "col": "vol_ratio_20d", "op": "ge", "thr": 2.0},
        {"id": "vol_ratio_gte_3", "col": "vol_ratio_20d", "op": "ge", "thr": 3.0},
        {"id": "cs_rank_lte_10pct", "col": "cs_move_pct_rank", "op": "le", "thr": 0.10},
        {"id": "cs_rank_lte_25pct", "col": "cs_move_pct_rank", "op": "le", "thr": 0.25},
        {"id": "rsi_lte_35", "col": "rsi14", "op": "le", "thr": 35},
        {"id": "rsi_lte_40", "col": "rsi14", "op": "le", "thr": 40},
        {"id": "dd_60d_lte_neg20", "col": "dd_60d", "op": "le", "thr": -0.20},
        {"id": "dd_60d_lte_neg30", "col": "dd_60d", "op": "le", "thr": -0.30},
        {"id": "pos_52w_lte_25", "col": "pos_52w_range", "op": "le", "thr": 0.25},
        {"id": "pre10_cum_lte_neg5", "col": "pre10_cum_move_pct", "op": "le", "thr": -5.0},
        {"id": "pre5_down_days_gte_3", "col": "pre5_down_days", "op": "ge", "thr": 3},
        {"id": "quiet_acc_lte_1", "col": "quiet_acc_score_5d", "op": "le", "thr": 1},
        {"id": "trigger_drawdown_vol", "col": "trigger_cause", "op": "eq", "thr": "drawdown_vol_spike"},
        {"id": "trigger_quiet_only", "col": "trigger_cause", "op": "eq", "thr": "quiet_accumulation"},
        {"id": "ihsg_washout", "col": "ihsg_regime", "op": "eq", "thr": "washout"},
        {"id": "near_support_60d", "col": "near_support_60d", "op": "ge", "thr": 1},
    ]


def _apply_cut(df: pd.DataFrame, spec: dict[str, Any]) -> pd.Series:
    col, op, thr = spec["col"], spec["op"], spec["thr"]
    if col not in df.columns:
        return pd.Series(False, index=df.index)
    s = df[col]
    if op == "le":
        return s <= thr
    if op == "ge":
        return s >= thr
    if op == "eq":
        return s == thr
    raise ValueError(op)


def indicator_scan(df: pd.DataFrame, baseline_rate: float) -> list[dict[str, Any]]:
    from idn_signal_stats import benjamini_hochberg

    rows: list[dict[str, Any]] = []
    for spec in indicator_definitions():
        mask = _apply_cut(df, spec)
        sub = df[mask.fillna(False)]
        if len(sub) < 20:
            continue
        k = int(sub["got_pop"].sum())
        n = int(len(sub))
        rate = k / n
        lo, hi = wilson_ci(k, n)
        p_lift = _binom_vs_baseline(k, n, baseline_rate)
        rows.append(
            {
                "indicator_id": spec["id"],
                "n": n,
                "pop_rate_pct": round(rate * 100, 2),
                "wilson_ci_low_pct": round(lo * 100, 2),
                "wilson_ci_high_pct": round(hi * 100, 2),
                "lift_vs_baseline": round(rate / baseline_rate, 3) if baseline_rate > 0 else None,
                "p_value_vs_baseline": round(p_lift, 4),
                "cluster_boot": cluster_bootstrap_rate(sub, "got_pop"),
            }
        )
    keys = [r["indicator_id"] for r in rows]
    ps = [r["p_value_vs_baseline"] for r in rows]
    fdr = benjamini_hochberg(keys, ps)
    for r in rows:
        r["fdr_q_value"] = fdr.get(r["indicator_id"])
        r["fdr_significant_5pct"] = bool(r["fdr_q_value"] is not None and r["fdr_q_value"] < 0.05)
    rows.sort(key=lambda x: (-x["pop_rate_pct"], -x["n"]))
    return rows


def composite_rules() -> list[dict[str, Any]]:
    """Pre-registered multi-indicator rules."""
    return [
        {
            "rule_id": "core_drawdown_vol",
            "desc": "drawdown_vol_spike trigger cause",
            "mask": lambda d: d["trigger_cause"] == "drawdown_vol_spike",
        },
        {
            "rule_id": "deep_dd_vol",
            "desc": "drawdown_vol_spike AND return_5d <= -8%",
            "mask": lambda d: (d["trigger_cause"] == "drawdown_vol_spike") & (d["return_5d"] <= -0.08),
        },
        {
            "rule_id": "deep_dd_quiet_cs",
            "desc": "return_5d <= -8% AND cs_rank <= 25% AND vol >= 2",
            "mask": lambda d: (d["return_5d"] <= -0.08) & (d["cs_move_pct_rank"] <= 0.25) & (d["vol_ratio_20d"] >= 2),
        },
        {
            "rule_id": "squeeze_washout",
            "desc": "bandar squeeze_from_drawdown AND ihsg washout",
            "mask": lambda d: (d["bandar_lite_label"] == "squeeze_from_drawdown") & (d["ihsg_regime"] == "washout"),
        },
        {
            "rule_id": "pre_grind_deep",
            "desc": "pre10_cum <= -5% AND return_5d <= -8%",
            "mask": lambda d: (d["pre10_cum_move_pct"] <= -5) & (d["return_5d"] <= -0.08),
        },
    ]


def rule_validation(df: pd.DataFrame, baseline_rate: float) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for rule in composite_rules():
        for era in ("insample", "oos_holdout", "all"):
            sub = df if era == "all" else df[df["era"] == era]
            mask = rule["mask"](sub)
            hit = sub[mask.fillna(False)]
            if len(hit) < 10:
                continue
            prop = proportion_inference(hit["got_pop"], label=rule["rule_id"])
            cb = cluster_bootstrap_rate(hit, "got_pop")
            k, n = int(hit["got_pop"].sum()), int(len(hit))
            rows.append(
                {
                    "rule_id": rule["rule_id"],
                    "description": rule["desc"],
                    "era": era,
                    **prop,
                    "lift_vs_baseline": round((prop["rate_pct"] / 100) / baseline_rate, 3) if baseline_rate else None,
                    "p_value_vs_baseline": round(_binom_vs_baseline(k, n, baseline_rate), 4),
                    "cluster_bootstrap": cb,
                    "oos_beats_insample": None,
                }
            )
    # flag OOS degradation
    by_rule: dict[str, dict[str, dict]] = {}
    for r in rows:
        by_rule.setdefault(r["rule_id"], {})[r["era"]] = r
    for rid, eras in by_rule.items():
        if "insample" in eras and "oos_holdout" in eras:
            ins = eras["insample"]["rate_pct"]
            oos = eras["oos_holdout"]["rate_pct"]
            eras["oos_holdout"]["oos_beats_insample"] = oos >= ins * 0.85
    return rows


def logistic_pop_model(df: pd.DataFrame) -> dict[str, Any]:
    """Grouped time split logistic: train pre-OOS, test OOS."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score, brier_score_loss
    from sklearn.preprocessing import StandardScaler

    feat_cols = [
        "return_5d",
        "vol_ratio_20d",
        "cs_move_pct_rank",
        "rsi14",
        "pos_52w_range",
        "dd_60d",
        "quiet_acc_score_5d",
        "pre10_cum_move_pct",
        "pre5_down_days",
        "pre5_vol_ratio_med",
    ]
    work = df.dropna(subset=feat_cols + ["got_pop"]).copy()
    if len(work) < 200:
        return {"sufficient": False}

    train = work[work["era"] == "insample"]
    test = work[work["era"] == "oos_holdout"]
    if len(train) < 100 or len(test) < 50:
        return {"sufficient": False, "reason": "thin split"}

    X_tr = train[feat_cols].to_numpy()
    y_tr = train["got_pop"].to_numpy()
    X_te = test[feat_cols].to_numpy()
    y_te = test["got_pop"].to_numpy()

    scaler = StandardScaler()
    X_tr_s = scaler.fit_transform(X_tr)
    X_te_s = scaler.transform(X_te)

    model = LogisticRegression(max_iter=500, class_weight="balanced", random_state=42)
    model.fit(X_tr_s, y_tr)
    proba_te = model.predict_proba(X_te_s)[:, 1]

    coefs = {feat_cols[i]: round(float(c), 4) for i, c in enumerate(model.coef_[0])}
    try:
        auc = round(float(roc_auc_score(y_te, proba_te)), 3)
    except ValueError:
        auc = None
    brier = round(float(brier_score_loss(y_te, proba_te)), 4)

    # top quartile predicted vs bottom on OOS
    te = test.copy()
    te["p_pop"] = proba_te
    q75 = te["p_pop"].quantile(0.75)
    q25 = te["p_pop"].quantile(0.25)
    top = te[te["p_pop"] >= q75]
    bot = te[te["p_pop"] <= q25]

    return {
        "sufficient": True,
        "train_n": int(len(train)),
        "test_n": int(len(test)),
        "features": feat_cols,
        "coefficients_std_scaled": coefs,
        "intercept": round(float(model.intercept_[0]), 4),
        "oos_auc": auc,
        "oos_brier": brier,
        "oos_top_quartile": proportion_inference(top["got_pop"]),
        "oos_bottom_quartile": proportion_inference(bot["got_pop"]),
        "interpretation": "Positive coef → higher pop probability. AUC on OOS tests whether indicators jointly beat baseline ranking.",
    }


def era_stability(df: pd.DataFrame) -> dict[str, Any]:
    yearly = []
    for yr, g in df.groupby("year"):
        yearly.append({**proportion_inference(g["got_pop"], label=str(yr)), "year": int(yr)})
    quarterly = []
    for q, g in df.groupby("quarter"):
        if len(g) < 20:
            continue
        quarterly.append({**proportion_inference(g["got_pop"], label=str(q)), "quarter": str(q)})
    rates = [y["rate_pct"] for y in yearly if y.get("sufficient")]
    return {
        "yearly": yearly,
        "quarterly": quarterly,
        "yearly_rate_std": round(float(np.std(rates)), 2) if len(rates) > 1 else None,
        "yearly_rate_range": [min(rates), max(rates)] if rates else None,
    }


def survival_by_bucket(df: pd.DataFrame) -> dict[str, Any]:
    """Cumulative pop rate by days since trigger."""

    def _curve(sub: pd.DataFrame, max_day: int = 15) -> list[dict[str, Any]]:
        n0 = len(sub)
        if n0 < 30 or "trigger_to_pop_days" not in sub.columns:
            return []
        lag = sub["trigger_to_pop_days"]
        curve = []
        for d in range(1, max_day + 1):
            hit = lag.notna() & (lag <= d)
            curve.append({"day": d, "cum_pop_rate_pct": round(int(hit.sum()) / n0 * 100, 2), "n_at_risk": n0})
        return curve

    return {
        "all_triggers": _curve(df),
        "deep_dd_return5d_lte_8": _curve(df[df["return_5d"] <= -0.08]),
        "drawdown_vol_spike": _curve(df[df["trigger_cause"] == "drawdown_vol_spike"]),
        "quiet_accumulation": _curve(df[df["trigger_cause"] == "quiet_accumulation"]),
    }


def path_outcomes(df: pd.DataFrame) -> dict[str, Any]:
    from idn_signal_stats import mean_return_inference

    out: dict[str, Any] = {}
    pop = df[df["got_pop"] == 1]
    if not pop.empty and pop["pop_return_1d_pct"].notna().any():
        out["pop_day_return_pct"] = mean_return_inference(pop["pop_return_1d_pct"])
    if pop["max_fwd_5d_from_trigger_pct"].notna().any():
        out["max_fwd_5d_from_trigger_on_poppers"] = mean_return_inference(pop["max_fwd_5d_from_trigger_pct"])
    all_fwd = df["max_fwd_5d_from_trigger_pct"].dropna()
    if len(all_fwd) >= 30:
        out["max_fwd_5d_all_triggers"] = mean_return_inference(all_fwd)
    hit = df["hit_10pct_within_5d"].dropna()
    if len(hit):
        out["hit_10pct_within_5d_rate"] = proportion_inference(hit.astype(int))
    return out


def placebo_baselines() -> dict[str, Any]:
    """Non-trigger fry days and standard-name vol/dd days: +10% within 12d rate."""
    cross = pd.read_parquet(
        FRY_DIR / "daily_cross_section.parquet",
        columns=["date", "yahoo_symbol", "name_type", "return_1d", "return_1d_pct", "vol_ratio_20d", "fwd_max_5d", "days_to_10pct"],
    )
    panel = pd.read_parquet(
        TURNAROUND_PANEL,
        columns=["date", "yahoo_symbol", "return_5d", "vol_ratio_20d", "bandar_lite_label"],
    )
    cross["date"] = pd.to_datetime(cross["date"])
    panel["date"] = pd.to_datetime(panel["date"])
    df = cross.merge(panel, on=["date", "yahoo_symbol"], how="left", suffixes=("", "_p"))

    trig = pd.read_parquet(FRY_DIR / "trigger_enriched.parquet", columns=["date", "yahoo_symbol"])
    trig["date"] = pd.to_datetime(trig["date"])
    trig_flag = trig.assign(is_trigger=True)[["date", "yahoo_symbol", "is_trigger"]]
    df = df.merge(trig_flag, on=["date", "yahoo_symbol"], how="left")
    df["is_trigger"] = df["is_trigger"].fillna(False)
    df["hit_10_within_12d"] = df["days_to_10pct"].notna() & (df["days_to_10pct"] <= 12)
    vol_dd_mask = (df["vol_ratio_20d"] >= 1.6) & (df["return_5d"] <= -0.04)

    fry = df[df["name_type"] == "fry"].copy()
    fry_placebo = fry[vol_dd_mask.loc[fry.index] & ~fry["is_trigger"]]

    std = df[df["name_type"] == "standard"].copy()
    std_sig = std[vol_dd_mask.loc[std.index]]

    trig_ep = pd.read_parquet(FRY_DIR / "trigger_enriched.parquet", columns=["got_pop"])
    fry_triggers = trig_ep["got_pop"]

    return {
        "fry_trigger_got_pop_episode": proportion_inference(fry_triggers),
        "fry_trigger_hit10_12d_path": proportion_inference(df[df["is_trigger"]]["hit_10_within_12d"].astype(int)),
        "fry_nontrigger_vol_dd_placebo": proportion_inference(fry_placebo["hit_10_within_12d"]),
        "standard_vol_dd_signature": proportion_inference(std_sig["hit_10_within_12d"]),
        "lift_trigger_vs_fry_placebo": round(
            float(fry_triggers.mean()) / max(float(fry_placebo["hit_10_within_12d"].mean()), 1e-9), 3
        ),
        "n_fry_placebo_days": int(len(fry_placebo)),
        "n_standard_vol_dd_days": int(len(std_sig)),
        "interpretation": "If fry triggers are meaningful, hit10-within-12d should exceed matched non-trigger fry days and standard names.",
    }


def mechanism_summary(
    df: pd.DataFrame,
    indicators: list[dict[str, Any]],
    rules: list[dict[str, Any]],
    placebo: dict[str, Any],
    logistic: dict[str, Any],
    era: dict[str, Any],
) -> dict[str, Any]:
    baseline = float(df["got_pop"].mean())
    sig_inds = [i for i in indicators if i.get("fdr_significant_5pct")]
    oos_rules = [r for r in rules if r["era"] == "oos_holdout" and r.get("sufficient")]
    best_oos = max(oos_rules, key=lambda x: x["rate_pct"], default=None)

    return {
        "baseline_pop_rate_pct": round(baseline * 100, 2),
        "mechanism_chain": [
            "1. Fry symbol grinds down (pre10 cum median negative on eventual poppers).",
            "2. Trigger = elevated vol + 5d drawdown OR quiet-build label; fires on LOW cross-section rank days.",
            "3. Waiting period: flat/negative drift — not a hold strategy.",
            "4. Pop = discrete +10-17% ARA day at ~99th cross-section percentile.",
            "5. Fade/giveback often ends episode.",
        ],
        "strongest_fdr_indicators": [
            {"id": i["indicator_id"], "pop_rate_pct": i["pop_rate_pct"], "q": i["fdr_q_value"], "n": i["n"]}
            for i in sig_inds[:8]
        ],
        "best_oos_rule": best_oos,
        "placebo_lift": placebo.get("lift_trigger_vs_fry_placebo"),
        "logistic_oos_auc": logistic.get("oos_auc"),
        "era_stability": {
            "yearly_range": era.get("yearly_rate_range"),
            "yearly_std": era.get("yearly_rate_std"),
        },
        "robustness_verdict": _robustness_verdict(sig_inds, best_oos, logistic, era, placebo),
    }


def _robustness_verdict(
    sig_inds: list,
    best_oos: dict | None,
    logistic: dict,
    era: dict,
    placebo: dict,
) -> str:
    checks = 0
    if len(sig_inds) >= 3:
        checks += 1
    if best_oos and best_oos.get("rate_pct", 0) >= 25 and best_oos.get("n", 0) >= 30:
        checks += 1
    if logistic.get("oos_auc") and logistic["oos_auc"] >= 0.58:
        checks += 1
    yr = era.get("yearly_rate_range") or [0, 0]
    if yr and (yr[1] - yr[0]) < 15:
        checks += 1
    lift = placebo.get("lift_trigger_vs_fry_placebo") or 0
    if lift >= 1.3:
        checks += 1
    if checks >= 4:
        return "robust_moderate"
    if checks >= 2:
        return "partially_robust_monitor"
    return "fragile_insufficient"


def build_robust_empirics() -> dict[str, Any]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df = load_research_frame()
    baseline = float(df["got_pop"].mean())

    report: dict[str, Any] = {
        "meta": {
            "n_triggers": int(len(df)),
            "n_symbols": int(df["yahoo_symbol"].nunique()),
            "date_min": str(df["date"].min().date()),
            "date_max": str(df["date"].max().date()),
            "oos_start": str(OOS_START.date()),
            "baseline_pop_rate_pct": round(baseline * 100, 2),
            "baseline_wilson_ci": proportion_inference(df["got_pop"]),
            "baseline_cluster_bootstrap": cluster_bootstrap_rate(df, "got_pop"),
        },
        "indicator_scan": indicator_scan(df, baseline),
        "composite_rules": rule_validation(df, baseline),
        "logistic_model": logistic_pop_model(df),
        "era_stability": era_stability(df),
        "survival_curves": survival_by_bucket(df),
        "path_outcomes": path_outcomes(df),
        "placebo_baselines": placebo_baselines(),
    }
    report["mechanism_summary"] = mechanism_summary(
        df,
        report["indicator_scan"],
        report["composite_rules"],
        report["placebo_baselines"],
        report["logistic_model"],
        report["era_stability"],
    )

    (OUT_DIR / "robust_empirics_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    # flat indicator table for quick scan
    ind_df = pd.DataFrame(report["indicator_scan"])
    if not ind_df.empty:
        ind_df.to_parquet(OUT_DIR / "indicator_scan.parquet", index=False)
    rules_df = pd.DataFrame(report["composite_rules"])
    if not rules_df.empty:
        rules_df.to_parquet(OUT_DIR / "composite_rules.parquet", index=False)

    return report
