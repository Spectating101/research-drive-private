#!/usr/bin/env python3
"""Best-effort long-run community ENGAGEMENT proxy (not Twitter follower growth).

Uses only series with multi-year coverage in the collected panel:
  - Google Trends (search attention; zeros treated as missing for z-scoring)
  - Wikipedia pageviews
  - Reddit submissions
  - GDELT entity mentions
  - DeFiLlama supply growth (adoption / capital uptake — separate column)

Excludes Twitter and holders from the composite (both are ~May–Jun 2026 only,
and Twitter in the composite would leak vs any follower-growth check).

Also ships:
  - ingredient-level weekly panel
  - Twitter calibration window (7 weeks) as a separate file
  - coverage + methods
"""

from __future__ import annotations

import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
SRC = (
    REPO
    / "data/datasets/stablecoin_trust_engagement/chatgpt_full_stablecoin_research_audit_20260713"
    / "package_20260707/panels/research_panel_weekly_full_history.csv"
)
SRC_EVENTS = REPO / "data/datasets/stablecoin_trust_engagement/20260707/security_events.csv"
SRC_SNAP = REPO / "data/datasets/stablecoin_trust_engagement/20260707/reference/security_snapshot.csv"
SRC_ENT = REPO / "data/datasets/stablecoin_trust_engagement/20260707/entities.csv"

STAMP = datetime.now(timezone.utc).strftime("%Y%m%d")
OUT = REPO / "data/datasets/stablecoin_trust_engagement" / f"engagement_proxy_v2_{STAMP}"


def _z_within(s: pd.Series) -> pd.Series:
    x = pd.to_numeric(s, errors="coerce")
    mu = x.mean()
    sd = x.std(ddof=0)
    if sd is None or not np.isfinite(sd) or sd == 0:
        return pd.Series(np.nan, index=s.index)
    return (x - mu) / sd


