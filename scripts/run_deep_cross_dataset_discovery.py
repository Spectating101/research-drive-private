#!/usr/bin/env python3
"""Blind cross-dataset factor discovery — no pre-assumed shock taxonomy.

Mines ALL numeric columns across fused / ticker-entity / global / alpha panels,
scores predictive power OOS (2024+), cross-references spillovers and emergent links.
"""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "backtests/outputs/platform/deep_research"
OOS_CUT = pd.Timestamp("2024-01-01")

PATHS = {
    "fused": REPO / "data_lake/research_panels/cross_asset_fused/fused_20260610_v2/cross_asset_fused_primary_panel.parquet",
    "global_w": REPO / "data_lake/research_panels/cross_asset_fused/fused_20260610_v2/global_assets_week_panel.parquet",
    "entity": REPO / "data_lake/research_panels/ticker_news_market/ticker_20260611/ticker_week_entity_market_panel.parquet",
    "residual": REPO / "data_lake/research_panels/ticker_news_market/ticker_20260610/ticker_week_entity_residual_panel.parquet",
    "reddit": REPO / "data_lake/sentiment/reddit_daily_signals.parquet",
    "alpha_feat": REPO / "backtests/outputs/alpha_feature_cache/daily_alpha_features.parquet",
    "alpha_px": REPO / "data_lake/daily_alpha_panel.csv",
}


def _z(s: pd.Series) -> pd.Series:
    s = pd.to_numeric(s, errors="coerce")
    mu, sd = float(s.mean()), float(s.std(ddof=0))
    if not np.isfinite(sd) or sd < 1e-12:
        return s * 0.0
    return (s - mu) / sd


def weekly_rank_ic(df: pd.DataFrame, x: str, y: str) -> tuple[float, float, int]:
    ics = []
    for _, g in df.groupby("week_end"):
        sub = g[[x, y]].dropna()
        if len(sub) < 6:
            continue
        ic = sub[x].rank().corr(sub[y].rank())
        if np.isfinite(ic):
            ics.append(float(ic))
    if len(ics) < 10:
        return np.nan, np.nan, len(ics)
    arr = np.array(ics)
    mu = float(arr.mean())
    sd = float(arr.std(ddof=1))
    t = mu / (sd / math.sqrt(len(arr))) if sd > 1e-12 else np.nan
    return mu, t, len(ics)


def panel_fe_t(df: pd.DataFrame, y: str, x: str, fe: str = "country_iso3") -> tuple[float, float, int]:
    cols = [fe, "week_end", y, x]
    sub = df[cols].replace([np.inf, -np.inf], np.nan).dropna()
    if len(sub) < 150:
        return np.nan, np.nan, len(sub)
    sub = sub.copy()
    sub["y"] = sub[y].astype(float)
    sub["x"] = _z(sub[x].astype(float))
    dummies = []
    for c in sorted(sub[fe].astype(str).unique())[1:]:
        sub[f"f_{c}"] = (sub[fe].astype(str) == c).astype(float)
        dummies.append(f"f_{c}")
    X = sub[["x"] + dummies].to_numpy(float)
    yv = sub["y"].to_numpy(float)
    beta, *_ = np.linalg.lstsq(X, yv, rcond=None)
    resid = yv - X @ beta
    n, k = X.shape
    s2 = float((resid @ resid) / max(n - k, 1))
    try:
        se = float(np.sqrt(s2 * np.linalg.inv(X.T @ X)[0, 0]))
        t = float(beta[0] / se) if se > 1e-12 else np.nan
    except np.linalg.LinAlgError:
        t = np.nan
    return float(beta[0]), t, n


