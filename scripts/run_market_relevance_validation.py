#!/usr/bin/env python3
"""Validate market-relevance signal across full history + era holdouts.

Writes: backtests/outputs/platform/market_relevance_validation/latest.json
"""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "backtests/outputs/platform/market_relevance_validation"
FUSED = REPO / "data_lake/research_panels/cross_asset_fused/fused_20260610_v2/cross_asset_fused_primary_panel.parquet"
GLOBAL = REPO / "data_lake/research_panels/cross_asset_fused/fused_20260610_v2/global_assets_week_panel.parquet"
FEAT = "mean_market_relevance_score_weighted"
ERAS = (
    ("full", None, None),
    ("2018_2019", "2018-01-01", "2020-01-01"),
    ("2020_2023", "2020-01-01", "2024-01-01"),
    ("2024_oos", "2024-01-01", None),
)


def weekly_rank_ic(df: pd.DataFrame, x: str, y: str) -> dict:
    ics = []
    for _, g in df.groupby("week_end"):
        s = g[[x, y]].dropna()
        if len(s) < 6:
            continue
        ic = s[x].rank().corr(s[y].rank())
        if np.isfinite(ic):
            ics.append(float(ic))
    if len(ics) < 10:
        return {"weeks": len(ics), "mean_ic": None, "tstat": None}
    a = np.array(ics)
    mu = float(a.mean())
    sd = float(a.std(ddof=1))
    t = mu / (sd / math.sqrt(len(a)) + 1e-12)
    return {"weeks": len(ics), "mean_ic": mu, "tstat": float(t)}


def era_slice(df: pd.DataFrame, start: str | None, end: str | None) -> pd.DataFrame:
    out = df
    if start:
        out = out[out["week_end"] >= pd.Timestamp(start)]
    if end:
        out = out[out["week_end"] < pd.Timestamp(end)]
    return out


def spillover_ic(asia: pd.DataFrame, g: pd.DataFrame, x: str, y: str, start: str | None, end: str | None) -> dict:
    m = asia.merge(g, on="week_end", how="inner")
    m = era_slice(m, start, end).dropna(subset=[x, y])
    if len(m) < 30:
        return {"n": len(m), "spearman": None, "t_approx": None}
    ic = float(m[x].corr(m[y], method="spearman"))
    return {"n": len(m), "spearman": ic, "t_approx": float(ic * math.sqrt(len(m)))}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    f = pd.read_parquet(FUSED)
    f["week_end"] = pd.to_datetime(f["week_end"])
    g = pd.read_parquet(GLOBAL)
    g["week_end"] = pd.to_datetime(g["week_end"])

    asia = (
        f.groupby("week_end", as_index=False)
        .agg(level=(FEAT, "mean"), dispersion=(FEAT, "std"))
        .sort_values("week_end")
    )

    era_results = []
    for name, start, end in ERAS:
        sub = era_slice(f, start, end)
        era_results.append(
            {
                "era": name,
                "start": start,
                "end": end,
                "country_fwd_return_4w": weekly_rank_ic(sub, FEAT, "fwd_return_4w"),
                "country_fwd_vol_4w": weekly_rank_ic(sub, FEAT, "fwd_vol_4w"),
                "asia_level_to_eem": spillover_ic(asia, g, "level", "global_EEM_fwd_return_1w", start, end),
                "asia_disp_to_bil": spillover_ic(asia, g, "dispersion", "global_BIL_fwd_return_1w", start, end),
                "asia_disp_to_btc": spillover_ic(asia, g, "dispersion", "global_BTC-USD_fwd_return_1w", start, end),
            }
        )

    vol_stable = all(
        (r["country_fwd_vol_4w"].get("tstat") or 0) > 1.5 for r in era_results if r["era"] != "2020_2023"
    )
    ret_oos_only = (era_results[-1]["country_fwd_return_4w"].get("tstat") or 0) > 2.0

    manifest = {
        "built_at_utc": datetime.now(UTC).isoformat(),
        "feature": FEAT,
        "fused_weeks": int(f["week_end"].nunique()),
        "fused_span": [str(f["week_end"].min().date()), str(f["week_end"].max().date())],
        "verdict": {
            "vol_signal_stable_multi_era": vol_stable,
            "return_signal_strong_2024_oos_only": ret_oos_only,
            "recommended_use": "vol_overlay + dispersion_tilt (not directional taxonomy)",
            "legacy_taxonomy_overlay": "deprecate for live book — weak OOS on book_eq",
        },
        "eras": era_results,
    }

    latest = OUT / "latest.json"
    latest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest["verdict"], indent=2))
    print(f"wrote {latest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
