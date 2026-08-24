#!/usr/bin/env python3
"""Build best-effort stablecoin multi-construct dataset (growth / engagement / events).

Construct separation (non-negotiable):
  A) growth_observed_*  — Twitter/holder interval Δ + supply adoption Δ
  B) engagement_attention_* — Trends/Wiki/Reddit/GDELT (+ QC); NOT growth
  C) security_events_* — provenance-backed candidates only

Prefers solo Google Trends harvest over legacy batched Trends when available.
"""
from __future__ import annotations

import hashlib
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
STAMP = datetime.now(timezone.utc).strftime("%Y%m%d")
OUT = REPO / "data/datasets/stablecoin_trust_engagement" / f"best_dataset_v1_{STAMP}"

# Sources
COMM = REPO / "stablecoin_skynet/data/community"
FOLLOWERS = COMM / "follower_growth_panel.csv"
HOLDERS = COMM / "holder_growth_panel.csv"
BRIDGE = REPO / "data/datasets/stablecoin_trust_engagement/bridge_v21/bridge_weekly_twitter_window.csv"
WAYBACK_MONTHLY = REPO / "data/datasets/stablecoin_trust_engagement/wayback_followers_monthly/wayback_followers_monthly_panel.csv"
WAYBACK_QUARTERLY = REPO / "data/datasets/stablecoin_trust_engagement/wayback_followers_monthly/wayback_followers_quarterly_panel.csv"
PANEL = (
    REPO
    / "data/datasets/stablecoin_trust_engagement/chatgpt_full_stablecoin_research_audit_20260713"
    / "package_20260707/panels/research_panel_weekly_full_history.csv"
)
# Fallback panel
PANEL_ALT = REPO / "data/datasets/stablecoin_trust_engagement/20260707/panel_weekly.csv"
WIKI = REPO / "stablecoin_skynet/data/derived/wikipedia/wikipedia_pageviews_weekly.csv"
EVENTS = REPO / "config/stablecoin_security_events.json"
EVENTS_CSV = REPO / "data/datasets/stablecoin_trust_engagement/20260707/security_events.csv"
ENTITIES = REPO / "data/datasets/stablecoin_trust_engagement/20260707/entities.csv"
TRENDS_SOLO_DIRS = [
    COMM / "google_trends_solo_20260714",
    COMM / "google_trends_solo_full",
]
TRENDS_LEGACY = COMM / "google_trends"


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _week(d: str) -> str | None:
    try:
        dt = pd.Timestamp(d)
        y, w, _ = dt.isocalendar()
        return f"{int(y)}-W{int(w):02d}"
    except Exception:
        return None


