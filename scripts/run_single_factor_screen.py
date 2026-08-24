#!/usr/bin/env python3
"""Screen every fused-panel factor one-by-one — no ML, era holdouts, readable report.

Outputs:
  backtests/outputs/platform/single_factor_screen/latest.json
  backtests/outputs/platform/single_factor_screen/latest.md
"""

from __future__ import annotations

import json
import math
import warnings
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "backtests/outputs/platform/single_factor_screen"
FUSED = REPO / "data_lake/research_panels/cross_asset_fused/fused_20260610_v2/cross_asset_fused_primary_panel.parquet"
GLOBAL = REPO / "data_lake/research_panels/cross_asset_fused/fused_20260610_v2/global_assets_week_panel.parquet"

ERAS = (
    ("full", None, None),
    ("2018_2019", "2018-01-01", "2020-01-01"),
    ("2020_2023", "2020-01-01", "2024-01-01"),
    ("2024_oos", "2024-01-01", None),
)
COUNTRY_TARGETS = ("fwd_return_1w", "fwd_return_4w", "fwd_vol_4w")
GLOBAL_ASSETS = ("BIL", "BTC-USD", "ETH-USD", "EEM", "EFA", "GLD", "IWM", "SPY", "DBC")

FAMILY_RULES = (
    ("corpus_volume", lambda c: c in {"news_rows", "unique_urls", "news_days", "entity_count", "high_priority_urls", "high_confidence_count", "equity_count", "etf_count", "index_count"}),
    ("relevance_tone", lambda c: "relevance" in c or "tone" in c or "market_relevant" in c),
    ("taxonomy_shock", lambda c: "per_1k" in c and "crypto" not in c and "asset_" not in c and "event_" not in c),
    ("crypto_asset", lambda c: c.startswith("asset_")),
    ("crypto_event", lambda c: c.startswith("event_")),
    ("crypto_other", lambda c: "crypto" in c),
    ("vix", lambda c: c.startswith("vix_")),
    ("other", lambda c: True),
)


def factor_family(name: str) -> str:
    for fam, pred in FAMILY_RULES:
        if pred(name):
            return fam
    return "other"


def era_mask(week_end: pd.Series, start: str | None, end: str | None) -> pd.Series:
    m = pd.Series(True, index=week_end.index)
    if start:
        m &= week_end >= pd.Timestamp(start)
    if end:
        m &= week_end < pd.Timestamp(end)
    return m


def weekly_rank_ic(df: pd.DataFrame, x: str, y: str) -> tuple[float, float, int]:
    sub = df[["week_end", x, y]].dropna()
    if len(sub) < 80:
        return np.nan, np.nan, 0
    sub = sub.copy()
    sub["rx"] = sub.groupby("week_end", sort=False)[x].rank()
    sub["ry"] = sub.groupby("week_end", sort=False)[y].rank()
    ics = sub.groupby("week_end", sort=False).apply(
        lambda g: float(g["rx"].corr(g["ry"])) if len(g) >= 6 and g["rx"].std() > 0 else np.nan,
        include_groups=False,
    ).dropna()
    if len(ics) < 12:
        return np.nan, np.nan, int(len(ics))
    a = ics.to_numpy(dtype=float)
    mu = float(a.mean())
    sd = float(a.std(ddof=1))
    return mu, mu / (sd / math.sqrt(len(a)) + 1e-12), int(len(a))


def spearman_ts(df: pd.DataFrame, x: str, y: str) -> tuple[float, float, int]:
    sub = df[[x, y]].dropna()
    if len(sub) < 30:
        return np.nan, np.nan, int(len(sub))
    ic = float(sub[x].corr(sub[y], method="spearman"))
    return ic, ic * math.sqrt(len(sub)), int(len(sub))


def stability(is_t: float, oos_t: float) -> float | None:
    if not np.isfinite(is_t) or not np.isfinite(oos_t):
        return None
    return float(abs(oos_t) / max(abs(is_t), 0.5))


def screen_country_cross_section(fused: pd.DataFrame, factor: str) -> list[dict]:
    rows = []
    for era, start, end in ERAS:
        sub = fused.loc[era_mask(fused["week_end"], start, end)]
        for tgt in COUNTRY_TARGETS:
            if tgt not in sub.columns:
                continue
            mu, t, w = weekly_rank_ic(sub, factor, tgt)
            rows.append(
                {
                    "test": "country_xs_rank_ic",
                    "factor": factor,
                    "family": factor_family(factor),
                    "era": era,
                    "target": tgt,
                    "mean_ic": mu,
                    "tstat": t,
                    "weeks": w,
                }
            )
    return rows


