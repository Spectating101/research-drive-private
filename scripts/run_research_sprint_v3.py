#!/usr/bin/env python3
"""Research sprint v3: crypto deep-dive + governance×institutions + horse-race extras."""

from __future__ import annotations

import io
import json
import math
import zipfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "backtests/outputs/research_sprint_v3"
FUSED = REPO / "data_lake/research_panels/cross_asset_fused/fused_20260610_v2/cross_asset_fused_primary_panel.parquet"
CRYPTO = REPO / "data_lake/research_panels/cross_asset_fused/fused_20260610_v2/country_week_crypto_news_panel.parquet"
GLOBAL = REPO / "data_lake/research_panels/cross_asset_fused/fused_20260610_v2/global_assets_week_panel.parquet"
MACRO = REPO / "data_lake/public_macro_market_baseline/2026-05-26/raw"
PROCESSED = REPO / "data_lake/news_shock_taxonomy/processed"

WB_ISO = {
    "AUS": "AUS",
    "CHN": "CHN",
    "HKG": "HKG",
    "IDN": "IDN",
    "IND": "IND",
    "JPN": "JPN",
    "KOR": "KOR",
    "MYS": "MYS",
    "PHL": "PHL",
    "SGP": "SGP",
    "THA": "THA",
    "TWN": "TWN",
    "VNM": "VNM",
}
CRYPTO_EVENTS = [
    "event_regulation_enforcement",
    "event_security_exploit",
    "event_market_stress",
    "event_institutional_adoption",
]
COUNTRY_FOCUS = ["IND", "HKG", "CHN", "KOR", "SGP"]


@dataclass
class RegOut:
    spec: str
    event: str
    target: str
    coef: float
    se: float
    tstat: float
    pval: float
    n: int
    r2: float


def zscore(s: pd.Series) -> pd.Series:
    s = pd.to_numeric(s, errors="coerce")
    sd = s.std(ddof=0)
    if not np.isfinite(sd) or sd == 0:
        return s * 0.0
    return (s - s.mean()) / sd


def ols_hc1(y: np.ndarray, x: np.ndarray) -> tuple[np.ndarray, np.ndarray, float]:
    """OLS with HC1 robust standard errors."""
    if x.ndim == 1:
        x = x.reshape(-1, 1)
    x1 = np.column_stack([np.ones(len(y)), x])
    beta, *_ = np.linalg.lstsq(x1, y, rcond=None)
    resid = y - x1 @ beta
    n, k = x1.shape
    xtx_inv = np.linalg.inv(x1.T @ x1)
    meat = x1.T @ (x1 * (resid**2)[:, None])
    scale = n / max(n - k, 1)
    vcov = xtx_inv @ meat @ xtx_inv * scale
    se = np.sqrt(np.clip(np.diag(vcov), 0, np.inf))
    ss_res = float(resid @ resid)
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")
    return beta, se, r2


def reg_row(spec: str, event: str, target: str, y: np.ndarray, x: np.ndarray) -> RegOut:
    beta, se, r2 = ols_hc1(y, x)
    tstat = float(beta[1] / se[1]) if se[1] > 0 else float("nan")
    pval = float(2 * (1 - 0.5 * (1 + math.erf(abs(tstat) / math.sqrt(2))))) if np.isfinite(tstat) else float("nan")
    return RegOut(spec, event, target, float(beta[1]), float(se[1]), tstat, pval, int(len(y)), float(r2))


def benjamini_hochberg(pvals: list[float]) -> list[float]:
    m = len(pvals)
    if m == 0:
        return []
    order = np.argsort(pvals)
    adj = [1.0] * m
    prev = 1.0
    for rank in range(m - 1, -1, -1):
        i = order[rank]
        q = pvals[i] * m / (rank + 1)
        prev = min(prev, q)
        adj[i] = min(prev, 1.0)
    return adj


def load_wb_indicator(code: str) -> pd.DataFrame:
    path = MACRO / f"world_bank/{code}.zip"
    with zipfile.ZipFile(path) as zf:
        name = [n for n in zf.namelist() if n.startswith("API_")][0]
        raw = pd.read_csv(io.BytesIO(zf.read(name)), skiprows=4)
    year_cols = [c for c in raw.columns if str(c).isdigit()]
    long = raw.melt(id_vars=["Country Code"], value_vars=year_cols, var_name="year", value_name="value")
    long["year"] = long["year"].astype(int)
    long["value"] = pd.to_numeric(long["value"], errors="coerce")
    long = long.dropna(subset=["value"])
    col = code.lower().replace(".", "_")
    return long.rename(columns={"Country Code": "wb_code", "value": col})