def build(df: pd.DataFrame) -> pd.DataFrame:
    out = df[
        [
            "entity_id",
            "week",
            "google_trends_index_mean",
            "reddit_submissions_sum",
            "wikipedia_pageviews_sum",
            "gdelt_entity_mention_rows",
            "supply_usd_end",
            "supply_growth_wow_pct",
            "twitter_followers_end",
            "twitter_followers_wow_pct",
            "holder_count_end",
            "holder_wow_pct",
            "peg_deviation_abs_max",
            "security_event_flag",
            "incident_count",
            "skynet_score",
            "code_security_score",
            "security_as_of",
        ]
    ].copy()
    out["week"] = out["week"].astype(str)

    # Ingredients (long-run engagement / attention)
    out["trends_raw"] = pd.to_numeric(out["google_trends_index_mean"], errors="coerce")
    # Treat zero Trends as missing for scoring (low-volume / batch artifact)
    out["trends_for_proxy"] = out["trends_raw"].where(out["trends_raw"] > 0)
    out["wiki_log1p"] = np.log1p(pd.to_numeric(out["wikipedia_pageviews_sum"], errors="coerce"))
    out["reddit_log1p"] = np.log1p(pd.to_numeric(out["reddit_submissions_sum"], errors="coerce"))
    out["gdelt_log1p"] = np.log1p(pd.to_numeric(out["gdelt_entity_mention_rows"], errors="coerce"))

    # Within-entity z of each ingredient
    parts = []
    for eid, g in out.groupby("entity_id", sort=False):
        g = g.copy()
        g["z_trends"] = _z_within(g["trends_for_proxy"])
        g["z_wiki"] = _z_within(g["wiki_log1p"])
        g["z_reddit"] = _z_within(g["reddit_log1p"])
        g["z_gdelt"] = _z_within(g["gdelt_log1p"])
        zmat = g[["z_trends", "z_wiki", "z_reddit", "z_gdelt"]]
        g["n_proxy_ingredients"] = zmat.notna().sum(axis=1)
        # Require ≥2 ingredients so a single sparse series doesn't dominate
        g["community_engagement_proxy"] = zmat.mean(axis=1, skipna=True)
        g.loc[g["n_proxy_ingredients"] < 2, "community_engagement_proxy"] = np.nan
        # Attention-only (Trends+Wiki+GDELT, no reddit) for robustness
        z_att = g[["z_trends", "z_wiki", "z_gdelt"]]
        g["n_attention_ingredients"] = z_att.notna().sum(axis=1)
        g["search_media_attention_proxy"] = z_att.mean(axis=1, skipna=True)
        g.loc[g["n_attention_ingredients"] < 2, "search_media_attention_proxy"] = np.nan
        parts.append(g)
    out = pd.concat(parts, ignore_index=True)

    # Adoption growth (capital / user-base on-chain — NOT social followers)
    out["adoption_supply_wow_pct"] = pd.to_numeric(out["supply_growth_wow_pct"], errors="coerce")
    out["adoption_supply_usd"] = pd.to_numeric(out["supply_usd_end"], errors="coerce")

    # Direct social size growth — short windows only (document, don't extend)
    out["twitter_wow_pct_direct"] = pd.to_numeric(out["twitter_followers_wow_pct"], errors="coerce")
    out["holders_wow_pct_direct"] = pd.to_numeric(out["holder_wow_pct"], errors="coerce")
    out["twitter_direct_flag"] = out["twitter_wow_pct_direct"].notna().astype(int)
    out["holders_direct_flag"] = out["holders_wow_pct_direct"].notna().astype(int)

    out["security_snapshot_skynet"] = pd.to_numeric(out["skynet_score"], errors="coerce")
    out["security_snapshot_code"] = pd.to_numeric(out["code_security_score"], errors="coerce")
    out["security_snapshot_as_of"] = out["security_as_of"]
    out["security_scores_are_historical_weekly"] = 0

    keep = [
        "entity_id",
        "week",
        "community_engagement_proxy",
        "n_proxy_ingredients",
        "search_media_attention_proxy",
        "n_attention_ingredients",
        "trends_raw",
        "trends_for_proxy",
        "z_trends",
        "wiki_log1p",
        "z_wiki",
        "reddit_log1p",
        "z_reddit",
        "gdelt_log1p",
        "z_gdelt",
        "adoption_supply_usd",
        "adoption_supply_wow_pct",
        "twitter_wow_pct_direct",
        "twitter_direct_flag",
        "holders_wow_pct_direct",
        "holders_direct_flag",
        "peg_deviation_abs_max",
        "security_event_flag",
        "incident_count",
        "security_snapshot_as_of",
        "security_snapshot_skynet",
        "security_snapshot_code",
        "security_scores_are_historical_weekly",
    ]
    return out[keep].sort_values(["entity_id", "week"]).reset_index(drop=True)