def score_feature(
    df: pd.DataFrame,
    feature: str,
    target: str,
    *,
    dataset: str,
    fe: str = "country_iso3",
    split_col: str = "week_end",
) -> dict | None:
    if feature not in df.columns or target not in df.columns:
        return None
    if not pd.api.types.is_numeric_dtype(df[feature]):
        return None
    sub = df[[split_col, fe, feature, target]].copy() if fe in df.columns else df[[split_col, feature, target]].copy()
    sub[split_col] = pd.to_datetime(sub[split_col])
    sub = sub.replace([np.inf, -np.inf], np.nan).dropna(subset=[feature, target])
    if len(sub) < 200:
        return None

    is_mask = sub[split_col] < OOS_CUT
    oos_mask = sub[split_col] >= OOS_CUT
    if oos_mask.sum() < 80 or is_mask.sum() < 200:
        return None

    if fe in sub.columns:
        ric_oos_m, ric_oos_t, w_oos = weekly_rank_ic(sub[oos_mask], feature, target)
        ric_is_m, ric_is_t, w_is = weekly_rank_ic(sub[is_mask], feature, target)
        fe_oos_b, fe_oos_t, n_oos = panel_fe_t(sub[oos_mask], target, feature, fe=fe)
        fe_is_b, fe_is_t, n_is = panel_fe_t(sub[is_mask], target, feature, fe=fe)
    else:
        # global time-series: spearman on levels
        ric_oos_m = float(sub.loc[oos_mask, feature].corr(sub.loc[oos_mask, target], method="spearman"))
        ric_is_m = float(sub.loc[is_mask, feature].corr(sub.loc[is_mask, target], method="spearman"))
        ric_oos_t = ric_is_t = fe_oos_t = fe_is_t = np.nan
        fe_oos_b = fe_is_b = np.nan
        w_oos = int(oos_mask.sum())
        w_is = int(is_mask.sum())
        n_oos = w_oos
        n_is = w_is

    stability = abs(ric_oos_t) / max(abs(ric_is_t), 0.5) if fe in sub.columns and np.isfinite(ric_oos_t) else np.nan
    # discovery score: OOS only, penalize IS>>OOS (overfit)
    disc = abs(ric_oos_t) if np.isfinite(ric_oos_t) else abs(fe_oos_t) if np.isfinite(fe_oos_t) else 0.0
    if np.isfinite(stability) and stability < 0.35:
        disc *= 0.5  # sign flip or collapse OOS

    return {
        "dataset": dataset,
        "feature": feature,
        "target": target,
        "oos_rank_ic": ric_oos_m,
        "oos_rank_ic_t": ric_oos_t,
        "is_rank_ic_t": ric_is_t,
        "oos_fe_t": fe_oos_t,
        "is_fe_t": fe_is_t,
        "oos_weeks": w_oos,
        "stability_ratio": stability,
        "discovery_score": disc,
        "n_oos": n_oos,
    }


def numeric_features(df: pd.DataFrame, exclude: set[str]) -> list[str]:
    out = []
    for c in df.columns:
        if c in exclude:
            continue
        if pd.api.types.is_numeric_dtype(df[c]):
            if df[c].notna().sum() > 100 and df[c].std(ddof=0) > 1e-12:
                out.append(c)
    return out


def sweep_fused() -> list[dict]:
    df = pd.read_parquet(PATHS["fused"])
    df["week_end"] = pd.to_datetime(df["week_end"])
    exclude = {"week_end", "index"}
    feats = numeric_features(df, exclude)
    targets = [c for c in feats if c.startswith("fwd_") or c.startswith("global_") and "fwd_return" in c]
    # also country fwd
    targets += [c for c in ["fwd_return_1w", "fwd_return_2w", "fwd_return_4w", "fwd_vol_4w"] if c in df.columns]
    targets = sorted(set(targets))
    feat_pool = [c for c in feats if c not in targets and not c.startswith("fwd_") and not c.startswith("global_")]
    rows = []
    for f in feat_pool:
        for t in targets:
            r = score_feature(df, f, t, dataset="fused_country", fe="country_iso3")
            if r:
                rows.append(r)
    return rows


