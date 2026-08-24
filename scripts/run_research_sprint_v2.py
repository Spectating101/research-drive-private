#!/usr/bin/env python3
"""Research sprint v2: horse race vs EPU/GPR/VIX + Asia crypto news spillovers."""

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
CRYPTO_PANEL = REPO / "data_lake/research_panels/cross_asset_fused/fused_20260610_v2/country_week_crypto_news_panel.parquet"
GLOBAL = REPO / "data_lake/research_panels/cross_asset_fused/fused_20260610_v2/global_assets_week_panel.parquet"
MACRO_ROOT = REPO / "data_lake/public_macro_market_baseline/2026-05-26/raw"
OUT = REPO / "backtests/outputs/research_sprint_v2"

EPU_COUNTRY = {
    "AUS": "Australia",
    "CHN": "China",
    "IND": "India",
    "JPN": "Japan",
    "KOR": "Korea",
    "MYS": "Malaysia",
    "PHL": "Philippines",
    "SGP": "Singapore",
    "THA": "Thailand",
    "TWN": "Taiwan",
    "VNM": "Vietnam",
    "HKG": "Hong Kong",
    "IDN": "Indonesia",
}
GPR_COL = {
    "AUS": "GPRC_AUS",
    "CHN": "GPRC_CHN",
    "HKG": "GPRC_HKG",
    "IDN": "GPRC_IDN",
    "IND": "GPRC_IND",
    "JPN": "GPRC_JPN",
    "KOR": "GPRC_KOR",
    "MYS": "GPRC_MYS",
    "PHL": "GPRC_PHL",
    "SGP": "GPRC_SGP",
    "THA": "GPRC_THA",
    "TWN": "GPRC_TWN",
    "VNM": "GPRC_VNM",
}
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
CRYPTO_EVENTS = [
    "event_regulation_enforcement",
    "event_security_exploit",
    "event_market_stress",
    "event_institutional_adoption",
    "event_exchange_market_structure",
]
TARGETS = ["fwd_return_1w", "fwd_return_4w", "fwd_vol_4w"]


@dataclass
class ModelFit:
    name: str
    target: str
    n: int
    k: int
    r2_within: float
    rmse: float


def zscore(s: pd.Series) -> pd.Series:
    s = pd.to_numeric(s, errors="coerce")
    sd = s.std(ddof=0)
    if not np.isfinite(sd) or sd == 0:
        return s * 0.0
    return (s - s.mean()) / sd


def load_epu_monthly() -> pd.DataFrame:
    path = MACRO_ROOT / "policy_uncertainty/All_Country_Data.xlsx"
    raw = pd.read_excel(path)
    raw = raw.dropna(subset=["Year", "Month"])
    raw["month"] = pd.to_datetime(
        raw["Year"].astype(int).astype(str) + "-" + raw["Month"].astype(int).astype(str) + "-01"
    )
    rows = []
    for iso, col in EPU_COUNTRY.items():
        if col not in raw.columns:
            continue
        sub = raw[["month", col]].rename(columns={col: "epu"}).dropna()
        sub["country_iso3"] = iso
        rows.append(sub)
    return pd.concat(rows, ignore_index=True)