def build_weekly_crypto_global() -> pd.DataFrame:
    crypto = pd.read_parquet(CRYPTO)
    crypto["week_end"] = pd.to_datetime(crypto["week_end"])
    g = pd.read_parquet(GLOBAL).copy()
    g["week_end"] = pd.to_datetime(g["week_end"])
    vix = pd.read_parquet(FUSED)[["week_end", "vix_fwd_return_1w", "vix_close"]].drop_duplicates()
    vix["week_end"] = pd.to_datetime(vix["week_end"])

    row_cols = [c for c in crypto.columns if c.endswith("_rows") and not c.endswith("_per_1k_crypto_rows")]
    per1k_cols = [c for c in crypto.columns if c.endswith("_per_1k_crypto_rows")]
    asia = crypto.groupby("week_end", as_index=False)[row_cols + per1k_cols + ["crypto_news_days"]].sum()

    for iso in COUNTRY_FOCUS:
        sub = crypto[crypto["country_iso3"] == iso].groupby("week_end", as_index=False)[per1k_cols].sum()
        sub = sub.rename(columns={c: f"{c}_{iso}" for c in per1k_cols})
        asia = asia.merge(sub, on="week_end", how="left")

    merged = asia.merge(g, on="week_end", how="inner").merge(vix, on="week_end", how="left")
    merged = merged.sort_values("week_end")
    for asset in ["BTC-USD", "ETH-USD"]:
        rcol = f"global_{asset}_return_1w"
        merged[f"z_mom_{asset}"] = zscore(merged[rcol].rolling(4).sum().shift(1))
        merged[f"z_rev_{asset}"] = zscore(-merged[rcol].rolling(1).sum().shift(1))
    merged["z_spy"] = zscore(merged["global_SPY_fwd_return_1w"])
    merged["z_vix_chg"] = zscore(merged["vix_fwd_return_1w"])
    merged["z_vix_level"] = zscore(merged["vix_close"])
    return merged


def crypto_regressions(df: pd.DataFrame) -> list[dict]:
    rows: list[RegOut] = []
    targets = {
        "btc_ret_1w": "global_BTC-USD_fwd_return_1w",
        "eth_ret_1w": "global_ETH-USD_fwd_return_1w",
        "btc_abs_1w": None,
    }
    df = df.copy()
    df["btc_abs_1w"] = df["global_BTC-USD_fwd_return_1w"].abs()

    for event in CRYPTO_EVENTS:
        for scope, col in [
            ("asia_total", f"{event}_per_1k_crypto_rows"),
            *[(f"country_{iso}", f"{event}_per_1k_crypto_rows_{iso}") for iso in COUNTRY_FOCUS],
        ]:
            if col not in df.columns:
                continue
            zev = f"z_{col}"
            df[zev] = zscore(df[col].fillna(0))
            controls_full = [zev, "z_mom_BTC-USD", "z_mom_ETH-USD", "z_spy", "z_vix_chg"]
            controls_base = [zev, "z_spy", "z_vix_chg"]
            for tgt_name, tgt_col in targets.items():
                tgt_col = tgt_col or tgt_name
                for spec_name, cols in [("full_momentum", controls_full), ("base", controls_base)]:
                    sub = df[[tgt_col, *cols]].replace([np.inf, -np.inf], np.nan).dropna()
                    if len(sub) < 100:
                        continue
                    y = sub[tgt_col].to_numpy(float)
                    x = sub[cols].to_numpy(float)
                    rows.append(reg_row(f"{scope}|{spec_name}", event, tgt_name, y, x))

    # lead-lag Asia regulation -> BTC
    base = "event_regulation_enforcement_per_1k_crypto_rows"
    if base in df.columns:
        for lag in [0, 1, 2]:
            col = f"lag{lag}_{base}"
            df[col] = df[base].shift(lag)
            zcol = f"z_{col}"
            df[zcol] = zscore(df[col].fillna(0))
            sub = df[["global_BTC-USD_fwd_return_1w", zcol, "z_mom_BTC-USD", "z_spy", "z_vix_chg"]].dropna()
            if len(sub) < 100:
                continue
            y = sub["global_BTC-USD_fwd_return_1w"].to_numpy(float)
            x = sub[[zcol, "z_mom_BTC-USD", "z_spy", "z_vix_chg"]].to_numpy(float)
            rows.append(reg_row(f"leadlag_lag{lag}", "event_regulation_enforcement", "btc_ret_1w", y, x))

    # subsample post-2022
    post = df[df["week_end"] >= "2022-01-01"]
    col = "event_security_exploit_per_1k_crypto_rows"
    if col in post.columns:
        zev = zscore(post[col].fillna(0))
        sub = post[["global_BTC-USD_fwd_return_1w", "z_mom_BTC-USD", "z_spy", "z_vix_chg"]].copy()
        sub["z_event"] = zev.values
        sub = sub.dropna()
        if len(sub) >= 80:
            rows.append(
                reg_row(
                    "post2022_asia",
                    "event_security_exploit",
                    "btc_ret_1w",
                    sub["global_BTC-USD_fwd_return_1w"].to_numpy(float),
                    sub[["z_event", "z_mom_BTC-USD", "z_spy", "z_vix_chg"]].to_numpy(float),
                )
            )

    out = [asdict(r) for r in rows]
    pvals = [r["pval"] for r in out if np.isfinite(r["pval"])]
    if pvals:
        adj = benjamini_hochberg(pvals)
        j = 0
        for r in out:
            if np.isfinite(r["pval"]):
                r["pval_bh"] = adj[j]
                j += 1
    return out