def load_solo_trends() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return long panel + per-entity QC; prefer solo dirs over legacy."""
    rows = []
    sources = {}
    for root in TRENDS_SOLO_DIRS:
        if not root.exists():
            continue
        for d in root.iterdir():
            f = d / "google_trends_weekly.csv"
            if d.is_dir() and f.exists() and d.name not in sources:
                t = pd.read_csv(f)
                if "google_trends_index" not in t.columns:
                    continue
                t = t.copy()
                t["entity_id"] = d.name
                t["trends_source"] = f"solo:{root.name}"
                rows.append(t)
                sources[d.name] = str(f)
    # fill gaps from legacy
    if TRENDS_LEGACY.exists():
        for d in TRENDS_LEGACY.iterdir():
            f = d / "google_trends_weekly.csv"
            if not (d.is_dir() and f.exists()) or d.name in sources:
                continue
            t = pd.read_csv(f)
            if "google_trends_index" not in t.columns:
                # sometimes query name is column
                valcols = [c for c in t.columns if c not in ("date", "slug", "is_partial", "isPartial", "query")]
                if not valcols:
                    continue
                t = t.rename(columns={valcols[0]: "google_trends_index"})
            t = t.copy()
            t["entity_id"] = d.name
            t["trends_source"] = "legacy_batched"
            rows.append(t)
            sources[d.name] = str(f)
    if not rows:
        return pd.DataFrame(), pd.DataFrame()
    df = pd.concat(rows, ignore_index=True)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["google_trends_index"] = pd.to_numeric(df["google_trends_index"], errors="coerce")
    df["week"] = df["date"].dt.strftime("%G-W%V")
    # weekly mean
    weekly = (
        df.groupby(["entity_id", "week"], as_index=False)
        .agg(
            google_trends_index_mean=("google_trends_index", "mean"),
            trends_source=("trends_source", "first"),
            n_obs=("google_trends_index", "count"),
        )
    )
    qc = []
    for eid, g in df.groupby("entity_id"):
        s = g["google_trends_index"]
        zero = float((s.fillna(0) == 0).mean())
        nuniq = int(s.nunique(dropna=True))
        n = int(s.notna().sum())
        src = g["trends_source"].iloc[0]
        if zero >= 0.80 or n <= 4:
            flag = "uninformative_likely_noise"
        elif zero >= 0.75 or nuniq <= 10 or n < 52:
            flag = "reject_or_descriptive_only"
        else:
            flag = "usable_attention_with_caveats"
        qc.append(
            {
                "entity_id": eid,
                "trends_source": src,
                "n_obs": n,
                "zero_share": round(zero, 4),
                "n_distinct_values": nuniq,
                "audit_quality_flag": flag,
            }
        )
    return weekly, pd.DataFrame(qc)


def build_growth() -> pd.DataFrame:
    """Observed social/holder interval growth + adoption (supply)."""
    parts = []
    # Prefer bridge weekly window (has n_days / date_min/max) for exact-7d flags
    if BRIDGE.exists():
        br = pd.read_csv(BRIDGE)
        br = br.rename(columns={"slug": "entity_id", "date_min": "interval_start", "date_max": "interval_end", "n_days": "interval_days"})
        br["exact_seven_day_flag"] = (br["interval_days"] == 7).astype(int)
        br["followers_change_abs"] = br["followers_end"] - br["followers_start"]
        br["followers_change_pct"] = br.get("twitter_followers_wow_pct")
        if "followers_change_pct" not in br.columns or br["followers_change_pct"].isna().all():
            br["followers_change_pct"] = np.where(
                br["followers_start"] > 0,
                100.0 * br["followers_change_abs"] / br["followers_start"],
                np.nan,
            )
        keep = [c for c in [
            "entity_id","week","interval_start","interval_end","interval_days","exact_seven_day_flag",
            "followers_start","followers_end","followers_change_abs","followers_change_pct"
        ] if c in br.columns]
        twdf = br[keep].copy()
        twdf["metric_family"] = "twitter_followers_observed"
        twdf["construct"] = "growth_observed_social_size"
        twdf["source"] = "skynet_bridge_weekly_twitter_window"
        parts.append(twdf)
    elif FOLLOWERS.exists():
        tw = pd.read_csv(FOLLOWERS)
        tw["date"] = pd.to_datetime(tw["date"], errors="coerce")
        tw = tw.sort_values(["slug", "date"])
        rows = []
        for slug, g in tw.groupby("slug"):
            g = g.dropna(subset=["followers"]).copy()
            if len(g) < 2:
                continue
            g["followers_start"] = g["followers"].shift(1)
            g["interval_start"] = g["date"].shift(1)
            g["interval_end"] = g["date"]
            g["interval_days"] = (g["interval_end"] - g["interval_start"]).dt.days
            g["followers_end"] = g["followers"]
            g["followers_change_abs"] = g["followers_end"] - g["followers_start"]
            g["followers_change_pct"] = np.where(
                g["followers_start"] > 0,
                100.0 * g["followers_change_abs"] / g["followers_start"],
                np.nan,
            )
            g["exact_seven_day_flag"] = (g["interval_days"] == 7).astype(int)
            g["week"] = g["interval_end"].dt.strftime("%G-W%V")
            g["entity_id"] = slug
            rows.append(
                g.dropna(subset=["followers_start"])[
                    [
                        "entity_id",
                        "week",
                        "interval_start",
                        "interval_end",
                        "interval_days",
                        "exact_seven_day_flag",
                        "followers_start",
                        "followers_end",
                        "followers_change_abs",
                        "followers_change_pct",
                    ]
                ]
            )
        if rows:
            twdf = pd.concat(rows, ignore_index=True)
            twdf["metric_family"] = "twitter_followers_observed"
            twdf["construct"] = "growth_observed_social_size"
            twdf["source"] = "skynet_twitter_follower_growth"
            parts.append(twdf)

    if HOLDERS.exists():
        hd = pd.read_csv(HOLDERS)
        hd["date"] = pd.to_datetime(hd["date"], errors="coerce")
        hd = hd.sort_values(["slug", "date"])
        rows = []
        for slug, g in hd.groupby("slug"):
            g = g.dropna(subset=["holder_count"]).copy()
            if len(g) < 2:
                continue
            g["holders_start"] = g["holder_count"].shift(1)
            g["interval_start"] = g["date"].shift(1)
            g["interval_end"] = g["date"]
            g["interval_days"] = (g["interval_end"] - g["interval_start"]).dt.days
            g["holders_end"] = g["holder_count"]
            g["holders_change_abs"] = g["holders_end"] - g["holders_start"]
            g["holders_change_pct"] = np.where(
                g["holders_start"] > 0,
                100.0 * g["holders_change_abs"] / g["holders_start"],
                np.nan,
            )
            g["exact_seven_day_flag"] = (g["interval_days"] == 7).astype(int)
            g["week"] = g["interval_end"].dt.strftime("%G-W%V")
            g["entity_id"] = slug
            rows.append(
                g.dropna(subset=["holders_start"])[
                    [
                        "entity_id",
                        "week",
                        "interval_start",
                        "interval_end",
                        "interval_days",
                        "exact_seven_day_flag",
                        "holders_start",
                        "holders_end",
                        "holders_change_abs",
                        "holders_change_pct",
                    ]
                ]
            )
        if rows:
            hdf = pd.concat(rows, ignore_index=True)
            hdf["metric_family"] = "onchain_holders_observed"
            hdf["construct"] = "growth_observed_holder_count"
            hdf["source"] = "skynet_holder_growth"
            parts.append(hdf)

    # adoption from long panel
    panel_path = PANEL if PANEL.exists() else PANEL_ALT
    if panel_path.exists():
        p = pd.read_csv(panel_path, usecols=lambda c: c in {
            "entity_id", "week", "supply_usd_end", "supply_growth_wow_pct"
        } or True)
        keep = [c for c in ["entity_id", "week", "supply_usd_end", "supply_growth_wow_pct"] if c in p.columns]
        if len(keep) >= 3:
            ad = p[keep].copy()
            ad = ad.dropna(subset=["supply_growth_wow_pct"], how="all")
            ad["metric_family"] = "supply_adoption"
            ad["construct"] = "growth_adoption_supply"
            ad["source"] = "defillama_via_research_panel"
            ad["exact_seven_day_flag"] = 1  # weekly panel assumption
            parts.append(ad)

    # Wayback archive sparse monthly/quarterly (best-effort historical size stocks)
    if WAYBACK_MONTHLY.exists():
        wm = pd.read_csv(WAYBACK_MONTHLY)
        wm = wm.rename(columns={"year_month": "period"})
        wm["week"] = ""  # not weekly
        wm["metric_family"] = "twitter_followers_wayback_monthly"
        wm["construct"] = "growth_archive_wayback_monthly_sparse"
        wm["source"] = "internet_archive_wayback"
        parts.append(wm)
    if WAYBACK_QUARTERLY.exists():
        wq = pd.read_csv(WAYBACK_QUARTERLY)
        wq = wq.rename(columns={"year_quarter": "period"})
        wq["week"] = ""
        wq["metric_family"] = "twitter_followers_wayback_quarterly"
        wq["construct"] = "growth_archive_wayback_quarterly_sparse"
        wq["source"] = "internet_archive_wayback"
        parts.append(wq)

    if not parts:
        return pd.DataFrame()
    # outer-ish concat with union columns
    return pd.concat(parts, ignore_index=True, sort=False)


def _z_within(s: pd.Series) -> pd.Series:
    x = pd.to_numeric(s, errors="coerce")
    # treat zeros as missing for Trends z-score
    mu = x.mean()
    sd = x.std(ddof=0)
    if sd is None or not np.isfinite(sd) or sd == 0:
        return pd.Series(np.nan, index=s.index)
    return (x - mu) / sd


def build_engagement(trends_w: pd.DataFrame, trends_qc: pd.DataFrame) -> pd.DataFrame:
    panel_path = PANEL if PANEL.exists() else PANEL_ALT
    base = pd.read_csv(panel_path)
    if "entity_id" not in base.columns and "slug" in base.columns:
        base = base.rename(columns={"slug": "entity_id"})
    cols = [
        "entity_id",
        "week",
        "reddit_submissions_sum",
        "wikipedia_pageviews_sum",
        "gdelt_entity_mention_rows",
        "supply_growth_wow_pct",
        "google_trends_index_mean",
    ]
    have = [c for c in cols if c in base.columns]
    eng = base[have].copy()

    # overlay solo/legacy trends
    if not trends_w.empty:
        eng = eng.drop(columns=["google_trends_index_mean"], errors="ignore")
        eng = eng.merge(trends_w, on=["entity_id", "week"], how="outer")
    if WIKI.exists():
        wiki = pd.read_csv(WIKI)
        if "entity_id" in wiki.columns and "week" in wiki.columns:
            wcol = "wikipedia_pageviews_sum" if "wikipedia_pageviews_sum" in wiki.columns else None
            if wcol:
                eng = eng.drop(columns=["wikipedia_pageviews_sum"], errors="ignore")
                eng = eng.merge(wiki[["entity_id", "week", wcol]], on=["entity_id", "week"], how="left")

    # QC join
    if not trends_qc.empty:
        eng = eng.merge(trends_qc[["entity_id", "audit_quality_flag", "zero_share", "trends_source"]], on="entity_id", how="left")
    else:
        eng["audit_quality_flag"] = "unknown"
        eng["zero_share"] = np.nan
        eng["trends_source"] = "unknown"

    # mask bad trends
    bad = eng["audit_quality_flag"].isin(["uninformative_likely_noise", "reject_or_descriptive_only"])
    trends_for_z = pd.to_numeric(eng.get("google_trends_index_mean"), errors="coerce")
    trends_for_z = trends_for_z.where(~bad)
    trends_for_z = trends_for_z.where(trends_for_z > 0)  # zeros -> missing

    eng["z_trends"] = eng.groupby("entity_id", group_keys=False)[trends_for_z.name if False else "google_trends_index_mean"].transform(
        lambda s: _z_within(pd.to_numeric(s, errors="coerce").where(lambda x: x > 0))
    )
    # recompute properly with masked series
    tmp = eng.copy()
    tmp["_trends_z_in"] = trends_for_z
    eng["z_trends"] = tmp.groupby("entity_id")["_trends_z_in"].transform(_z_within)

    for col, zname in [
        ("reddit_submissions_sum", "z_reddit"),
        ("wikipedia_pageviews_sum", "z_wiki"),
        ("gdelt_entity_mention_rows", "z_gdelt"),
    ]:
        if col in eng.columns:
            eng[zname] = eng.groupby("entity_id")[col].transform(_z_within)
        else:
            eng[zname] = np.nan

    zcols = ["z_trends", "z_reddit", "z_wiki", "z_gdelt"]
    zmat = eng[zcols]
    eng["n_engagement_ingredients"] = zmat.notna().sum(axis=1)
    eng["community_engagement_proxy"] = zmat.mean(axis=1, skipna=True).where(eng["n_engagement_ingredients"] >= 2)
    eng["construct"] = "engagement_attention_not_growth"
    eng["label_warning"] = "NOT community growth; search/social attention + news intensity"
    return eng


def build_events() -> tuple[pd.DataFrame, pd.DataFrame]:
    if EVENTS.exists():
        payload = json.loads(EVENTS.read_text(encoding="utf-8"))
        ev = pd.DataFrame(payload.get("events") or [])
        rej = pd.DataFrame(payload.get("rejected_mappings_documented") or [])
    elif EVENTS_CSV.exists():
        ev = pd.read_csv(EVENTS_CSV)
        rej = pd.DataFrame()
    else:
        return pd.DataFrame(), pd.DataFrame()
    if not ev.empty:
        ev["outcome_attention_populated"] = 0
        ev["outcome_follower_populated"] = 0
        ev["outcome_coverage_note"] = "Candidates only — no fabricated event-window outcomes"
        ev["construct"] = "security_trust_event_candidate"
    return ev, rej


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    trends_w, trends_qc = load_solo_trends()
    growth = build_growth()
    eng = build_engagement(trends_w, trends_qc)
    events, rejected = build_events()

    # write
    paths = {}
    if not growth.empty:
        p = OUT / "01_growth_observed_and_adoption.csv"
        growth.to_csv(p, index=False)
        paths["growth"] = str(p.name)
    if not eng.empty:
        p = OUT / "02_engagement_attention_weekly.csv"
        eng.to_csv(p, index=False)
        paths["engagement"] = str(p.name)
    if not trends_qc.empty:
        p = OUT / "02b_trends_series_qc.csv"
        trends_qc.to_csv(p, index=False)
        paths["trends_qc"] = str(p.name)
    if not events.empty:
        p = OUT / "03_security_event_candidates_with_provenance.csv"
        events.to_csv(p, index=False)
        paths["events"] = str(p.name)
    if not rejected.empty:
        p = OUT / "03b_rejected_wrong_asset_mappings.csv"
        rejected.to_csv(p, index=False)
        paths["rejected"] = str(p.name)
    # Archive sparse growth extras
    for src, name in [
        (WAYBACK_MONTHLY, "05_wayback_followers_monthly_sparse.csv"),
        (WAYBACK_QUARTERLY, "05b_wayback_followers_quarterly_sparse.csv"),
        (REPO / "data/datasets/stablecoin_trust_engagement/wayback_followers_monthly/wayback_coverage_by_entity.csv", "05c_wayback_coverage_by_entity.csv"),
    ]:
        if src.exists():
            import shutil
            dst = OUT / name
            shutil.copy2(src, dst)
            paths[name] = name


    # calibration: exact-7d twitter vs engagement proxy overlap
    cal = None
    if not growth.empty and not eng.empty and "followers_change_pct" in growth.columns:
        g7 = growth[(growth.get("metric_family") == "twitter_followers_observed") & (growth["exact_seven_day_flag"] == 1)]
        if not g7.empty:
            m = g7.merge(
                eng[["entity_id", "week", "community_engagement_proxy"]],
                on=["entity_id", "week"],
                how="inner",
            )
            if len(m) >= 10:
                rho = m["followers_change_pct"].corr(m["community_engagement_proxy"], method="spearman")
                cal = {
                    "n_overlap_exact_7d": int(len(m)),
                    "spearman_followers_wow_vs_engagement_proxy": None if pd.isna(rho) else float(rho),
                    "note": "Diagnostic only — not validation that attention equals growth",
                }
                m.to_csv(OUT / "04_calibration_twitter7d_vs_engagement.csv", index=False)

    # coverage summary
    cov = {
        "created_at": _utc(),
        "purpose": "best_effort_multi_construct_dataset_not_professor_completed_answer",
        "files": paths,
        "growth": {
            "rows": int(len(growth)),
            "twitter_exact_7d": int(((growth.get("metric_family") == "twitter_followers_observed") & (growth.get("exact_seven_day_flag") == 1)).sum()) if not growth.empty else 0,
            "entities_twitter": int(growth.loc[growth.get("metric_family") == "twitter_followers_observed", "entity_id"].nunique()) if not growth.empty and "metric_family" in growth.columns else 0,
        },
        "engagement": {
            "rows": int(len(eng)),
            "entities": int(eng["entity_id"].nunique()) if not eng.empty else 0,
            "weeks": int(eng["week"].nunique()) if not eng.empty else 0,
            "proxy_nonnull": int(eng["community_engagement_proxy"].notna().sum()) if not eng.empty and "community_engagement_proxy" in eng.columns else 0,
            "trends_usable_entities": int((trends_qc["audit_quality_flag"] == "usable_attention_with_caveats").sum()) if not trends_qc.empty else 0,
            "trends_solo_entities": int((trends_qc["trends_source"].astype(str).str.startswith("solo")).sum()) if not trends_qc.empty else 0,
        },
        "events": {"n": int(len(events)), "rejected_mappings": int(len(rejected))},
        "calibration": cal,
        "cluster_note": "Solo Trends shards may still be harvesting on Windows nodes; re-run this builder to pick up new files.",
    }
    (OUT / "manifest.json").write_text(json.dumps(cov, indent=2) + "\n", encoding="utf-8")

    methods = f"""# Best dataset v1 — methods

