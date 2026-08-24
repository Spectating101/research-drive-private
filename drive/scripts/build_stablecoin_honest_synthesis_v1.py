#!/usr/bin/env python3
"""Build an honest stablecoin multi-construct synthesis + professor submission pack.

Does NOT invent historical security scores or follower stocks.
Does NOT treat community_growth_index / attention_proxy as community growth.
"""

from __future__ import annotations

import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
SRC_PANEL = (
    REPO
    / "data/datasets/stablecoin_trust_engagement/chatgpt_full_stablecoin_research_audit_20260713"
    / "package_20260707/panels/research_panel_weekly_full_history.csv"
)
SRC_EVENTS = (
    REPO
    / "data/datasets/stablecoin_trust_engagement/20260707/security_events.csv"
)
SRC_SNAPSHOT = (
    REPO
    / "data/datasets/stablecoin_trust_engagement/20260707/reference/security_snapshot.csv"
)
SRC_ENTITIES = (
    REPO / "data/datasets/stablecoin_trust_engagement/20260707/entities.csv"
)
SRC_BRIDGE = (
    REPO
    / "data/datasets/stablecoin_trust_engagement/bridge_v21/bridge_weekly_twitter_window.csv"
)

STAMP = datetime.now(timezone.utc).strftime("%Y%m%d")
OUT = REPO / "data/datasets/stablecoin_trust_engagement" / f"honest_synthesis_{STAMP}"
PROF = OUT / "professor_submission"


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def build_weekly(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["week"] = out["week"].astype(str)

    # --- Attention (NOT community growth) ---
    out["search_attention_trends"] = out["google_trends_index_mean"]
    out["search_attention_trends_obs"] = out["google_trends_observations"]
    out["search_attention_is_zero"] = (
        out["search_attention_trends"].notna() & (out["search_attention_trends"] == 0)
    ).astype(int)
    out["wiki_pageviews"] = out["wikipedia_pageviews_sum"]
    out["gdelt_entity_mentions"] = out["gdelt_entity_mention_rows"]
    out["reddit_submissions"] = out["reddit_submissions_sum"]

    # Legacy leaky composite — quarantine under explicit name
    out["legacy_leaky_attention_proxy"] = out["community_growth_index"]
    out["legacy_leaky_attention_proxy_note"] = (
        "Within-entity z-mean of Trends/Reddit/sparse Twitter WoW/holders; "
        "NOT community growth; includes Twitter when present (leakage vs follower growth)."
    )

    # --- Direct community growth (Twitter) — only where observed ---
    tw_weeks = set(
        out.loc[out["twitter_followers_wow_pct"].notna(), "week"].unique()
    )
    out["twitter_followers_end_observed"] = out["twitter_followers_end"]
    out["twitter_followers_wow_pct_observed"] = out["twitter_followers_wow_pct"]
    out["twitter_direct_growth_observed_flag"] = out["twitter_followers_wow_pct"].notna().astype(int)
    # Do not invent history: leave null outside window (already mostly null)

    # --- Adoption (not social community) ---
    out["holders_end"] = out["holder_count_end"]
    out["holders_wow_pct"] = out["holder_wow_pct"]
    out["supply_usd_end"] = out["supply_usd_end"]
    out["supply_wow_pct"] = out["supply_growth_wow_pct"]

    # --- Outcomes / stress ---
    out["peg_deviation_abs_max"] = out["peg_deviation_abs_max"]
    out["peg_below_99_flag"] = out["peg_below_99_flag"]

    # --- Security: time-varying signals vs snapshot ---
    out["security_event_flag"] = out["security_event_flag"].fillna(0).astype(int)
    out["security_event_count"] = out["security_event_count"].fillna(0)
    out["incident_count"] = out["incident_count"].fillna(0)
    out["github_security_keyword_commits"] = out["github_security_keyword_commit_count"]
    out["github_activity_index"] = out["github_activity_index"]

    # Snapshot scores: present on panel but MUST be flagged (single as_of)
    out["security_snapshot_as_of"] = out["security_as_of"]
    out["security_snapshot_skynet_score"] = out["skynet_score"]
    out["security_snapshot_code_score"] = out["code_security_score"]
    out["security_snapshot_flag"] = out["skynet_score"].notna().astype(int)
    # If score appears on multiple weeks, it is still the same snapshot — mark all
    # entities that have any snapshot value
    has_snap = out.groupby("entity_id")["skynet_score"].transform(lambda s: s.notna().any())
    out.loc[has_snap & out["skynet_score"].isna(), "security_snapshot_flag"] = 0
    out["security_scores_are_historical_weekly"] = 0  # explicit false

    # Coverage flags
    out["has_search_attention"] = out["search_attention_trends"].notna().astype(int)
    out["has_informative_search_attention"] = (
        out["search_attention_trends"].notna() & (out["search_attention_trends"] > 0)
    ).astype(int)
    out["has_wiki"] = out["wiki_pageviews"].notna().astype(int)
    out["has_gdelt"] = out["gdelt_entity_mentions"].notna().astype(int)
    out["has_reddit"] = out["reddit_submissions"].notna().astype(int)
    out["has_holders"] = out["holders_end"].notna().astype(int)
    out["has_supply"] = out["supply_usd_end"].notna().astype(int)
    out["has_direct_twitter_growth"] = out["twitter_direct_growth_observed_flag"]

    keep = [
        "entity_id",
        "week",
        # attention
        "search_attention_trends",
        "search_attention_trends_obs",
        "search_attention_is_zero",
        "wiki_pageviews",
        "gdelt_entity_mentions",
        "reddit_submissions",
        "legacy_leaky_attention_proxy",
        # direct community
        "twitter_followers_end_observed",
        "twitter_followers_wow_pct_observed",
        "twitter_direct_growth_observed_flag",
        # adoption
        "holders_end",
        "holders_wow_pct",
        "supply_usd_end",
        "supply_wow_pct",
        # outcomes
        "peg_deviation_abs_max",
        "peg_below_99_flag",
        # security time-varying
        "security_event_flag",
        "security_event_count",
        "incident_count",
        "github_security_keyword_commits",
        "github_activity_index",
        # security snapshot (not longitudinal)
        "security_snapshot_as_of",
        "security_snapshot_skynet_score",
        "security_snapshot_code_score",
        "security_snapshot_flag",
        "security_scores_are_historical_weekly",
        # coverage
        "has_search_attention",
        "has_informative_search_attention",
        "has_wiki",
        "has_gdelt",
        "has_reddit",
        "has_holders",
        "has_supply",
        "has_direct_twitter_growth",
    ]
    return out[keep].sort_values(["entity_id", "week"]).reset_index(drop=True)


def coverage_table(weekly: pd.DataFrame) -> pd.DataFrame:
    rows = []
    n = len(weekly)
    specs = [
        ("search_attention_trends", "attention", "Google Trends (normalized search interest)"),
        ("informative_search_attention", "attention", "Trends > 0 (excludes constant/low-volume zeros)"),
        ("wiki_pageviews", "attention", "Wikipedia pageviews"),
        ("gdelt_entity_mentions", "attention", "GDELT entity mention rows"),
        ("reddit_submissions", "attention_activity", "Reddit submissions (sparse)"),
        ("twitter_followers_wow_pct_observed", "community_growth_direct", "Twitter WoW — May–Jun 2026 only"),
        ("holders_wow_pct", "adoption", "On-chain holder growth"),
        ("supply_wow_pct", "adoption", "DeFiLlama supply growth"),
        ("peg_deviation_abs_max", "outcome", "Peg deviation (outcome, not security def)"),
        ("security_event_flag", "security_event", "Dated security event flag on week"),
        ("github_security_keyword_commits", "security_activity", "GitHub security-keyword commits"),
        ("security_snapshot_skynet_score", "security_snapshot", "Skynet score snapshot (NOT weekly history)"),
        ("legacy_leaky_attention_proxy", "deprecated", "Legacy composite — do not use as community growth"),
    ]
    for col, construct, desc in specs:
        if col == "informative_search_attention":
            mask = weekly["has_informative_search_attention"] == 1
            rate = float(mask.mean())
            n_ent = int(weekly.loc[mask, "entity_id"].nunique())
            weeks = weekly.loc[mask, "week"]
        elif col not in weekly.columns:
            continue
        else:
            mask = weekly[col].notna()
            if col == "security_event_flag":
                mask = weekly[col].fillna(0) > 0
            rate = float(mask.mean()) if col != "security_event_flag" else float((weekly[col] > 0).mean())
            n_ent = int(weekly.loc[weekly[col].notna() if col != "security_event_flag" else weekly[col] > 0, "entity_id"].nunique())
            weeks = weekly.loc[mask, "week"] if mask.any() else pd.Series(dtype=str)
        rows.append(
            {
                "column": col,
                "construct": construct,
                "description": desc,
                "row_coverage": round(rate, 4),
                "n_entities_with_any": n_ent,
                "week_min": weeks.min() if len(weeks) else None,
                "week_max": weeks.max() if len(weeks) else None,
                "usable_as_historical_community_growth": construct == "community_growth_direct",
                "usable_as_historical_security_score": False,
            }
        )
    return pd.DataFrame(rows)


def overlap_descriptives(weekly: pd.DataFrame, bridge: pd.DataFrame | None) -> pd.DataFrame:
    """Short-window descriptives only — no bootstrap CI theater."""
    rows = []
    w = weekly[weekly["twitter_direct_growth_observed_flag"] == 1].copy()
    # within-entity demeaned Spearman-ish via pooled demean
    def _assoc(xcol: str, ycol: str = "twitter_followers_wow_pct_observed") -> dict:
        m = w.dropna(subset=[xcol, ycol]).copy()
        if m.empty or m["entity_id"].nunique() < 3:
            return {
                "x": xcol,
                "y": ycol,
                "n_rows": int(len(m)),
                "n_entities": int(m["entity_id"].nunique()) if len(m) else 0,
                "pooled_spearman": np.nan,
                "within_entity_spearman": np.nan,
                "note": "insufficient overlap",
            }
        pooled = m[xcol].corr(m[ycol], method="spearman")
        m["x_dm"] = m[xcol] - m.groupby("entity_id")[xcol].transform("mean")
        m["y_dm"] = m[ycol] - m.groupby("entity_id")[ycol].transform("mean")
        within = m["x_dm"].corr(m["y_dm"], method="spearman")
        return {
            "x": xcol,
            "y": ycol,
            "n_rows": int(len(m)),
            "n_entities": int(m["entity_id"].nunique()),
            "pooled_spearman": None if pd.isna(pooled) else round(float(pooled), 4),
            "within_entity_spearman": None if pd.isna(within) else round(float(within), 4),
            "note": "exploratory short-window association only; not a validated leading indicator",
        }

    for x in [
        "search_attention_trends",
        "wiki_pageviews",
        "gdelt_entity_mentions",
        "holders_wow_pct",
        "supply_wow_pct",
        "legacy_leaky_attention_proxy",
    ]:
        rows.append(_assoc(x))

    # lag-1 trends vs growth (same short window)
    w = w.sort_values(["entity_id", "week"])
    w["trends_lag1"] = w.groupby("entity_id")["search_attention_trends"].shift(1)
    rows.append(_assoc("trends_lag1"))
    return pd.DataFrame(rows)


def write_readme(path: Path, meta: dict) -> None:
    path.write_text(
        f"""# Stablecoin constructs — honest synthesis

Built: `{meta["generated_at"]}`

## What this is

A multi-source **entity–week** synthesis for stablecoins that keeps constructs separate.

It does **not** answer, as a complete panel:

> How does security/audit evolution relate to community growth over 2021–2026?

Those two longitudinal series are **not available** for the full sample.

## What we do have

| Construct | What is in the data | Limit |
|-----------|---------------------|--------|
| **Direct community growth** | Twitter follower WoW | Only ~`2026-W20`–`2026-W26` |
| **Search attention** | Google Trends | Normalized interest; many zeros; ≠ community size |
| **Other attention** | Wikipedia, GDELT, sparse Reddit | Corroborators, not growth |
| **Adoption** | Holders, DeFiLlama supply | Capital uptake ≠ social followers |
| **Outcomes** | Peg deviation | Response measure, not security definition |
| **Security events** | Dated event list + week flags | Sparse; not a weekly score history |
| **Security snapshot** | Skynet / code scores | Single `as_of` (~2026-06-22), **not** historical weekly scores |
| **Legacy leaky proxy** | `legacy_leaky_attention_proxy` | Old `community_growth_index`; **do not use as community growth** |

## Files

### Synthesis (full)

- `synthesized_weekly_panel.csv` — construct-separated weekly panel + coverage flags
- `coverage_by_construct.csv` — row/entity coverage and allowed use
- `overlap_descriptives_twitter_window.csv` — short-window associations only (no bootstrap theater)
- `COLUMN_DICTIONARY.csv` — column → construct map
- `entities.csv` — entity reference
- `security_events_dated.csv` — one row per dated event
- `security_snapshot_latest.csv` — snapshot scores with as_of

### Professor submission (minimal)

See `professor_submission/` — same facts, fewer files, blunt email.

## Hard rules

1. Do not treat Trends or `legacy_leaky_attention_proxy` as historical community growth.
2. Do not treat Skynet snapshot scores as a 2021–2026 security panel.
3. Do not run an event study that assumes dense attention/growth around every event.
4. Peg/supply moves are outcomes, not definitions of security failure.
""",
        encoding="utf-8",
    )


def write_email(path: Path) -> None:
    path.write_text(
        """Subject: Stablecoin data package — constructs and coverage limits

Hi Professor Kong,

Thank you again for the question on the attention measure and on security vs community growth over time.

After reviewing source coverage carefully, I want to be direct about a measurement constraint:

We do not have (a) a complete historical weekly security-score panel for the sample, or (b) a complete historical Twitter/X follower-growth panel. Skynet security fields in our collection are effectively a mid-2026 snapshot. Direct follower growth is observed only for a short May–June 2026 window.

I am therefore sending a package that keeps constructs separate rather than filling missing history with a proxy labeled as community growth.

Contents (professor_submission/):

1. synthesized_weekly_panel.csv — entity–week panel with explicit construct columns and coverage flags
2. coverage_by_construct.csv — what is actually observed, and what it may be used for
3. security_events_dated.csv — dated security-related events (one row per event)
4. security_snapshot_latest.csv — latest Skynet/code scores with as_of date (snapshot only)
5. overlap_descriptives_twitter_window.csv — exploratory associations inside the short Twitter window only

Google Trends appears as search attention, not as community size. The older composite previously discussed is retained only as legacy_leaky_attention_proxy and should not be interpreted as community growth.

Best,
Chris
""",
        encoding="utf-8",
    )


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    PROF.mkdir(parents=True, exist_ok=True)

    raw = pd.read_csv(SRC_PANEL)
    weekly = build_weekly(raw)
    entities = pd.read_csv(SRC_ENTITIES)
    events = pd.read_csv(SRC_EVENTS)
    snapshot = pd.read_csv(SRC_SNAPSHOT)
    bridge = pd.read_csv(SRC_BRIDGE) if SRC_BRIDGE.exists() else None

    cov = coverage_table(weekly)
    overlap = overlap_descriptives(weekly, bridge)

    col_dict = pd.DataFrame(
        [
            {"column": c, "construct": (
                "key" if c in ("entity_id", "week") else
                "attention" if c.startswith(("search_", "wiki_", "gdelt_", "reddit_")) or c.startswith("has_search") or c.startswith("has_wiki") or c.startswith("has_gdelt") or c.startswith("has_reddit") else
                "community_growth_direct" if "twitter" in c else
                "adoption" if c.startswith(("holders_", "supply_", "has_holders", "has_supply")) else
                "outcome" if c.startswith("peg_") else
                "security_event" if "event" in c or c == "incident_count" else
                "security_activity" if c.startswith("github_") else
                "security_snapshot" if "snapshot" in c or c.startswith("security_scores") else
                "deprecated" if "legacy" in c else
                "coverage"
            )}
            for c in weekly.columns
        ]
    )

    # Write full synthesis
    weekly.to_csv(OUT / "synthesized_weekly_panel.csv", index=False)
    try:
        weekly.to_parquet(OUT / "synthesized_weekly_panel.parquet", index=False)
    except Exception:
        pass
    cov.to_csv(OUT / "coverage_by_construct.csv", index=False)
    overlap.to_csv(OUT / "overlap_descriptives_twitter_window.csv", index=False)
    col_dict.to_csv(OUT / "COLUMN_DICTIONARY.csv", index=False)
    entities.to_csv(OUT / "entities.csv", index=False)
    events.to_csv(OUT / "security_events_dated.csv", index=False)
    snapshot.to_csv(OUT / "security_snapshot_latest.csv", index=False)

    meta = {
        "generated_at": _utc(),
        "source_panel": str(SRC_PANEL.relative_to(REPO)),
        "n_rows": int(len(weekly)),
        "n_entities": int(weekly["entity_id"].nunique()),
        "week_min": str(weekly["week"].min()),
        "week_max": str(weekly["week"].max()),
        "twitter_direct_rows": int(weekly["twitter_direct_growth_observed_flag"].sum()),
        "twitter_weeks": sorted(
            weekly.loc[weekly["twitter_direct_growth_observed_flag"] == 1, "week"].unique().tolist()
        ),
        "security_snapshot_as_of_values": sorted(
            [str(x) for x in weekly["security_snapshot_as_of"].dropna().unique().tolist()]
        ),
        "design_rules": [
            "no synthetic historical security scores",
            "no synthetic historical follower stocks",
            "Trends labeled as search attention only",
            "legacy community_growth_index quarantined as legacy_leaky_attention_proxy",
            "no ±12-week empty event-study panel",
        ],
    }
    (OUT / "manifest.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    write_readme(OUT / "README.md", meta)

    # Professor minimal pack
    weekly.to_csv(PROF / "synthesized_weekly_panel.csv", index=False)
    cov.to_csv(PROF / "coverage_by_construct.csv", index=False)
    events.to_csv(PROF / "security_events_dated.csv", index=False)
    snapshot.to_csv(PROF / "security_snapshot_latest.csv", index=False)
    overlap.to_csv(PROF / "overlap_descriptives_twitter_window.csv", index=False)
    write_readme(PROF / "README.md", meta)
    write_email(PROF / "EMAIL.txt")
    (PROF / "manifest.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")

    zip_path = (
        REPO
        / "data/datasets/stablecoin_trust_engagement"
        / f"professor_honest_synthesis_{STAMP}.zip"
    )
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(PROF.rglob("*")):
            if f.is_file():
                zf.write(f, arcname=f"professor_honest_synthesis_{STAMP}/{f.relative_to(PROF)}")

    # Convenience copies at dataset root / Downloads-friendly path
    root_zip = REPO / f"stablecoin_professor_honest_synthesis_{STAMP}.zip"
    root_zip.write_bytes(zip_path.read_bytes())

    print(json.dumps({"out": str(OUT), "professor_zip": str(zip_path), "root_zip": str(root_zip), **{k: meta[k] for k in ("n_rows", "n_entities", "twitter_direct_rows", "twitter_weeks")}}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