def build_asia_aggregate() -> pd.DataFrame:
    """Weekly Asia-wide aggregates — cross-country meta signal."""
    df = pd.read_parquet(PATHS["fused"])
    df["week_end"] = pd.to_datetime(df["week_end"])
    num = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    meta = [c for c in num if c not in {"index"} and not c.startswith("global_") and not c.startswith("fwd_")]
    agg = df.groupby("week_end")[meta].agg(["mean", "std", "max"])
    agg.columns = [f"asia_{a}_{b}" for a, b in agg.columns]
    agg = agg.reset_index()
    g = pd.read_parquet(PATHS["global_w"])
    g["week_end"] = pd.to_datetime(g["week_end"])
    vix = pd.read_parquet(REPO / "data_lake/research_panels/cross_asset_fused/fused_20260610_v2/macro_vix_week_panel.parquet")
    vix["week_end"] = pd.to_datetime(vix["week_end"])
    m = agg.merge(g, on="week_end", how="inner").merge(vix, on="week_end", how="left")
    return m


def sweep_global_spillover() -> list[dict]:
    m = build_asia_aggregate()
    exclude = {"week_end"}
    feats = numeric_features(m, exclude)
    targets = [c for c in feats if "fwd_return" in c or c in ("vix_fwd_return_1w",)]
    feat_pool = [c for c in feats if c not in targets and not c.endswith("_price")]
    rows = []
    for f in feat_pool:
        for t in targets:
            r = score_feature(m, f, t, dataset="asia_to_global", fe="week_end")  # no FE, ts only
            if r:
                r["fe"] = "none_ts"
                rows.append(r)
    return rows


def sweep_entity() -> list[dict]:
    df = pd.read_parquet(PATHS["entity"])
    df["week_end"] = pd.to_datetime(df["week_end"])
    exclude = {"week_end", "confidence"}  # confidence might be coded wrong
    feats = numeric_features(df, exclude)
    targets = [c for c in ["fwd_return_1w", "fwd_return_2w", "fwd_return_4w", "fwd_vol_4w"] if c in df.columns]
    feat_pool = [c for c in feats if c not in targets and not c.startswith("fwd_") and c != "price"]
    rows = []
    for f in feat_pool:
        for t in targets:
            r = score_feature(df, f, t, dataset="ticker_entity", fe="country_iso3")
            if r:
                rows.append(r)
    return rows


def sweep_entity_cross_section() -> list[dict]:
    """Within week, across tickers — does feature RANK predict return rank?"""
    df = pd.read_parquet(PATHS["entity"])
    df["week_end"] = pd.to_datetime(df["week_end"])
    idn = df[df["country_iso3"] == "IDN"].copy()
    feats = [
        c
        for c in idn.columns
        if pd.api.types.is_numeric_dtype(idn[c])
        and c not in {"price", "return_1w", "return_4w"}
        and not c.startswith("fwd_")
    ]
    targets = ["fwd_return_1w", "fwd_return_4w", "fwd_vol_4w"]
    rows = []
    for f in feats:
        for t in targets:
            ics_is, ics_oos = [], []
            for dt, g in idn.groupby("week_end"):
                sub = g[[f, t]].dropna()
                if len(sub) < 8:
                    continue
                ic = sub[f].rank().corr(sub[t].rank())
                if not np.isfinite(ic):
                    continue
                (ics_oos if dt >= OOS_CUT else ics_is).append(ic)
            if len(ics_oos) < 15:
                continue
            oos_arr = np.array(ics_oos)
            is_arr = np.array(ics_is) if ics_is else np.array([0.0])
            oos_t = float(oos_arr.mean() / (oos_arr.std(ddof=1) / math.sqrt(len(oos_arr)) + 1e-12))
            is_t = float(is_arr.mean() / (is_arr.std(ddof=1) / math.sqrt(len(is_arr)) + 1e-12))
            stab = abs(oos_t) / max(abs(is_t), 0.5)
            disc = abs(oos_t) * (1.0 if stab >= 0.35 else 0.5)
            rows.append(
                {
                    "dataset": "idn_ticker_xs",
                    "feature": f,
                    "target": t,
                    "oos_rank_ic": float(oos_arr.mean()),
                    "oos_rank_ic_t": oos_t,
                    "is_rank_ic_t": is_t,
                    "oos_fe_t": np.nan,
                    "is_fe_t": np.nan,
                    "oos_weeks": len(ics_oos),
                    "stability_ratio": stab,
                    "discovery_score": disc,
                    "n_oos": len(ics_oos) * 8,
                }
            )
    return rows