def screen_asia_level(global_df: pd.DataFrame, factor: str) -> list[dict]:
    rows = []
    xcol = f"asia_{factor}"
    if xcol not in global_df.columns:
        return rows
    for era, start, end in ERAS:
        sub = global_df.loc[era_mask(global_df["week_end"], start, end)]
        for asset in GLOBAL_ASSETS:
            tgt = f"global_{asset}_fwd_return_1w"
            if tgt not in sub.columns:
                continue
            ic, t, n = spearman_ts(sub, xcol, tgt)
            rows.append(
                {
                    "test": "asia_level_spillover",
                    "factor": factor,
                    "family": factor_family(factor),
                    "era": era,
                    "target": f"{asset}_fwd_1w",
                    "spearman": ic,
                    "tstat": t,
                    "weeks": n,
                }
            )
    return rows


def screen_asia_dispersion(global_df: pd.DataFrame, factor: str) -> list[dict]:
    rows = []
    xcol = f"asia_disp_{factor}"
    if xcol not in global_df.columns:
        return rows
    for era, start, end in ERAS:
        sub = global_df.loc[era_mask(global_df["week_end"], start, end)]
        for asset in GLOBAL_ASSETS:
            tgt = f"global_{asset}_fwd_return_1w"
            if tgt not in sub.columns:
                continue
            ic, t, n = spearman_ts(sub, xcol, tgt)
            rows.append(
                {
                    "test": "asia_dispersion_spillover",
                    "factor": factor,
                    "family": factor_family(factor),
                    "era": era,
                    "target": f"{asset}_fwd_1w",
                    "spearman": ic,
                    "tstat": t,
                    "weeks": n,
                }
            )
    return rows