def event_catalog(df: pd.DataFrame, top_n: int = 15) -> list[dict]:
    rows = []
    for event in ["event_regulation_enforcement", "event_security_exploit"]:
        col = f"{event}_per_1k_crypto_rows"
        if col not in df.columns:
            continue
        sub = df[["week_end", col, "global_BTC-USD_fwd_return_1w", "global_ETH-USD_fwd_return_1w", "crypto_news_days"]].dropna()
        sub = sub.nlargest(top_n, col)
        for _, r in sub.iterrows():
            rows.append(
                {
                    "event": event,
                    "week_end": str(r["week_end"].date()),
                    "intensity": float(r[col]),
                    "btc_fwd_1w": float(r["global_BTC-USD_fwd_return_1w"]),
                    "eth_fwd_1w": float(r["global_ETH-USD_fwd_return_1w"]),
                    "crypto_news_days": float(r["crypto_news_days"]),
                }
            )
    return rows


def sample_articles(limit: int = 12) -> list[dict]:
    """Pull exemplar URLs from high-priority samples."""
    patterns = {
        "regulation": ["regulation", "regulator", "ban", "enforcement", "sec "],
        "exploit": ["hack", "exploit", "breach", "stolen", "attack"],
    }
    found: list[dict] = []
    for path in sorted(PROCESSED.glob("*/sample_high_priority.csv"), reverse=True):
        try:
            df = pd.read_csv(path, usecols=["date", "country_iso3", "canonical_url", "shock_hints"], nrows=8000)
        except Exception:
            continue
        text = (
            df["canonical_url"].astype(str)
            + " "
            + df.get("shock_hints", pd.Series("", index=df.index)).astype(str)
        ).str.lower()
        for kind, keys in patterns.items():
            mask = False
            for k in keys:
                mask = mask | text.str.contains(k, na=False)
            sub = df[mask & text.str.contains("crypto|bitcoin|ethereum|binance|defi|nft|token", na=False)]
            for _, r in sub.head(2).iterrows():
                found.append(
                    {
                        "kind": kind,
                        "date": str(r["date"]),
                        "country": str(r["country_iso3"]),
                        "url": str(r["canonical_url"]),
                    }
                )
        if len(found) >= limit:
            break
    return found[:limit]