def sweep_residual() -> list[dict]:
    p = PATHS["residual"]
    if not p.exists():
        return []
    df = pd.read_parquet(p)
    df["week_end"] = pd.to_datetime(df["week_end"])
    feats = numeric_features(df, {"week_end", "price"})
    targets = [c for c in ["fwd_return_1w", "fwd_return_4w", "fwd_vol_4w"] if c in df.columns]
    feat_pool = [c for c in feats if c not in targets and not c.startswith("fwd_")]
    rows = []
    for f in feat_pool:
        for t in targets:
            r = score_feature(df, f, t, dataset="entity_residual", fe="country_iso3")
            if r:
                rows.append(r)
    return rows


def sweep_alpha_cross_asset() -> list[dict]:
    if not PATHS["alpha_feat"].exists():
        return []
    feats = pd.read_parquet(PATHS["alpha_feat"])
    feats["date"] = pd.to_datetime(feats["date"])
    px = pd.read_csv(PATHS["alpha_px"])
    px["Date"] = pd.to_datetime(px["Date"])
    tickers = [c for c in px.columns if c != "Date"]
    px[tickers] = px[tickers].apply(pd.to_numeric, errors="coerce")
    px = px.set_index("Date").sort_index()
    fwd21 = px.pct_change(21).shift(-21)

    feat_cols = [c for c in feats.columns if c not in {"date", "instrument"}]
    rows = []
    for col in feat_cols:
        ics_is, ics_oos = [], []
        for dt, g in feats.groupby("date"):
            if dt not in fwd21.index:
                continue
            sub = g[["instrument", col]].dropna()
            if len(sub) < 5:
                continue
            rets = []
            xs = []
            for _, row in sub.iterrows():
                sym = str(row["instrument"])
                if sym in fwd21.columns:
                    r = fwd21.loc[dt, sym]
                    if np.isfinite(r):
                        rets.append(float(r))
                        xs.append(float(row[col]))
            if len(rets) < 5:
                continue
            ic = pd.Series(xs).rank().corr(pd.Series(rets).rank())
            if not np.isfinite(ic):
                continue
            (ics_oos if dt >= OOS_CUT else ics_is).append(ic)
        if len(ics_oos) < 20:
            continue
        oos_arr = np.array(ics_oos)
        is_arr = np.array(ics_is) if ics_is else np.array([0.0])
        oos_t = float(oos_arr.mean() / (oos_arr.std(ddof=1) / math.sqrt(len(oos_arr)) + 1e-12))
        is_t = float(is_arr.mean() / (is_arr.std(ddof=1) / math.sqrt(len(is_arr)) + 1e-12))
        stab = abs(oos_t) / max(abs(is_t), 0.5)
        rows.append(
            {
                "dataset": "alpha_book_xs",
                "feature": col,
                "target": "fwd_return_21d",
                "oos_rank_ic": float(oos_arr.mean()),
                "oos_rank_ic_t": oos_t,
                "is_rank_ic_t": is_t,
                "oos_fe_t": np.nan,
                "is_fe_t": np.nan,
                "oos_weeks": len(ics_oos),
                "stability_ratio": stab,
                "discovery_score": abs(oos_t) * (1.0 if stab >= 0.35 else 0.5),
                "n_oos": len(ics_oos) * 5,
            }
        )
    return rows


def sweep_reddit_btc() -> list[dict]:
    if not PATHS["reddit"].exists():
        return []
    r = pd.read_parquet(PATHS["reddit"])
    r["Date"] = pd.to_datetime(r["Date"])
    crypto = r[r["Ticker"].isin(["BTC", "BTC-USD", "ETH", "ETH-USD", "MSTR", "COIN"])].copy()
    if crypto.empty:
        crypto = r.copy()
    w = crypto.set_index("Date").resample("W-FRI").mean(numeric_only=True).reset_index()
    w = w.rename(columns={"Date": "week_end"})
    g = pd.read_parquet(PATHS["global_w"])[
        ["week_end", "global_BTC-USD_fwd_return_1w", "global_ETH-USD_fwd_return_1w", "global_BTC-USD_return_1w"]
    ]
    g["week_end"] = pd.to_datetime(g["week_end"])
    m = w.merge(g, on="week_end", how="inner")
    feats = numeric_features(m, {"week_end"})
    targets = [c for c in m.columns if "fwd_return" in c]
    rows = []
    for f in feats:
        for t in targets:
            r0 = score_feature(m, f, t, dataset="reddit_crypto", fe="week_end")
            if r0:
                rows.append(r0)
    return rows