def summarize_factor(all_rows: pd.DataFrame, factor: str) -> dict:
    f = all_rows[all_rows.factor == factor]
    # Best country vol signal (full sample)
    vol = f[(f.test == "country_xs_rank_ic") & (f.target == "fwd_vol_4w") & (f.era == "full")]
    ret = f[(f.test == "country_xs_rank_ic") & (f.target == "fwd_return_4w") & (f.era == "full")]
    vol_oos = f[(f.test == "country_xs_rank_ic") & (f.target == "fwd_vol_4w") & (f.era == "2024_oos")]
    ret_oos = f[(f.test == "country_xs_rank_ic") & (f.target == "fwd_return_4w") & (f.era == "2024_oos")]
    vol_is = f[(f.test == "country_xs_rank_ic") & (f.target == "fwd_vol_4w") & (f.era == "2020_2023")]

    best_spill = (
        f[f.test == "asia_level_spillover"]
        .loc[lambda d: d.era == "full"]
        .assign(abs_t=lambda d: d.tstat.abs())
        .sort_values("abs_t", ascending=False)
        .head(1)
    )
    best_disp = (
        f[f.test == "asia_dispersion_spillover"]
        .loc[lambda d: d.era == "full"]
        .assign(abs_t=lambda d: d.tstat.abs())
        .sort_values("abs_t", ascending=False)
        .head(1)
    )

    def _t(frame: pd.DataFrame) -> float | None:
        if frame.empty:
            return None
        v = frame.iloc[0].get("tstat")
        return float(v) if pd.notna(v) else None

    vol_full = _t(vol)
    ret_full = _t(ret)
    vol_o = _t(vol_oos)
    ret_o = _t(ret_oos)
    vol_i = _t(vol_is)

    return {
        "factor": factor,
        "family": factor_family(factor),
        "vol_4w_full_t": vol_full,
        "ret_4w_full_t": ret_full,
        "vol_4w_2024_t": vol_o,
        "ret_4w_2024_t": ret_o,
        "vol_stability_is_to_oos": stability(vol_i or np.nan, vol_o or np.nan),
        "best_level_spillover": best_spill.iloc[0].to_dict() if len(best_spill) else None,
        "best_disp_spillover": best_disp.iloc[0].to_dict() if len(best_disp) else None,
        "vol_score": abs(vol_full or 0) * (1.0 if (vol_o or 0) > 1.5 else 0.5),
        "ret_score": abs(ret_o or 0) if abs(ret_o or 0) > abs(ret_full or 0) else abs(ret_full or 0),
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    fused = pd.read_parquet(FUSED)
    fused["week_end"] = pd.to_datetime(fused["week_end"])

    factors = [
        c
        for c in fused.columns
        if pd.api.types.is_numeric_dtype(fused[c])
        and fused[c].std(ddof=0) > 0
        and not c.startswith("fwd_")
        and not c.startswith("global_")
        and c not in {"index", "price", "return_1w", "return_4w", "vix_fwd_return_1w"}
    ]

    asia_level = fused.groupby("week_end", as_index=False)[factors].mean(numeric_only=True)
    asia_level = asia_level.rename(columns={c: f"asia_{c}" for c in factors})
    asia_disp = fused.groupby("week_end", as_index=False)[factors].std(numeric_only=True)
    asia_disp = asia_disp.rename(columns={c: f"asia_disp_{c}" for c in factors})

    g = pd.read_parquet(GLOBAL)
    g["week_end"] = pd.to_datetime(g["week_end"])
    global_df = g.merge(asia_level, on="week_end").merge(asia_disp, on="week_end")

    rows: list[dict] = []
    for i, fac in enumerate(factors):
        rows.extend(screen_country_cross_section(fused, fac))
        rows.extend(screen_asia_level(global_df, fac))
        rows.extend(screen_asia_dispersion(global_df, fac))
        if (i + 1) % 15 == 0:
            print(f"  screened {i+1}/{len(factors)} factors...")

    df = pd.DataFrame(rows)
    summaries = [summarize_factor(df, f) for f in factors]
    summ = pd.DataFrame(summaries)

    vol_rank = summ.sort_values("vol_score", ascending=False).head(20)
    ret_rank = summ.sort_values("ret_score", ascending=False).head(20)

    by_family = {}
    for fam, gdf in summ.groupby("family"):
        by_family[fam] = {
            "best_vol": gdf.sort_values("vol_score", ascending=False).head(3)[
                ["factor", "vol_4w_full_t", "vol_4w_2024_t", "vol_stability_is_to_oos"]
            ].to_dict(orient="records"),
            "best_ret": gdf.sort_values("ret_score", ascending=False).head(3)[
                ["factor", "ret_4w_full_t", "ret_4w_2024_t"]
            ].to_dict(orient="records"),
        }

    manifest = {
        "built_at_utc": datetime.now(UTC).isoformat(),
        "method": "single_factor_only_no_ml",
        "n_factors": len(factors),
        "n_tests": len(df),
        "eras": [e[0] for e in ERAS],
        "top_vol_factors": vol_rank.to_dict(orient="records"),
        "top_return_factors": ret_rank.to_dict(orient="records"),
        "by_family": by_family,
        "all_summaries": summ.sort_values("vol_score", ascending=False).to_dict(orient="records"),
    }

    latest = OUT / "latest.json"
    latest.write_text(json.dumps(manifest, indent=2, default=str) + "\n", encoding="utf-8")

    lines = [
        "# Single-factor screen (no ML)",
        f"- built: {manifest['built_at_utc']}",
        f"- factors: {len(factors)} | tests: {len(df)}",
        "",
        "## Top vol predictors (country cross-section, fwd_vol_4w)",
    ]
    for r in vol_rank.itertuples():
        lines.append(
            f"- **{r.factor}** [{r.family}]: full t={r.vol_4w_full_t:.2f}, 2024 t={r.vol_4w_2024_t:.2f}, "
            f"stability={r.vol_stability_is_to_oos}"
        )
    lines += ["", "## Top return predictors (country cross-section, fwd_return_4w)"]
    for r in ret_rank.itertuples():
        lines.append(
            f"- **{r.factor}** [{r.family}]: full t={r.ret_4w_full_t:.2f}, 2024 t={r.ret_4w_2024_t:.2f}"
        )
    lines += ["", "## By family (best vol in each bucket)"]
    for fam, block in by_family.items():
        lines.append(f"### {fam}")
        for b in block["best_vol"]:
            lines.append(f"- vol: {b['factor']} full_t={b['vol_4w_full_t']}, 2024_t={b['vol_4w_2024_t']}")
        lines.append("")

    (OUT / "latest.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"screened {len(factors)} factors, {len(df)} tests")
    print(f"wrote {latest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