def coverage(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for col, construct, note in [
        ("community_engagement_proxy", "engagement_proxy_long", "z-mean of Trends(>0)/Wiki/Reddit/GDELT; ≥2 ingredients; EXCLUDES Twitter"),
        ("search_media_attention_proxy", "attention_proxy_long", "z-mean of Trends(>0)/Wiki/GDELT; ≥2 ingredients"),
        ("trends_for_proxy", "attention", "Google Trends with zeros dropped"),
        ("wiki_log1p", "attention", "Wikipedia pageviews log1p"),
        ("reddit_log1p", "forum_activity", "Reddit submissions log1p (ends ~2025-W21)"),
        ("gdelt_log1p", "news_attention", "GDELT entity mentions log1p"),
        ("adoption_supply_wow_pct", "adoption_growth", "DeFiLlama supply WoW — capital uptake, not social followers"),
        ("twitter_wow_pct_direct", "social_size_direct", "Twitter follower WoW — 7 weeks only"),
        ("holders_wow_pct_direct", "onchain_holders_direct", "Holder WoW — ~5 weeks only (same short Skynet window)"),
    ]:
        m = df[col].notna()
        rows.append(
            {
                "column": col,
                "construct": construct,
                "row_coverage": round(float(m.mean()), 4),
                "n_entities": int(df.loc[m, "entity_id"].nunique()) if m.any() else 0,
                "week_min": df.loc[m, "week"].min() if m.any() else None,
                "week_max": df.loc[m, "week"].max() if m.any() else None,
                "note": note,
            }
        )
    return pd.DataFrame(rows)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    raw = pd.read_csv(SRC, low_memory=False)
    panel = build(raw)
    cov = coverage(panel)
    events = pd.read_csv(SRC_EVENTS)
    snap = pd.read_csv(SRC_SNAP)
    ent = pd.read_csv(SRC_ENT)

    tw = panel[panel["twitter_direct_flag"] == 1].copy()
    # Long panel without insisting on twitter
    long = panel.drop(columns=[c for c in panel.columns if c.startswith("twitter_") or c.startswith("holders_")])

    panel.to_csv(OUT / "engagement_proxy_weekly_full.csv", index=False)
    long.to_csv(OUT / "engagement_proxy_weekly_longrun.csv", index=False)
    tw.to_csv(OUT / "twitter_calibration_7weeks.csv", index=False)
    cov.to_csv(OUT / "coverage_by_signal.csv", index=False)
    events.to_csv(OUT / "security_events_dated.csv", index=False)
    snap.to_csv(OUT / "security_snapshot_latest.csv", index=False)
    ent.to_csv(OUT / "entities.csv", index=False)

    # Overlap: proxy vs twitter in 7-week window (honesty check)
    m = panel[panel["twitter_direct_flag"] == 1].dropna(
        subset=["community_engagement_proxy", "twitter_wow_pct_direct"]
    )
    if len(m) >= 30:
        pooled = m["community_engagement_proxy"].corr(m["twitter_wow_pct_direct"], method="spearman")
        m = m.copy()
        m["xdm"] = m["community_engagement_proxy"] - m.groupby("entity_id")["community_engagement_proxy"].transform("mean")
        m["ydm"] = m["twitter_wow_pct_direct"] - m.groupby("entity_id")["twitter_wow_pct_direct"].transform("mean")
        within = m["xdm"].corr(m["ydm"], method="spearman")
    else:
        pooled = within = float("nan")

    meta = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "n_rows": int(len(panel)),
        "n_entities": int(panel["entity_id"].nunique()),
        "engagement_proxy_row_coverage": float(panel["community_engagement_proxy"].notna().mean()),
        "engagement_proxy_week_span": [
            str(panel.loc[panel["community_engagement_proxy"].notna(), "week"].min()),
            str(panel.loc[panel["community_engagement_proxy"].notna(), "week"].max()),
        ],
        "twitter_calibration_rows": int(len(tw)),
        "twitter_weeks": sorted(tw["week"].unique().tolist()),
        "overlap_proxy_vs_twitter_pooled_spearman": None if pd.isna(pooled) else round(float(pooled), 4),
        "overlap_proxy_vs_twitter_within_spearman": None if pd.isna(within) else round(float(within), 4),
        "claims_allowed": [
            "community_engagement_proxy = multi-year engagement/attention composite (Trends>0, Wiki, Reddit, GDELT)",
            "NOT historical Twitter follower growth",
            "NOT historical holder growth",
            "adoption_supply_wow = capital uptake proxy",
            "Twitter/holders files are calibration/direct only",
        ],
        "not_available_in_collection": [
            "historical Twitter/X follower stocks before 2026-W20",
            "historical Telegram member time series",
            "historical Discord member time series",
            "historical CoinGecko reddit_subscribers / telegram panel (snapshot fields only in Skynet harvest)",
            "historical weekly Skynet security scores",
        ],
    }
    (OUT / "manifest.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")

    readme = f"""# Community engagement proxy v2 (best long-run effort)

Built: `{meta["generated_at"]}`

## Straight answer

**Twitter follower growth:** only **7 weeks** (`2026-W20`–`W26`) in our collection.  
**On-chain holders growth:** also only ~**5 weeks** (same short Skynet window).  
So “community size growth” as follower/holder stocks is **not** recoverable historically from what we have.

That does **not** mean there is no long-run community-*related* data. We do have multi-year **engagement / attention / adoption** series.

## Primary long-run measure

`community_engagement_proxy` = within-entity mean of z-scores of:

1. Google Trends (zeros dropped — treated as missing)
2. Wikipedia pageviews (log1p)
3. Reddit submissions (log1p)
4. GDELT entity mentions (log1p)

Requires **≥2** ingredients that week. **Excludes Twitter** (no leakage into follower checks).

Also provided: `search_media_attention_proxy` (Trends+Wiki+GDELT only).

`adoption_supply_wow_pct` = DeFiLlama supply growth — **capital uptake**, useful as a parallel “usage base” proxy, not social community.

## Files

| File | Use |
|------|-----|
| `engagement_proxy_weekly_longrun.csv` | Main long panel (no twitter/holder columns) |
| `engagement_proxy_weekly_full.csv` | Same + short direct twitter/holder columns |
| `twitter_calibration_7weeks.csv` | Direct Twitter WoW only |
| `coverage_by_signal.csv` | What exists and for how long |
| `security_events_dated.csv` / `security_snapshot_latest.csv` | Security side |

## Overlap check (7-week Twitter window)

Pooled Spearman(proxy, twitter WoW) ≈ **{meta.get("overlap_proxy_vs_twitter_pooled_spearman")}**  
Within-entity ≈ **{meta.get("overlap_proxy_vs_twitter_within_spearman")}**  

Treat as exploratory calibration only — **do not** use this to impute years of follower growth.

## What we still don't have (would need new collection)

- Historical Telegram / Discord member counts  
- Historical CoinGecko social subscriber panels  
- Pre-2026 Twitter follower archives  
- Historical weekly Skynet security scores  

## How to talk about this to a professor

> We cannot reconstruct historical Twitter community-size growth.  
> We can provide a multi-year **engagement proxy** from Trends, Wikipedia, Reddit activity, and GDELT, plus supply growth as adoption, plus a short Twitter calibration window.
"""
    (OUT / "README.md").write_text(readme, encoding="utf-8")

    email = """Subject: Stablecoin package — long-run engagement proxy (Twitter growth only 7 weeks)

Hi Professor Kong,

Direct Twitter/X follower-growth history is only available in our collection for seven weeks (2026-W20 to 2026-W26). On-chain holder growth is similarly short. Extending that into a multi-year “community growth” series would require inventing data we do not have.

What we can provide instead is a multi-year community engagement proxy built from Google Trends (zeros excluded), Wikipedia pageviews, Reddit submissions, and GDELT mentions — without putting Twitter into the composite. Supply growth is included separately as an adoption/capital-uptake measure. The seven-week Twitter window is kept only as a calibration sample.

Security remains dated events plus a mid-2026 score snapshot, not a historical weekly security-score panel.

Best,
Chris
"""
    (OUT / "EMAIL.txt").write_text(email, encoding="utf-8")

    zip_path = REPO / f"stablecoin_engagement_proxy_v2_{STAMP}.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(OUT.iterdir()):
            if f.is_file() and f.suffix in {".csv", ".md", ".txt", ".json"}:
                # skip full panel in zip if huge — include longrun + calibration + docs
                if f.name == "engagement_proxy_weekly_full.csv":
                    continue
                zf.write(f, arcname=f"engagement_proxy_v2_{STAMP}/{f.name}")
    # also copy longrun is included; full stays on disk only
    dl = Path.home() / "Downloads" / zip_path.name
    dl.write_bytes(zip_path.read_bytes())

    print(json.dumps({"out": str(OUT), "zip": str(zip_path), **{k: meta[k] for k in meta if k != "claims_allowed" and k != "not_available_in_collection"}}, indent=2))
    print("\nCoverage:")
    print(cov.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
