#!/usr/bin/env python3
"""Lean blind discovery — focused emergent signals, compact JSON output."""

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
OUT = REPO / "backtests/outputs/platform/deep_research"
FUSED = REPO / "data_lake/research_panels/cross_asset_fused/fused_20260610_v2/cross_asset_fused_primary_panel.parquet"
GLOBAL = REPO / "data_lake/research_panels/cross_asset_fused/fused_20260610_v2/global_assets_week_panel.parquet"
OOS = pd.Timestamp("2024-01-01")
TOP_N = 12

# Structural / emergent candidates (not pre-built shock taxonomy labels).
META_CANDIDATES = (
    "mean_market_relevance_score_weighted",
    "news_rows",
    "unique_urls",
    "entity_count",
    "mean_tone_avg",
    "article_count",
    "url_count",
    "gkg_record_count",
)
TAX_CANDIDATES = (
    "financial_stress_per_1k_rows",
    "political_instability_per_1k_rows",
    "geopolitical_security_per_1k_rows",
    "macro_policy_per_1k_rows",
    "trade_supply_chain_per_1k_rows",
)
TARGETS_C = ("fwd_return_1w", "fwd_return_4w", "fwd_vol_4w")


def weekly_rank_ic_stats(df: pd.DataFrame, x: str, y: str) -> tuple[float, float, int]:
    sub = df[["week_end", x, y]].dropna()
    if len(sub) < 100:
        return np.nan, np.nan, 0
    sub = sub.copy()
    sub["rx"] = sub.groupby("week_end", sort=False)[x].rank()
    sub["ry"] = sub.groupby("week_end", sort=False)[y].rank()
    ics = sub.groupby("week_end", sort=False).apply(
        lambda g: float(g["rx"].corr(g["ry"])) if len(g) >= 6 and g["rx"].std() > 0 else np.nan,
        include_groups=False,
    )
    ics = ics.dropna()
    if len(ics) < 12:
        return np.nan, np.nan, int(len(ics))
    a = ics.to_numpy(dtype=float)
    mu = float(a.mean())
    sd = float(a.std(ddof=1))
    return mu, mu / (sd / math.sqrt(len(a)) + 1e-12), int(len(a))


def score_pair(df: pd.DataFrame, feat: str, tgt: str, ds: str) -> dict | None:
    if feat not in df.columns or tgt not in df.columns:
        return None
    sub = df.copy()
    sub["week_end"] = pd.to_datetime(sub["week_end"])
    oos = sub[sub.week_end >= OOS]
    is_ = sub[sub.week_end < OOS]
    if len(oos) < 80:
        return None
    ric_o, to, _ = weekly_rank_ic_stats(oos, feat, tgt)
    ric_i, ti, _ = weekly_rank_ic_stats(is_, feat, tgt)
    stab = abs(to) / max(abs(ti), 0.5) if np.isfinite(to) else np.nan
    disc = (abs(to) if np.isfinite(to) else 0) * (1 if (stab >= 0.35 or not np.isfinite(stab)) else 0.5)
    return {
        "dataset": ds,
        "feature": feat,
        "target": tgt,
        "oos_rank_ic": ric_o,
        "oos_rank_ic_t": to,
        "is_rank_ic_t": ti,
        "stability_ratio": stab,
        "discovery_score": disc,
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    if not FUSED.exists():
        raise SystemExit(f"missing fused panel: {FUSED}")

    rows: list[dict] = []
    fused = pd.read_parquet(FUSED)
    fused["week_end"] = pd.to_datetime(fused["week_end"])

    meta_feats = [c for c in META_CANDIDATES if c in fused.columns]
    tax_feats = [c for c in TAX_CANDIDATES if c in fused.columns]
    targets_g = [c for c in fused.columns if c.startswith("global_") and "fwd_return" in c][:6]

    for pool_name, pool in [("meta_structural", meta_feats), ("taxonomy_blind", tax_feats)]:
        for f in pool:
            for t in TARGETS_C:
                r = score_pair(fused, f, t, f"fused_{pool_name}")
                if r:
                    rows.append(r)
            wk = fused.groupby("week_end", as_index=False)[[f, *targets_g]].mean(numeric_only=True)
            for t in targets_g:
                r = score_pair(wk, f, t, f"asia_agg_{pool_name}")
                if r:
                    rows.append(r)

    if GLOBAL.exists() and meta_feats:
        disp = fused.groupby("week_end", as_index=False)[meta_feats].std(numeric_only=True)
        disp = disp.rename(columns={c: f"asia_disp_{c}" for c in meta_feats})
        g = pd.read_parquet(GLOBAL)
        g["week_end"] = pd.to_datetime(g["week_end"])
        spill = disp.merge(g, on="week_end")
        spill_feats = [c for c in spill.columns if c.startswith("asia_disp_")]
        spill_tgts = [c for c in spill.columns if "fwd_return" in c][:4]
        for f in spill_feats:
            for t in spill_tgts:
                r = score_pair(spill, f, t, "asia_dispersion_spillover")
                if r:
                    rows.append(r)

    if not rows:
        raise SystemExit("no discovery pairs scored")

    df = pd.DataFrame(rows).sort_values("discovery_score", ascending=False)
    emergent = df[~df.feature.astype(str).str.contains("per_1k|political_instability|macro_policy|financial_stress")]
    stable = df[df.stability_ratio.fillna(0) >= 0.35]

    manifest = {
        "built_at_utc": datetime.now(UTC).isoformat(),
        "n_pairs": int(len(df)),
        "top_overall": df.head(TOP_N).to_dict(orient="records"),
        "top_emergent_non_taxonomy": emergent.head(TOP_N).to_dict(orient="records"),
        "top_stable_oos": stable.head(TOP_N).to_dict(orient="records"),
        "verdict": {
            "best_emergent": emergent.iloc[0].to_dict() if len(emergent) else {},
            "anchor_feature": "mean_market_relevance_score_weighted",
        },
    }
    p = OUT / "latest.json"
    p.write_text(json.dumps(manifest, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(manifest["verdict"], indent=2, default=str))
    print(f"pairs={len(df)} wrote {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