Built: {cov['created_at']}

## Constructs (do not mix labels)

1. **Growth observed / adoption** (`01_…`)
   - Twitter follower interval changes from Skynet (exact_seven_day_flag)
   - On-chain holder interval changes from Skynet
   - Supply WoW as **adoption growth** (DeFiLlama), not social size

2. **Engagement / attention** (`02_…`)
   - Google Trends (solo harvest preferred; legacy batched filled gaps)
   - Wikipedia pageviews, Reddit submissions, GDELT mentions
   - `community_engagement_proxy` = mean of within-entity z-scores with ≥2 ingredients
   - Trends zeros treated as missing for z-scoring; QC flags attached

3. **Security event candidates** (`03_…`)
   - Provenance-visible curated events
   - Rejected wrong-asset mappings documented (OETH≠OUSD, Ethena≠sUSD)
   - No event-study outcome theater

## What this is NOT
- Not a multi-year Twitter community-growth series
- Not Professor Kong “completed answer” packaging
- Not validation that Trends = growth (see calibration file if present)

## Re-run
```bash
python3 drive/scripts/build_stablecoin_best_dataset_v1.py
```
After cluster Trends shards finish, re-run to upgrade solo coverage.
"""
    (OUT / "METHODS.md").write_text(methods, encoding="utf-8")
    (OUT / "README.md").write_text(
        "# Best dataset v1\n\nSee METHODS.md. Constructs separated. Re-run builder after harvests complete.\n",
        encoding="utf-8",
    )

    zpath = REPO / "data/datasets/stablecoin_trust_engagement" / f"stablecoin_best_dataset_v1_{STAMP}.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(OUT.iterdir()):
            if f.is_file():
                z.write(f, f"best_dataset_v1_{STAMP}/{f.name}")
    digest = hashlib.sha256(zpath.read_bytes()).hexdigest()
    cov["zip"] = str(zpath)
    cov["sha256"] = digest
    (OUT / "manifest.json").write_text(json.dumps(cov, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(cov, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