def governance_institutions(fused: pd.DataFrame) -> list[dict]:
    rl = load_wb_indicator("RL.EST")
    cc = load_wb_indicator("CC.EST")
    inst = rl.merge(cc, on=["wb_code", "year"], how="outer")
    rl_col = "rl_est" if "rl_est" in inst.columns else "rl.est"
    cc_col = "cc_est" if "cc_est" in inst.columns else "cc.est"
    inst["inst_quality"] = inst[[rl_col, cc_col]].mean(axis=1)

    df = fused.copy()
    df["week_end"] = pd.to_datetime(df["week_end"])
    df["year"] = df["week_end"].dt.year
    df["wb_code"] = df["country_iso3"].map(WB_ISO)
    df = df.merge(inst, on=["wb_code", "year"], how="left")
    df["inst_quality"] = df.groupby("country_iso3")["inst_quality"].ffill()
    df["low_inst"] = (df["inst_quality"] < df["inst_quality"].median()).astype(float)
    df["z_gov"] = df.groupby("country_iso3")["governance_corruption_per_1k_rows"].transform(lambda s: zscore(s.fillna(0)))
    df["gov_x_lowinst"] = df["z_gov"] * df["low_inst"]

    rows = []
    for target in ["fwd_return_4w", "fwd_vol_4w"]:
        sub = df[["country_iso3", target, "z_gov", "low_inst", "gov_x_lowinst"]].dropna()
        if len(sub) < 200:
            continue
        # country FE via demean
        for col in [target, "z_gov", "gov_x_lowinst"]:
            sub[col] = sub.groupby("country_iso3")[col].transform(lambda s: s - s.mean())
        y = sub[target].to_numpy(float)
        x = sub[["z_gov", "gov_x_lowinst"]].to_numpy(float)
        beta, se, r2 = ols_hc1(y, x)
        rows.append(
            {
                "target": target,
                "coef_gov": float(beta[1]),
                "se_gov": float(se[1]),
                "coef_gov_x_low_inst": float(beta[2]),
                "se_interaction": float(se[2]),
                "t_interaction": float(beta[2] / se[2]) if se[2] > 0 else float("nan"),
                "r2": float(r2),
                "n": int(len(sub)),
            }
        )

    # between-country: avg governance shock vs avg return by country, moderated by inst
    cross = (
        df.groupby("country_iso3", as_index=False)
        .agg(
            avg_gov=("governance_corruption_per_1k_rows", "mean"),
            avg_ret_4w=("fwd_return_4w", "mean"),
            avg_vol_4w=("fwd_vol_4w", "mean"),
            inst_quality=("inst_quality", "last"),
        )
        .dropna()
    )
    if len(cross) >= 8:
        cross["z_gov"] = zscore(cross["avg_gov"])
        cross["z_inst"] = zscore(cross["inst_quality"])
        cross["inter"] = cross["z_gov"] * cross["z_inst"]
        y = cross["avg_ret_4w"].to_numpy(float)
        x = cross[["z_gov", "z_inst", "inter"]].to_numpy(float)
        beta, se, r2 = ols_hc1(y, x)
        rows.append(
            {
                "target": "cross_country_avg_return_4w",
                "coef_gov": float(beta[1]),
                "se_gov": float(se[1]),
                "coef_gov_x_low_inst": float(beta[3]),
                "se_interaction": float(se[3]),
                "t_interaction": float(beta[3] / se[3]) if se[3] > 0 else float("nan"),
                "r2": float(r2),
                "n": int(len(cross)),
            }
        )
    return rows


def main() -> int:
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_dir = OUT / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    weekly = build_weekly_crypto_global()
    fused = pd.read_parquet(FUSED)

    results = {
        "built_at_utc": datetime.now(UTC).isoformat(),
        "run_id": run_id,
        "crypto_regressions": crypto_regressions(weekly),
        "crypto_event_catalog": event_catalog(weekly),
        "sample_articles": sample_articles(),
        "governance_institutions": governance_institutions(fused),
    }

    pd.DataFrame(results["crypto_regressions"]).to_csv(out_dir / "crypto_regressions_v3.csv", index=False)
    pd.DataFrame(results["crypto_event_catalog"]).to_csv(out_dir / "crypto_event_catalog.csv", index=False)
    pd.DataFrame(results["sample_articles"]).to_csv(out_dir / "sample_articles.csv", index=False)
    pd.DataFrame(results["governance_institutions"]).to_csv(out_dir / "governance_institutions.csv", index=False)
    (out_dir / "research_sprint_v3.json").write_text(json.dumps(results, indent=2), encoding="utf-8")

    # highlights
    hl = []
    for r in results["crypto_regressions"]:
        if r["spec"].startswith("asia_total|full_momentum") and r["pval"] < 0.1:
            hl.append(f"{r['event']} -> {r['target']}: coef={r['coef']:+.4f} t={r['tstat']:+.2f} p={r['pval']:.3f}")
    for r in results["crypto_regressions"]:
        if r["spec"].startswith("country_") and "full_momentum" in r["spec"] and r["pval"] < 0.05:
            hl.append(f"{r['spec']} {r['event']}: coef={r['coef']:+.4f} p={r['pval']:.3f}")
    for g in results["governance_institutions"]:
        if "t_interaction" in g:
            hl.append(f"gov×inst {g['target']}: interaction t={g.get('t_interaction', float('nan')):+.2f}")
    (out_dir / "highlights.txt").write_text("\n".join(hl), encoding="utf-8")
    print(json.dumps({"run_id": run_id, "out_dir": str(out_dir), "highlights": hl}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
