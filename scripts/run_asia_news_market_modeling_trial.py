#!/usr/bin/env python3
"""Run lightweight modeling trials on the Asia news-market panel.

This is deliberately modest. It produces walk-forward diagnostics, simple
avoidance-rule tests, and country summaries from the current research panel.
It does not claim live alpha; it creates repeatable evidence to decide what is
worth improving.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd


REPO = Path(__file__).resolve().parents[1]
DEFAULT_PANEL = (
    REPO
    / "data_lake/research_panels/asia_news_market/post_gdelt_parallel_20260526_marresume_repaired/"
    / "asia_country_week_news_market_primary_panel.parquet"
)
DEFAULT_OUT_ROOT = REPO / "backtests/outputs/asia_news_market_modeling"

SIGNAL_FEATURES = [
    "mean_tone_weighted",
    "market_relevant_share",
    "broad_context_share",
    "financial_stress_per_1k_rows",
    "geopolitical_security_per_1k_rows",
    "governance_corruption_per_1k_rows",
    "health_per_1k_rows",
    "macro_policy_per_1k_rows",
    "natural_environment_per_1k_rows",
    "political_instability_per_1k_rows",
    "trade_supply_chain_per_1k_rows",
    "return_1w",
    "return_4w",
]
TARGETS = ["fwd_return_1w", "fwd_return_2w", "fwd_return_4w", "fwd_vol_4w"]
RISK_COMPONENTS = [
    "financial_stress_per_1k_rows",
    "geopolitical_security_per_1k_rows",
    "governance_corruption_per_1k_rows",
    "political_instability_per_1k_rows",
]


@dataclass
class Perf:
    weeks: int
    mean_weekly_return: float
    ann_return: float
    ann_vol: float
    sharpe: float
    max_drawdown: float
    hit_rate: float


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--panel", type=Path, default=DEFAULT_PANEL)
    p.add_argument("--out-root", type=Path, default=DEFAULT_OUT_ROOT)
    p.add_argument("--run-id", default="")
    p.add_argument("--min-train-weeks", type=int, default=52)
    p.add_argument("--ridge-alpha", type=float, default=10.0)
    return p.parse_args()


def load_panel(path: Path) -> pd.DataFrame:
    df = pd.read_parquet(path) if path.suffix.lower() in {".parquet", ".pq"} else pd.read_csv(path)
    df["week_end"] = pd.to_datetime(df["week_end"], errors="coerce")
    df = df.dropna(subset=["week_end", "country_iso3"])
    for col in set(SIGNAL_FEATURES + TARGETS + ["news_rows"]):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.sort_values(["week_end", "country_iso3"]).reset_index(drop=True)


def zscore_from_train(train: pd.DataFrame, frame: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    out = pd.DataFrame(index=frame.index)
    for col in cols:
        med = float(train[col].median()) if train[col].notna().any() else 0.0
        mu = float(train[col].fillna(med).mean())
        sd = float(train[col].fillna(med).std(ddof=0))
        if not np.isfinite(sd) or sd == 0:
            sd = 1.0
        out[col] = (frame[col].fillna(med) - mu) / sd
    return out


def make_design(train: pd.DataFrame, frame: pd.DataFrame, feature_cols: list[str]) -> tuple[np.ndarray, list[str]]:
    x_num = zscore_from_train(train, frame, feature_cols)
    countries = sorted(train["country_iso3"].dropna().unique().tolist())
    for country in countries[1:]:
        x_num[f"country__{country}"] = (frame["country_iso3"] == country).astype(float)
    x_num.insert(0, "intercept", 1.0)
    return x_num.to_numpy(dtype=float), x_num.columns.tolist()


def ridge_fit_predict(
    train: pd.DataFrame,
    test: pd.DataFrame,
    feature_cols: list[str],
    target: str,
    alpha: float,
) -> np.ndarray:
    sub = train[feature_cols + ["country_iso3", target]].replace([np.inf, -np.inf], np.nan).dropna(subset=[target])
    if len(sub) < 30:
        return np.full(len(test), np.nan)
    x, _ = make_design(sub, sub, feature_cols)
    y = sub[target].to_numpy(dtype=float)
    xtx = x.T @ x
    penalty = np.eye(xtx.shape[0]) * alpha
    penalty[0, 0] = 0.0
    try:
        beta = np.linalg.solve(xtx + penalty, x.T @ y)
    except np.linalg.LinAlgError:
        beta = np.linalg.pinv(xtx + penalty) @ x.T @ y
    x_test, _ = make_design(sub, test, feature_cols)
    return x_test @ beta


def cross_sectional_spearman(frame: pd.DataFrame, pred_col: str, target: str) -> pd.DataFrame:
    rows = []
    for week, group in frame.groupby("week_end"):
        sub = group[[pred_col, target]].replace([np.inf, -np.inf], np.nan).dropna()
        if len(sub) < 5 or sub[pred_col].nunique() < 3 or sub[target].nunique() < 3:
            continue
        rows.append({"week_end": week, "spearman": float(sub[pred_col].corr(sub[target], method="spearman"))})
    return pd.DataFrame(rows)


def perf(returns: pd.Series) -> Perf:
    returns = pd.to_numeric(returns, errors="coerce").dropna()
    if returns.empty:
        return Perf(0, float("nan"), float("nan"), float("nan"), float("nan"), float("nan"), float("nan"))
    equity = (1.0 + returns).cumprod()
    peak = equity.cummax()
    dd = equity / peak - 1.0
    mean = float(returns.mean())
    vol = float(returns.std(ddof=1))
    ann_return = float((equity.iloc[-1]) ** (52.0 / len(returns)) - 1.0) if equity.iloc[-1] > 0 else float("nan")
    ann_vol = float(vol * math.sqrt(52.0)) if np.isfinite(vol) else float("nan")
    sharpe = float(mean / vol * math.sqrt(52.0)) if vol and np.isfinite(vol) else float("nan")
    return Perf(
        weeks=int(len(returns)),
        mean_weekly_return=mean,
        ann_return=ann_return,
        ann_vol=ann_vol,
        sharpe=sharpe,
        max_drawdown=float(dd.min()),
        hit_rate=float((returns > 0).mean()),
    )


def build_risk_scores(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    feature_cols = [c for c in RISK_COMPONENTS if c in out.columns]
    pieces = []
    for week, group in out.groupby("week_end"):
        tmp = pd.DataFrame(index=group.index)
        for col in feature_cols:
            values = group[col].fillna(group[col].median())
            sd = values.std(ddof=0)
            tmp[col] = 0.0 if not np.isfinite(sd) or sd == 0 else (values - values.mean()) / sd
        if "mean_tone_weighted" in group.columns:
            tone = group["mean_tone_weighted"].fillna(group["mean_tone_weighted"].median())
            sd = tone.std(ddof=0)
            tmp["negative_tone"] = 0.0 if not np.isfinite(sd) or sd == 0 else -(tone - tone.mean()) / sd
        out.loc[group.index, "risk_score"] = tmp.sum(axis=1)
        pieces.append(tmp)
    out["risk_score"] = out["risk_score"].fillna(0.0)
    return out


def avoidance_tests(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for target in ["fwd_return_1w", "fwd_return_2w", "fwd_return_4w"]:
        weekly = []
        for week, group in df.groupby("week_end"):
            sub = group[["country_iso3", "risk_score", target]].dropna()
            if len(sub) < 8:
                continue
            eq = float(sub[target].mean())
            avoid_top3 = float(sub.nsmallest(max(1, len(sub) - 3), "risk_score")[target].mean())
            low_risk = float(sub.nsmallest(max(1, len(sub) // 3), "risk_score")[target].mean())
            high_risk = float(sub.nlargest(max(1, len(sub) // 3), "risk_score")[target].mean())
            weekly.append(
                {
                    "week_end": week,
                    "equal_weight": eq,
                    "avoid_top3_risk": avoid_top3,
                    "low_risk_tercile": low_risk,
                    "high_risk_tercile": high_risk,
                    "avoid_minus_equal": avoid_top3 - eq,
                    "low_minus_high": low_risk - high_risk,
                }
            )
        w = pd.DataFrame(weekly)
        if w.empty:
            continue
        for strategy in ["equal_weight", "avoid_top3_risk", "low_risk_tercile", "high_risk_tercile", "avoid_minus_equal", "low_minus_high"]:
            result = asdict(perf(w[strategy]))
            result.update({"target": target, "strategy": strategy})
            rows.append(result)
    return pd.DataFrame(rows)


def prediction_strategy(preds: pd.DataFrame) -> pd.DataFrame:
    rows = []
    target = "fwd_return_1w"
    pred_col = f"pred_{target}"
    weekly = []
    for week, group in preds.groupby("week_end"):
        sub = group[[pred_col, target, "risk_score"]].replace([np.inf, -np.inf], np.nan).dropna()
        if len(sub) < 8 or sub[pred_col].nunique() < 3:
            continue
        top_n = max(1, len(sub) // 3)
        bottom_n = max(1, len(sub) // 3)
        eq = float(sub[target].mean())
        top = float(sub.nlargest(top_n, pred_col)[target].mean())
        bottom = float(sub.nsmallest(bottom_n, pred_col)[target].mean())
        filtered = sub[sub["risk_score"] <= sub["risk_score"].quantile(0.75)]
        top_filtered = float(filtered.nlargest(max(1, len(filtered) // 3), pred_col)[target].mean()) if len(filtered) >= 5 else float("nan")
        weekly.append(
            {
                "week_end": week,
                "equal_weight": eq,
                "top_predicted": top,
                "bottom_predicted": bottom,
                "top_minus_bottom": top - bottom,
                "top_minus_equal": top - eq,
                "top_predicted_ex_high_risk": top_filtered,
            }
        )
    w = pd.DataFrame(weekly)
    if w.empty:
        return pd.DataFrame()
    for strategy in [c for c in w.columns if c != "week_end"]:
        result = asdict(perf(w[strategy]))
        result.update({"target": target, "strategy": strategy})
        rows.append(result)
    return pd.DataFrame(rows)


def walk_forward(df: pd.DataFrame, min_train_weeks: int, alpha: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    feature_cols = [col for col in SIGNAL_FEATURES if col in df.columns]
    weeks = sorted(df["week_end"].dropna().unique())
    pred_frames = []
    for idx, week in enumerate(weeks):
        if idx < min_train_weeks:
            continue
        train = df[df["week_end"] < week]
        test = df[df["week_end"] == week].copy()
        if test.empty:
            continue
        for target in TARGETS:
            if target not in df.columns:
                continue
            test[f"pred_{target}"] = ridge_fit_predict(train, test, feature_cols, target, alpha)
        pred_frames.append(test)
    preds = pd.concat(pred_frames, ignore_index=True) if pred_frames else pd.DataFrame()

    rows = []
    if not preds.empty:
        for target in TARGETS:
            pred_col = f"pred_{target}"
            if pred_col not in preds.columns:
                continue
            sub = preds[[pred_col, target]].replace([np.inf, -np.inf], np.nan).dropna()
            if len(sub) < 5:
                continue
            pearson = float(sub[pred_col].corr(sub[target], method="pearson"))
            spearman = float(sub[pred_col].corr(sub[target], method="spearman"))
            ic = cross_sectional_spearman(preds, pred_col, target)
            rows.append(
                {
                    "target": target,
                    "n": int(len(sub)),
                    "pearson": pearson,
                    "spearman": spearman,
                    "weekly_ic_mean": float(ic["spearman"].mean()) if not ic.empty else float("nan"),
                    "weekly_ic_t": float(ic["spearman"].mean() / (ic["spearman"].std(ddof=1) / math.sqrt(len(ic)))) if len(ic) > 1 and ic["spearman"].std(ddof=1) > 0 else float("nan"),
                    "weeks": int(len(ic)),
                }
            )
    return preds, pd.DataFrame(rows)


def write_readme(out_dir: Path, summary: dict[str, object]) -> None:
    lines = [
        "# Asia News-Market Modeling Trial",
        "",
        f"- Built at UTC: `{summary['built_at_utc']}`",
        f"- Panel: `{summary['panel']}`",
        f"- Rows: `{summary['rows']}`",
        f"- Countries: `{', '.join(summary['countries'])}`",
        f"- Date range: `{summary['date_min']}` to `{summary['date_max']}`",
        "",
        "## Interpretation",
        "",
        "This is a background modeling trial, not a live trading system. It tests whether news-shock features add useful ranking or avoidance information over the current 2024-2026 panel.",
        "",
        "Primary files:",
        "",
        "- `walkforward_predictions.csv`: expanding-window ridge predictions.",
        "- `walkforward_summary.csv`: prediction/realized correlations and weekly IC.",
        "- `avoidance_backtest.csv`: simple risk-avoidance rule diagnostics.",
        "- `prediction_strategy_backtest.csv`: top-vs-bottom predicted return diagnostics.",
        "- `country_signal_summary.csv`: country-level average signal/outcome profile.",
    ]
    (out_dir / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    run_id = args.run_id or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_dir = args.out_root / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    df = build_risk_scores(load_panel(args.panel))
    preds, wf_summary = walk_forward(df, args.min_train_weeks, args.ridge_alpha)
    avoidance = avoidance_tests(df)
    pred_strategy = prediction_strategy(preds) if not preds.empty else pd.DataFrame()

    country_summary = (
        df.groupby("country_iso3", as_index=False)
        .agg(
            weeks=("week_end", "nunique"),
            avg_news_rows=("news_rows", "mean"),
            avg_risk_score=("risk_score", "mean"),
            avg_fwd_return_1w=("fwd_return_1w", "mean"),
            avg_fwd_return_4w=("fwd_return_4w", "mean"),
            avg_fwd_vol_4w=("fwd_vol_4w", "mean"),
            avg_political_instability=("political_instability_per_1k_rows", "mean"),
            avg_governance_corruption=("governance_corruption_per_1k_rows", "mean"),
            avg_trade_supply_chain=("trade_supply_chain_per_1k_rows", "mean"),
            avg_macro_policy=("macro_policy_per_1k_rows", "mean"),
        )
        .sort_values("avg_risk_score", ascending=False)
    )

    df.to_csv(out_dir / "feature_panel_with_risk_score.csv", index=False)
    if not preds.empty:
        preds.to_csv(out_dir / "walkforward_predictions.csv", index=False)
    wf_summary.to_csv(out_dir / "walkforward_summary.csv", index=False)
    avoidance.to_csv(out_dir / "avoidance_backtest.csv", index=False)
    pred_strategy.to_csv(out_dir / "prediction_strategy_backtest.csv", index=False)
    country_summary.to_csv(out_dir / "country_signal_summary.csv", index=False)

    summary = {
        "built_at_utc": datetime.now(UTC).isoformat(),
        "run_id": run_id,
        "panel": str(args.panel),
        "rows": int(len(df)),
        "countries": sorted(df["country_iso3"].dropna().unique().tolist()),
        "date_min": str(df["week_end"].min().date()) if df["week_end"].notna().any() else "",
        "date_max": str(df["week_end"].max().date()) if df["week_end"].notna().any() else "",
        "min_train_weeks": int(args.min_train_weeks),
        "ridge_alpha": float(args.ridge_alpha),
        "outputs": {
            "feature_panel": str(out_dir / "feature_panel_with_risk_score.csv"),
            "walkforward_predictions": str(out_dir / "walkforward_predictions.csv"),
            "walkforward_summary": str(out_dir / "walkforward_summary.csv"),
            "avoidance_backtest": str(out_dir / "avoidance_backtest.csv"),
            "prediction_strategy_backtest": str(out_dir / "prediction_strategy_backtest.csv"),
            "country_signal_summary": str(out_dir / "country_signal_summary.csv"),
        },
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    write_readme(out_dir, summary)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