def find_lead_lag() -> list[dict]:
    """CHN meta → IDN / global next-week — contagion discovery."""
    df = pd.read_parquet(PATHS["fused"])
    df["week_end"] = pd.to_datetime(df["week_end"])
    chn = df[df["country_iso3"] == "CHN"].set_index("week_end").sort_index()
    idn = df[df["country_iso3"] == "IDN"].set_index("week_end").sort_index()
    g = pd.read_parquet(PATHS["global_w"]).set_index("week_end").sort_index()

    drivers = numeric_features(chn.reset_index(), {"week_end", "country_iso3", "index"})
    drivers = [c for c in drivers if not c.startswith("fwd_") and not c.startswith("global_")][:60]

    rows = []
    for d in drivers:
        x = chn[d].shift(0)
        for label, yseries in [
            ("idn_fwd_return_1w", idn["fwd_return_1w"]),
            ("idn_fwd_vol_4w", idn["fwd_vol_4w"]),
            ("btc_fwd_return_1w", g["global_BTC-USD_fwd_return_1w"]),
            ("eem_fwd_return_1w", g["global_EEM_fwd_return_1w"]),
        ]:
            aligned = pd.concat([_z(x), yseries], axis=1, join="inner").dropna()
            aligned.columns = ["x", "y"]
            if len(aligned) < 100:
                continue
            oos = aligned[aligned.index >= OOS_CUT]
            is_ = aligned[aligned.index < OOS_CUT]
            if len(oos) < 30:
                continue
            oos_ic = oos["x"].corr(oos["y"], method="spearman")
            is_ic = is_["x"].corr(is_["y"], method="spearman")
            rows.append(
                {
                    "dataset": "lead_lag_chn",
                    "feature": d,
                    "target": label,
                    "oos_rank_ic": float(oos_ic),
                    "oos_rank_ic_t": float(oos_ic) * math.sqrt(len(oos)),  # rough
                    "is_rank_ic_t": float(is_ic) * math.sqrt(len(is_)),
                    "oos_weeks": len(oos),
                    "stability_ratio": abs(oos_ic) / max(abs(is_ic), 0.05),
                    "discovery_score": abs(oos_ic) * math.sqrt(len(oos)),
                }
            )
    return rows