def load_gpr_monthly() -> pd.DataFrame:
    path = MACRO_ROOT / "geopolitical_risk/data_gpr_export.xls"
    raw = pd.read_excel(path)
    raw = raw[raw["month"].notna()].copy()
    raw["month"] = pd.to_datetime(raw["month"])
    rows = []
    for iso, col in GPR_COL.items():
        if col not in raw.columns:
            continue
        sub = raw[["month", col]].rename(columns={col: "gpr"}).dropna()
        sub["country_iso3"] = iso
        rows.append(sub)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def attach_macro_baselines(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["week_end"] = pd.to_datetime(out["week_end"])
    out["month"] = out["week_end"].dt.to_period("M").dt.to_timestamp()

    epu = load_epu_monthly()
    gpr_country = load_gpr_monthly()
    gpr_country = gpr_country[gpr_country["country_iso3"].notna()] if "country_iso3" in gpr_country.columns else gpr_country

    out = out.merge(epu, on=["country_iso3", "month"], how="left")
    out = out.merge(
        gpr_country.rename(columns={"gpr": "gpr_country"}),
        on=["country_iso3", "month"],
        how="left",
    )

    gpr_global = pd.read_excel(MACRO_ROOT / "geopolitical_risk/data_gpr_export.xls")
    gpr_global = gpr_global[gpr_global["month"].notna()].copy()
    gpr_global["month"] = pd.to_datetime(gpr_global["month"])
    gpr_global = gpr_global[["month", "GPR"]].rename(columns={"GPR": "gpr_global"})
    out = out.merge(gpr_global, on="month", how="left")

    for c in ["epu", "gpr_country", "gpr_global", "vix_close", "mean_tone_weighted"]:
        if c in out.columns:
            out[f"z_{c}"] = out.groupby("country_iso3")[c].transform(lambda s: zscore(s.fillna(s.median())))
    out["z_log_news_rows"] = out.groupby("country_iso3")["news_rows"].transform(
        lambda s: zscore(np.log1p(s.fillna(0)))
    )
    for shock in SHOCKS:
        col = f"{shock}_per_1k_rows"
        if col in out.columns:
            out[f"z_{shock}"] = out.groupby("country_iso3")[col].transform(lambda s: zscore(s.fillna(0)))
    return out


def within_matrix(df: pd.DataFrame, y_col: str, x_cols: list[str]) -> tuple[np.ndarray, np.ndarray, pd.DataFrame]:
    sub = df[["country_iso3", y_col, *x_cols]].replace([np.inf, -np.inf], np.nan).dropna()
    sub = sub.copy()
    sub[y_col] = sub.groupby("country_iso3")[y_col].transform(lambda s: s - s.mean())
    for col in x_cols:
        sub[col] = sub.groupby("country_iso3")[col].transform(lambda s: s - s.fillna(0).mean())
    y = sub[y_col].to_numpy(dtype=float)
    x = sub[x_cols].to_numpy(dtype=float)
    return y, x, sub


def fit_within(y: np.ndarray, x: np.ndarray) -> tuple[np.ndarray, float, float]:
    if x.ndim == 1:
        x = x.reshape(-1, 1)
    x1 = np.column_stack([np.ones(len(y)), x])
    beta, *_ = np.linalg.lstsq(x1, y, rcond=None)
    resid = y - x1 @ beta
    rmse = float(np.sqrt(np.mean(resid**2)))
    ss_res = float(np.sum(resid**2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")
    return beta, r2, rmse


def horse_race(df: pd.DataFrame) -> dict:
    baseline = ["z_epu", "z_gpr_country", "z_gpr_global", "z_vix_close", "z_mean_tone_weighted", "z_log_news_rows"]
    baseline = [c for c in baseline if c in df.columns]
    shocks = [f"z_{s}" for s in SHOCKS if f"z_{s}" in df.columns]

    fits = []
    coef_rows = []
    for target in TARGETS:
        if target not in df.columns:
            continue
        for name, cols in [
            ("baseline_only", baseline),
            ("taxonomy_only", shocks),
            ("baseline_plus_taxonomy", baseline + shocks),
        ]:
            if not cols:
                continue
            y, x, sub = within_matrix(df, target, cols)
            if len(y) < 100:
                continue
            beta, r2, rmse = fit_within(y, x)
            fits.append(ModelFit(name=name, target=target, n=len(y), k=len(cols), r2_within=r2, rmse=rmse))

        y, xb, _ = within_matrix(df, target, baseline)
        y, xf, _ = within_matrix(df, target, baseline + shocks)
        if len(y) >= 100 and shocks:
            _, r2_b, _ = fit_within(y, xb)
            _, r2_f, _ = fit_within(y, xf)
            delta_r2 = r2_f - r2_b
            fits.append(
                ModelFit(
                    name="delta_r2_taxonomy_given_baseline",
                    target=target,
                    n=len(y),
                    k=len(shocks),
                    r2_within=delta_r2,
                    rmse=float("nan"),
                )
            )

        # taxonomy coefs conditional on baseline
        cols = baseline + shocks
        y, x, _ = within_matrix(df, target, cols)
        if len(y) < 100:
            continue
        beta, _, _ = fit_within(y, x)
        for i, col in enumerate(cols):
            coef_rows.append(
                {
                    "target": target,
                    "feature": col,
                    "coef_within": float(beta[i + 1]),
                    "is_taxonomy": col in shocks,
                }
            )

    return {
        "model_fits": [asdict(f) for f in fits],
        "coefficients": coef_rows,
    }


def governance_interaction(df: pd.DataFrame) -> list[dict]:
    """Governance shock × country institutional proxy (median vol as crude fragility proxy)."""
    out = []
    if "governance_corruption_per_1k_rows" not in df.columns:
        return out
    tmp = df.copy()
    country_fragility = tmp.groupby("country_iso3")["fwd_vol_4w"].transform("median")
    tmp["fragility"] = country_fragility
    tmp["z_gov"] = tmp.groupby("country_iso3")["governance_corruption_per_1k_rows"].transform(lambda s: zscore(s))
    tmp["z_frag"] = tmp.groupby("country_iso3")["fragility"].transform(lambda s: zscore(s))
    tmp["gov_x_frag"] = tmp["z_gov"] * tmp["z_frag"]
    for target in ["fwd_return_4w", "fwd_vol_4w"]:
        y, x, _ = within_matrix(tmp, target, ["z_gov", "z_frag", "gov_x_frag"])
        if len(y) < 100:
            continue
        beta, r2, _ = fit_within(y, x)
        out.append(
            {
                "target": target,
                "coef_gov": float(beta[1]),
                "coef_fragility": float(beta[2]),
                "coef_interaction": float(beta[3]),
                "r2_within": float(r2),
                "n": int(len(y)),
            }
        )
    return out


def crypto_spillover(crypto: pd.DataFrame, global_df: pd.DataFrame) -> dict:
    crypto = crypto.copy()
    crypto["week_end"] = pd.to_datetime(crypto["week_end"])
    global_df = global_df.copy()
    global_df["week_end"] = pd.to_datetime(global_df["week_end"])

    # Asia aggregate + top-country slices
    agg_cols = [c for c in crypto.columns if c.endswith("_per_1k_crypto_rows")]
    agg_cols += [c for c in crypto.columns if c.endswith("_rows") and not c.endswith("_per_1k_crypto_rows")]
    asia_week = crypto.groupby("week_end", as_index=False)[agg_cols].sum()
    for iso in ["CHN", "KOR", "SGP", "HKG", "IND"]:
        sub = crypto[crypto["country_iso3"] == iso].groupby("week_end", as_index=False)[agg_cols].sum()
        sub = sub.add_suffix(f"_{iso}").rename(columns={f"week_end_{iso}": "week_end"})
        asia_week = asia_week.merge(sub, on="week_end", how="left")

    g = global_df.copy()
    g["btc_abs_fwd_1w"] = g["global_BTC-USD_fwd_return_1w"].abs()
    g["eth_abs_fwd_1w"] = g["global_ETH-USD_fwd_return_1w"].abs()
    g["btc_fwd_vol_4w"] = g["global_BTC-USD_return_1w"].rolling(4).std().shift(-4)
    g["eth_fwd_vol_4w"] = g["global_ETH-USD_return_1w"].rolling(4).std().shift(-4)

    vix = pd.read_parquet(FUSED)[["week_end", "vix_fwd_return_1w"]].drop_duplicates()
    vix["week_end"] = pd.to_datetime(vix["week_end"])
    g = g.merge(vix, on="week_end", how="left")
    merged = asia_week.merge(g, on="week_end", how="inner")
    controls = [c for c in ["global_SPY_fwd_return_1w", "vix_fwd_return_1w"] if c in merged.columns]

    # zscore features on full sample
    for event in CRYPTO_EVENTS:
        for suffix in ["", "_CHN", "_KOR", "_SGP"]:
            col = f"{event}_per_1k_crypto_rows{suffix}"
            if col in merged.columns:
                merged[f"z_{col}"] = zscore(merged[col].fillna(0))
    for c in controls:
        if c in merged.columns:
            merged[f"z_{c}"] = zscore(merged[c].fillna(0))

    regressions = []
    events = []
    for event in CRYPTO_EVENTS:
        base_col = f"{event}_per_1k_crypto_rows"
        zcol = f"z_{base_col}"
        if zcol not in merged.columns:
            continue
        for target in [
            "global_BTC-USD_fwd_return_1w",
            "global_ETH-USD_fwd_return_1w",
            "btc_abs_fwd_1w",
            "eth_abs_fwd_1w",
            "btc_fwd_vol_4w",
            "eth_fwd_vol_4w",
        ]:
            if target not in merged.columns:
                continue
            cols = [zcol] + [f"z_{c}" for c in controls if f"z_{c}" in merged.columns]
            sub = merged[[target, *cols]].replace([np.inf, -np.inf], np.nan).dropna()
            if len(sub) < 80:
                continue
            y = sub[target].to_numpy(dtype=float)
            x = sub[cols].to_numpy(dtype=float)
            beta, r2, rmse = fit_within(y, x)  # no FE at global weekly level
            regressions.append(
                {
                    "event": event,
                    "target": target,
                    "coef_event": float(beta[1]),
                    "r2": float(r2),
                    "n": int(len(sub)),
                    "controls": controls,
                }
            )

        # event study top decile
        sub = merged[[base_col, "global_BTC-USD_fwd_return_1w", "global_ETH-USD_fwd_return_1w", "btc_abs_fwd_1w"]].dropna()
        if len(sub) < 80:
            continue
        thr = sub[base_col].quantile(0.9)
        hi, lo = sub[sub[base_col] >= thr], sub[sub[base_col] < thr]
        events.append(
            {
                "event": event,
                "hi_n": int(len(hi)),
                "btc_fwd_1w_hi": float(hi["global_BTC-USD_fwd_return_1w"].mean()),
                "btc_fwd_1w_lo": float(lo["global_BTC-USD_fwd_return_1w"].mean()),
                "btc_diff": float(hi["global_BTC-USD_fwd_return_1w"].mean() - lo["global_BTC-USD_fwd_return_1w"].mean()),
                "btc_abs_hi": float(hi["btc_abs_fwd_1w"].mean()),
                "btc_abs_lo": float(lo["btc_abs_fwd_1w"].mean()),
            }
        )

    # country-specific regulation → BTC
    country_regs = []
    for iso in ["CHN", "KOR", "SGP", "HKG", "IND"]:
        col = f"event_regulation_enforcement_per_1k_crypto_rows_{iso}"
        if col not in merged.columns:
            continue
        sub = merged[[col, "global_BTC-USD_fwd_return_1w", "global_SPY_fwd_return_1w"]].dropna()
        if len(sub) < 80:
            continue
        country_regs.append(
            {
                "country": iso,
                "corr_reg_btc": float(sub[col].corr(sub["global_BTC-USD_fwd_return_1w"])),
                "corr_reg_spy": float(sub[col].corr(sub["global_SPY_fwd_return_1w"])),
                "n": int(len(sub)),
            }
        )

    return {
        "weeks": int(len(merged)),
        "regressions": regressions,
        "event_studies_top_decile": events,
        "country_regulation_correlations": country_regs,
    }


def main() -> int:
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_dir = OUT / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    fused = pd.read_parquet(FUSED)
    fused = attach_macro_baselines(fused)

    results = {
        "built_at_utc": datetime.now(UTC).isoformat(),
        "run_id": run_id,
        "horse_race": horse_race(fused),
        "governance_interaction": governance_interaction(fused),
        "crypto": crypto_spillover(pd.read_parquet(CRYPTO_PANEL), pd.read_parquet(GLOBAL)),
    }

    pd.DataFrame(results["horse_race"]["model_fits"]).to_csv(out_dir / "horse_race_model_fits.csv", index=False)
    pd.DataFrame(results["horse_race"]["coefficients"]).to_csv(out_dir / "horse_race_coefficients.csv", index=False)
    pd.DataFrame(results["crypto"]["regressions"]).to_csv(out_dir / "crypto_regressions.csv", index=False)
    pd.DataFrame(results["crypto"]["event_studies_top_decile"]).to_csv(out_dir / "crypto_event_studies.csv", index=False)

    (out_dir / "research_sprint_v2.json").write_text(json.dumps(results, indent=2), encoding="utf-8")

    highlights = []
    for fit in results["horse_race"]["model_fits"]:
        if fit["name"] == "delta_r2_taxonomy_given_baseline":
            highlights.append(f"ΔR² taxonomy | {fit['target']}: {fit['r2_within']:+.4f}")
    for row in results["crypto"]["event_studies_top_decile"]:
        if row["event"] in {"event_security_exploit", "event_regulation_enforcement", "event_market_stress"}:
            highlights.append(
                f"Crypto {row['event']}: BTC 1w hi-lo diff {row['btc_diff']:+.4f}, |ret| hi {row['btc_abs_hi']:.4f} lo {row['btc_abs_lo']:.4f}"
            )
    (out_dir / "highlights.txt").write_text("\n".join(highlights), encoding="utf-8")
    print(json.dumps({"run_id": run_id, "out_dir": str(out_dir), "highlights": highlights}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
