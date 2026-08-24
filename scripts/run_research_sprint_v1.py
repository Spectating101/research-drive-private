#!/usr/bin/env python3
"""First-pass research sprint across fused, broadcast, entity, and crypto panels.

Outputs JSON + CSV summaries under backtests/outputs/research_sprint_v1/.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
FUSED = REPO / "data_lake/research_panels/cross_asset_fused/fused_20260610_v2/cross_asset_fused_primary_panel.parquet"
CRYPTO = REPO / "data_lake/research_panels/cross_asset_fused/fused_20260610_v2/country_week_crypto_news_panel.parquet"
GLOBAL = REPO / "data_lake/research_panels/cross_asset_fused/fused_20260610_v2/global_assets_week_panel.parquet"
BROADCAST = REPO / "data_lake/research_panels/ticker_news_market/ticker_20260610/ticker_week_country_broadcast_panel.parquet"
ENTITY_RES = REPO / "data_lake/research_panels/ticker_news_market/ticker_20260610/ticker_week_entity_residual_panel.parquet"
OUT = REPO / "backtests/outputs/research_sprint_v1"

SHOCKS = [
    "political_instability",
    "governance_corruption",
    "financial_stress",
    "geopolitical_security",
    "macro_policy",
    "trade_supply_chain",
    "health",
    "natural_environment",
]
TARGETS = ["fwd_return_1w", "fwd_return_2w", "fwd_return_4w", "fwd_vol_4w"]


@dataclass
class RegResult:
    shock: str
    target: str
    spec: str
    n: int
    coef: float
    se: float
    tstat: float


def _load(path: Path) -> pd.DataFrame:
    df = pd.read_parquet(path)
    if "week_end" in df.columns:
        df["week_end"] = pd.to_datetime(df["week_end"], errors="coerce")
    return df


def _zscore(s: pd.Series) -> pd.Series:
    s = pd.to_numeric(s, errors="coerce")
    mu, sd = s.mean(), s.std(ddof=0)
    if not np.isfinite(sd) or sd == 0:
        return s * 0.0
    return (s - mu) / sd


def panel_ols(
    df: pd.DataFrame,
    y_col: str,
    x_col: str,
    fe_country: bool = True,
    fe_week: bool = False,
) -> RegResult | None:
    sub = df[["country_iso3", "week_end", y_col, x_col]].replace([np.inf, -np.inf], np.nan).dropna()
    if len(sub) < 100:
        return None
    sub = sub.copy()
    sub["y"] = sub[y_col].astype(float)
    sub["x"] = _zscore(sub[x_col].astype(float))
    if fe_country:
        for c in sorted(sub["country_iso3"].unique())[1:]:
            sub[f"c_{c}"] = (sub["country_iso3"] == c).astype(float)
    if fe_week:
        for w in sorted(sub["week_end"].unique())[1:]:
            sub[f"w_{w.value}"] = (sub["week_end"] == w).astype(float)
    x_cols = ["x"] + [c for c in sub.columns if c.startswith("c_") or c.startswith("w_")]
    x = sub[x_cols].to_numpy(dtype=float)
    y = sub["y"].to_numpy(dtype=float)
    x = np.column_stack([np.ones(len(sub)), x])
    try:
        beta = np.linalg.lstsq(x, y, rcond=None)[0]
        resid = y - x @ beta
        dof = max(len(y) - x.shape[1], 1)
        sigma2 = float((resid @ resid) / dof)
        cov = sigma2 * np.linalg.inv(x.T @ x)
        se = float(np.sqrt(cov[1, 1]))
        coef = float(beta[1])
        tstat = coef / se if se > 0 else float("nan")
    except np.linalg.LinAlgError:
        return None
    spec = "FE_country" if fe_country and not fe_week else "FE_country_week" if fe_country and fe_week else "pooled"
    return RegResult(shock=x_col.replace("_per_1k_rows", ""), target=y_col, spec=spec, n=len(sub), coef=coef, se=se, tstat=tstat)


def event_study(df: pd.DataFrame, shock: str, target: str, z_thresh: float = 1.5) -> dict:
    col = f"{shock}_per_1k_rows"
    if col not in df.columns or target not in df.columns:
        return {}
    tmp = df[["country_iso3", "week_end", col, target]].dropna().copy()
    tmp["z"] = tmp.groupby("country_iso3")[col].transform(
        lambda x: (x - x.mean()) / (x.std(ddof=0) + 1e-9)
    )
    hi = tmp[tmp["z"] >= z_thresh]
    lo = tmp[tmp["z"] < z_thresh]
    return {
        "shock": shock,
        "target": target,
        "z_thresh": z_thresh,
        "hi_n": int(len(hi)),
        "hi_mean": float(hi[target].mean()) if len(hi) else float("nan"),
        "lo_mean": float(lo[target].mean()) if len(lo) else float("nan"),
        "diff": float(hi[target].mean() - lo[target].mean()) if len(hi) and len(lo) else float("nan"),
    }


def cross_section_rank_ic(df: pd.DataFrame, shock: str, target: str) -> dict:
    col = f"{shock}_per_1k_rows"
    if col not in df.columns:
        return {}
    rows = []
    for _, g in df.groupby("week_end"):
        sub = g[[col, target]].dropna()
        if len(sub) < 8:
            continue
        rows.append(sub[col].rank(pct=True).corr(sub[target].rank(pct=True), method="spearman"))
    if not rows:
        return {}
    arr = np.array(rows, dtype=float)
    tstat = float(arr.mean() / (arr.std(ddof=1) / math.sqrt(len(arr)))) if len(arr) > 2 else float("nan")
    return {
        "shock": shock,
        "target": target,
        "weekly_rank_ic_mean": float(arr.mean()),
        "weekly_rank_ic_t": tstat,
        "weeks": int(len(arr)),
    }


def composite_risk(df: pd.DataFrame) -> pd.Series:
    cols = [f"{s}_per_1k_rows" for s in SHOCKS if f"{s}_per_1k_rows" in df.columns]
    if not cols:
        return pd.Series(0.0, index=df.index)
    z = pd.DataFrame({c: _zscore(df[c]) for c in cols})
    return z.sum(axis=1)


def analyze_fused(df: pd.DataFrame) -> dict:
    out: dict = {"panel": "cross_asset_fused_primary", "rows": len(df), "regressions": [], "events": [], "rank_ic": []}
    for shock in SHOCKS:
        col = f"{shock}_per_1k_rows"
        if col not in df.columns:
            continue
        for target in TARGETS:
            r = panel_ols(df, target, col, fe_country=True, fe_week=False)
            if r:
                out["regressions"].append(asdict(r))
            out["events"].append(event_study(df, shock, target))
            out["rank_ic"].append(cross_section_rank_ic(df, shock, target))

    tmp = df.copy()
    tmp["risk_score"] = composite_risk(tmp)
    vol_rows = []
    for q in [0.9, 0.95]:
        thr = tmp["risk_score"].quantile(q)
        hi = tmp[tmp["risk_score"] >= thr]
        lo = tmp[tmp["risk_score"] < thr]
        vol_rows.append(
            {
                "quantile": q,
                "hi_n": int(len(hi)),
                "hi_fwd_vol_4w": float(hi["fwd_vol_4w"].mean()),
                "lo_fwd_vol_4w": float(lo["fwd_vol_4w"].mean()),
                "vol_diff": float(hi["fwd_vol_4w"].mean() - lo["fwd_vol_4w"].mean()),
                "hi_fwd_return_4w": float(hi["fwd_return_4w"].mean()),
                "lo_fwd_return_4w": float(lo["fwd_return_4w"].mean()),
            }
        )
    out["composite_risk"] = vol_rows

    country = (
        df.groupby("country_iso3", as_index=False)
        .agg(
            weeks=("week_end", "count"),
            avg_fwd_return_4w=("fwd_return_4w", "mean"),
            avg_fwd_vol_4w=("fwd_vol_4w", "mean"),
            avg_political=("political_instability_per_1k_rows", "mean"),
            avg_governance=("governance_corruption_per_1k_rows", "mean"),
            avg_macro=("macro_policy_per_1k_rows", "mean"),
        )
        .sort_values("avg_fwd_return_4w", ascending=False)
    )
    out["country_summary"] = country.to_dict(orient="records")
    return out


def analyze_broadcast(df: pd.DataFrame) -> dict:
    out: dict = {"panel": "ticker_week_country_broadcast", "rows": len(df), "symbols": int(df["yahoo_symbol"].nunique())}
    shock_cols = [f"{s}_per_1k_rows" for s in SHOCKS if f"{s}_per_1k_rows" in df.columns]
    rows = []
    for col in shock_cols:
        sub = df[[col, "fwd_return_1w", "fwd_return_4w", "fwd_vol_4w"]].dropna()
        if len(sub) < 500:
            continue
        rows.append(
            {
                "feature": col,
                "n": int(len(sub)),
                "corr_fwd_return_1w": float(sub[col].corr(sub["fwd_return_1w"])),
                "corr_fwd_return_4w": float(sub[col].corr(sub["fwd_return_4w"])),
                "corr_fwd_vol_4w": float(sub[col].corr(sub["fwd_vol_4w"])),
            }
        )
    out["pooled_correlations"] = rows

    # within country-week demeaned
    demean_rows = []
    tmp = df[["country_iso3", "week_end", "yahoo_symbol"] + shock_cols[:4] + ["fwd_return_1w", "fwd_vol_4w"]].copy()
    for col in shock_cols[:4]:
        if col not in tmp.columns:
            continue
        for c in ["fwd_return_1w", "fwd_vol_4w"]:
            tmp[f"d_{col}"] = tmp.groupby(["country_iso3", "week_end"])[col].transform(lambda s: s - s.mean())
            tmp[f"d_{c}"] = tmp.groupby(["country_iso3", "week_end"])[c].transform(lambda s: s - s.mean())
            sub = tmp[[f"d_{col}", f"d_{c}"]].dropna()
            if len(sub) < 500:
                continue
            demean_rows.append(
                {
                    "feature": col,
                    "target": c,
                    "within_country_week_corr": float(sub[f"d_{col}"].corr(sub[f"d_{c}"])),
                    "n": int(len(sub)),
                }
            )
    out["within_country_week"] = demean_rows
    return out


def analyze_entity_residual(df: pd.DataFrame) -> dict:
    out: dict = {
        "panel": "ticker_week_entity_residual",
        "rows": len(df),
        "symbols": int(df["yahoo_symbol"].nunique()) if "yahoo_symbol" in df.columns else 0,
        "week_min": str(df["week_end"].min()),
        "week_max": str(df["week_end"].max()),
    }
    entity_shocks = [
        "governance_corruption_per_1k_entity_rows",
        "political_instability_per_1k_entity_rows",
        "financial_stress_per_1k_entity_rows",
        "macro_policy_per_1k_entity_rows",
    ]
    events = []
    for col in entity_shocks:
        if col not in df.columns:
            continue
        sub = df[[col, "fwd_return_1w", "fwd_return_4w", "fwd_vol_4w"]].dropna()
        sub = sub[sub[col] > 0]
        if len(sub) < 50:
            continue
        thr = sub[col].quantile(0.9)
        hi, lo = sub[sub[col] >= thr], sub[sub[col] < thr]
        events.append(
            {
                "feature": col,
                "n": int(len(sub)),
                "hi_n": int(len(hi)),
                "hi_fwd_return_1w": float(hi["fwd_return_1w"].mean()),
                "lo_fwd_return_1w": float(lo["fwd_return_1w"].mean()),
                "diff_return_1w": float(hi["fwd_return_1w"].mean() - lo["fwd_return_1w"].mean()),
                "hi_fwd_vol_4w": float(hi["fwd_vol_4w"].mean()),
                "lo_fwd_vol_4w": float(lo["fwd_vol_4w"].mean()),
                "diff_vol_4w": float(hi["fwd_vol_4w"].mean() - lo["fwd_vol_4w"].mean()),
            }
        )
    out["entity_events_top_decile"] = events
    return out


def analyze_crypto(crypto: pd.DataFrame, global_df: pd.DataFrame) -> dict:
    out: dict = {"panel": "country_week_crypto_news + global_assets"}
    g = global_df.copy()
    if "week_end" in g.columns:
        g["week_end"] = pd.to_datetime(g["week_end"], errors="coerce")
    c = crypto.copy()
    agg = c.groupby("week_end", as_index=False).agg(
        crypto_news_days=("crypto_news_days", "sum") if "crypto_news_days" in c.columns else ("week_end", "count"),
        macro_policy=("macro_policy_per_1k_rows", "mean") if "macro_policy_per_1k_rows" in c.columns else ("week_end", "count"),
        geopolitical=("geopolitical_security_per_1k_rows", "mean") if "geopolitical_security_per_1k_rows" in c.columns else ("week_end", "count"),
    )
    merged = agg.merge(g, on="week_end", how="inner", suffixes=("_news", "_mkt"))
    rows = []
    for target in [c for c in merged.columns if "BTC" in c and "fwd_return" in c] + [
        c for c in merged.columns if "ETH" in c and "fwd_return" in c
    ]:
        for feat in ["macro_policy", "geopolitical", "crypto_news_days"]:
            if feat not in merged.columns or target not in merged.columns:
                continue
            sub = merged[[feat, target]].dropna()
            if len(sub) < 52:
                continue
            rows.append({"feature": feat, "target": target, "corr": float(sub[feat].corr(sub[target])), "n": int(len(sub))})
    out["global_crypto_correlations"] = rows
    return out


def main() -> int:
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_dir = OUT / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    fused = _load(FUSED)
    results = {
        "built_at_utc": datetime.now(UTC).isoformat(),
        "run_id": run_id,
        "fused": analyze_fused(fused),
        "broadcast": analyze_broadcast(_load(BROADCAST)),
        "entity_residual": analyze_entity_residual(_load(ENTITY_RES)),
    }
    if CRYPTO.exists() and GLOBAL.exists():
        results["crypto"] = analyze_crypto(_load(CRYPTO), _load(GLOBAL))

    # flatten key regression table
    reg_df = pd.DataFrame(results["fused"]["regressions"])
    reg_df.to_csv(out_dir / "fused_panel_regressions.csv", index=False)
    pd.DataFrame(results["fused"]["events"]).to_csv(out_dir / "fused_event_studies.csv", index=False)
    pd.DataFrame(results["fused"]["rank_ic"]).to_csv(out_dir / "fused_rank_ic.csv", index=False)
    pd.DataFrame(results["fused"]["country_summary"]).to_csv(out_dir / "country_summary.csv", index=False)

    (out_dir / "research_sprint_results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")

    # executive highlights
    highlights = []
    if not reg_df.empty:
        vol_regs = reg_df[(reg_df["target"] == "fwd_vol_4w") & (reg_df["spec"] == "FE_country")].sort_values("tstat", key=abs, ascending=False)
        ret4_regs = reg_df[(reg_df["target"] == "fwd_return_4w") & (reg_df["spec"] == "FE_country")].sort_values("tstat", key=abs, ascending=False)
        highlights.append("Top vol predictors (country FE):")
        for _, r in vol_regs.head(5).iterrows():
            highlights.append(f"  {r['shock']}: coef={r['coef']:+.4f} t={r['tstat']:+.2f}")
        highlights.append("Top 4w return predictors (country FE):")
        for _, r in ret4_regs.head(5).iterrows():
            highlights.append(f"  {r['shock']}: coef={r['coef']:+.4f} t={r['tstat']:+.2f}")

    (out_dir / "highlights.txt").write_text("\n".join(highlights), encoding="utf-8")
    print(json.dumps({"run_id": run_id, "out_dir": str(out_dir), "highlights": highlights}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