def emergent_composites(df_rows: pd.DataFrame) -> list[dict]:
    """Check if discovered top features cluster into interpretable composites."""
    top = df_rows.sort_values("discovery_score", ascending=False).head(30)
    clusters: dict[str, list[str]] = {}
    for _, r in top.iterrows():
        f = str(r["feature"])
        if "tone" in f or "relevance" in f:
            clusters.setdefault("tone_relevance", []).append(f)
        elif "entity" in f or "unique_ent" in f:
            clusters.setdefault("entity_attention", []).append(f)
        elif "crypto" in f or "bitcoin" in f or "ethereum" in f:
            clusters.setdefault("crypto_native", []).append(f)
        elif "news_rows" in f or "unique_urls" in f or "high_priority" in f:
            clusters.setdefault("news_volume_meta", []).append(f)
        elif "vix" in f:
            clusters.setdefault("macro_vol", []).append(f)
        elif "per_1k" in f or "share" in f:
            clusters.setdefault("taxonomy_shock", []).append(f)
        elif f.startswith("asia_"):
            clusters.setdefault("asia_dispersion", []).append(f)
        else:
            clusters.setdefault("other", []).append(f)
    return [{"cluster": k, "features": v, "n": len(v)} for k, v in sorted(clusters.items(), key=lambda x: -len(x[1]))]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    print("Sweeping fused country panel (blind)...")
    all_rows: list[dict] = []
    all_rows.extend(sweep_fused())
    print(f"  fused: {len(all_rows)} pairs")
    print("Sweeping Asia→global spillover...")
    g_rows = sweep_global_spillover()
    all_rows.extend(g_rows)
    print(f"  spillover: {len(g_rows)} pairs")
    print("Sweeping ticker entity panel...")
    e_rows = sweep_entity()
    all_rows.extend(e_rows)
    print(f"  entity: {len(e_rows)} pairs")
    print("Sweeping IDN cross-section...")
    xs = sweep_entity_cross_section()
    all_rows.extend(xs)
    print(f"  idn_xs: {len(xs)} pairs")
    print("Sweeping entity residual...")
    all_rows.extend(sweep_residual())
    print("Sweeping alpha book cross-section...")
    all_rows.extend(sweep_alpha_cross_asset())
    print("Sweeping reddit→crypto...")
    all_rows.extend(sweep_reddit_btc())
    print("Lead-lag CHN→...")
    all_rows.extend(find_lead_lag())

    df = pd.DataFrame(all_rows)
    df = df.sort_values("discovery_score", ascending=False)

    # Exclude known taxonomy-only if other clusters compete
    top50 = df.head(50).to_dict(orient="records")
    top_oos_stable = df[(df["stability_ratio"].fillna(0) >= 0.35)].head(30).to_dict(orient="records")

    # Best per target type
    vol_hits = df[df["target"].astype(str).str.contains("vol")].head(10).to_dict(orient="records")
    ret_hits = df[df["target"].astype(str).str.contains("return")].head(10).to_dict(orient="records")

    clusters = emergent_composites(df)

    # Meta verdict from data
    best = df.iloc[0].to_dict() if not df.empty else {}
    stable_best = (
        df[(df["stability_ratio"].fillna(0) >= 0.35)].iloc[0].to_dict() if (df["stability_ratio"].fillna(0) >= 0.35).any() else best
    )

    manifest = {
        "built_at_utc": datetime.now(UTC).isoformat(),
        "method": "blind_numeric_sweep_oos_2024+",
        "n_pairs_tested": len(df),
        "oos_cutoff": str(OOS_CUT.date()),
        "verdict": {
            "headline": "Data-discovered signal (not pre-labelled taxonomy)",
            "top_discovery": best,
            "top_oos_stable": stable_best,
            "cluster_mix": clusters,
        },
        "top_50": top50,
        "top_oos_stable": top_oos_stable,
        "top_vol": vol_hits,
        "top_return": ret_hits,
    }

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    jpath = OUT / f"discovery_{stamp}.json"
    latest = OUT / "latest.json"
    mpath = OUT / "latest.md"
    jpath.write_text(json.dumps(manifest, indent=2, default=str) + "\n", encoding="utf-8")
    latest.write_text(json.dumps(manifest, indent=2, default=str) + "\n", encoding="utf-8")

    lines = [
        "# Deep research — blind cross-dataset discovery",
        f"- built: {manifest['built_at_utc']}",
        f"- pairs tested: {manifest['n_pairs_tested']}",
        f"- OOS from: {manifest['oos_cutoff']}",
        "",
        "## Top discovery (OOS score)",
    ]
    for k in ("feature", "target", "dataset", "oos_rank_ic_t", "oos_fe_t", "stability_ratio", "discovery_score"):
        if k in best:
            lines.append(f"- {k}: {best[k]}")
    lines += ["", "## Clusters in top 30", ""]
    for c in clusters:
        lines.append(f"- **{c['cluster']}** ({c['n']}): {', '.join(c['features'][:5])}")
    lines += ["", "## Top 15 stable OOS (stability≥0.35)", ""]
    for r in top_oos_stable[:15]:
        lines.append(
            f"- [{r['dataset']}] **{r['feature']}** → {r['target']}: "
            f"oos_ic_t={r.get('oos_rank_ic_t')}, stab={r.get('stability_ratio')}, score={r.get('discovery_score', 0):.2f}"
        )
    mpath.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(manifest["verdict"], indent=2, default=str))
    print(f"\nWrote {latest}\nWrote {mpath}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
