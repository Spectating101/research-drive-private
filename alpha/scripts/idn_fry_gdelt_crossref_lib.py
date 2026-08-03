"""Cross-reference fry episodes with GDELT news-shock dots and literature anchors.

Joins:
  - fry trigger/pop episodes (price FSM)
  - IDN daily country shock panel (GDELT GKG taxonomy dots)
  - ticker entity daily shock panel (symbol-specific dots)
  - literature / publication framing from research handoffs

Clusters news 'dots' around each episode:
  - theme dominance (which shock bucket fired)
  - burst detection (consecutive high-shock days)
  - pre-trigger vs post-trigger shock intensity
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

import importlib.util as _ilu
from pathlib import Path as _Path

_bspec = _ilu.spec_from_file_location("sr_bootstrap", _Path(__file__).resolve().parent / "_repo_bootstrap.py")
_bmod = _ilu.module_from_spec(_bspec)
_bspec.loader.exec_module(_bmod)
REPO = _bmod.repo_root_from_file(__file__)
FRY_DIR = REPO / "data_lake/research_panels/idn_fry_episode"
NEWS_PROCESSED = REPO / "data_lake/news_shock_taxonomy/processed"
ENTITY_DAILY = REPO / "data_lake/research_panels/ticker_news_market/ticker_20260611/daily_ticker_entity_shock_panel.parquet"
ASIA_NEWS_LATEST = REPO / "data_lake/research_panels/asia_news_market/asia_news_market_completed_through_202509_20260525"
OUT_DIR = FRY_DIR

SHOCK_COLS = [
    "financial_stress_rows",
    "geopolitical_security_rows",
    "governance_corruption_rows",
    "health_rows",
    "macro_policy_rows",
    "natural_environment_rows",
    "political_instability_rows",
    "trade_supply_chain_rows",
]

PRE_DAYS = 7
POST_DAYS = 12
BURST_MIN_DAYS = 2


def load_idn_country_shocks() -> pd.DataFrame:
    """Concat deduped IDN daily country shock rows from all processed GDELT windows."""
    frames: list[pd.DataFrame] = []
    if not NEWS_PROCESSED.exists():
        return pd.DataFrame()
    for win in sorted(NEWS_PROCESSED.glob("asia_gkg_window_*")):
        path = win / "daily_country_shock_panel.csv"
        if not path.exists():
            continue
        df = pd.read_csv(path)
        if "country_iso3" not in df.columns:
            continue
        sub = df[df["country_iso3"] == "IDN"].copy()
        if sub.empty:
            continue
        sub["date"] = pd.to_datetime(sub["date"])
        sub["source_window"] = win.name
        frames.append(sub)
    if not frames:
        return pd.DataFrame()
    all_df = pd.concat(frames, ignore_index=True)
    # dedupe: prefer latest processed window per date
    all_df = all_df.sort_values("source_window").drop_duplicates(subset=["date"], keep="last")
    for c in SHOCK_COLS:
        if c not in all_df.columns:
            all_df[c] = 0
    all_df["shock_dot_total"] = all_df[SHOCK_COLS].sum(axis=1)
    all_df["active_shock_themes"] = all_df[SHOCK_COLS].gt(0).sum(axis=1)
    return all_df.sort_values("date").reset_index(drop=True)


def load_entity_daily() -> pd.DataFrame:
    if not ENTITY_DAILY.exists():
        return pd.DataFrame()
    df = pd.read_parquet(ENTITY_DAILY)
    df["date"] = pd.to_datetime(df["date"])
    for c in SHOCK_COLS:
        if c not in df.columns:
            df[c] = 0
    df["entity_shock_total"] = df[SHOCK_COLS].sum(axis=1)
    df["entity_mention_rows"] = df.get("entity_mention_rows", 0)
    return df


def _dominant_theme(row: pd.Series, cols: list[str]) -> str | None:
    vals = {c.replace("_rows", ""): float(row.get(c, 0) or 0) for c in cols}
    if max(vals.values()) <= 0:
        return None
    return max(vals, key=vals.get)


def _window_slice(panel: pd.DataFrame, sym: str | None, t0: pd.Timestamp, pre: int, post: int) -> pd.DataFrame:
    start = t0 - pd.Timedelta(days=pre)
    end = t0 + pd.Timedelta(days=post)
    if sym is not None:
        sub = panel[(panel["yahoo_symbol"] == sym) & (panel["date"] >= start) & (panel["date"] <= end)]
    else:
        sub = panel[(panel["date"] >= start) & (panel["date"] <= end)]
    return sub.sort_values("date")


def _burst_days(shock_series: pd.Series, threshold: float) -> int:
    """Count max consecutive days above threshold."""
    if shock_series.empty:
        return 0
    flags = (shock_series >= threshold).astype(int).to_numpy()
    best = cur = 0
    for f in flags:
        if f:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best if best >= BURST_MIN_DAYS else 0


def episode_news_features(
    trig: pd.DataFrame,
    country: pd.DataFrame,
    entity: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if not country.empty:
        country = country.copy()
        country["shock_z"] = (country["shock_dot_total"] - country["shock_dot_total"].rolling(30, min_periods=10).median()) / (
            country["shock_dot_total"].rolling(30, min_periods=10).std().replace(0, np.nan)
        )
        country["shock_z"] = country["shock_z"].fillna(0)
    burst_thr = 1.5

    for _, r in trig.iterrows():
        sym = r["yahoo_symbol"]
        t0 = pd.to_datetime(r["date"])
        got_pop = int(r["got_pop"])

        cw = _window_slice(country, None, t0, PRE_DAYS, POST_DAYS) if not country.empty else pd.DataFrame()
        pre_c = cw[cw["date"] < t0] if not cw.empty else pd.DataFrame()
        post_c = cw[cw["date"] >= t0] if not cw.empty else pd.DataFrame()

        ew = _window_slice(entity, sym, t0, PRE_DAYS, POST_DAYS) if not entity.empty else pd.DataFrame()
        pre_e = ew[ew["date"] < t0] if not ew.empty else pd.DataFrame()
        post_e = ew[ew["date"] >= t0] if not ew.empty else pd.DataFrame()

        pre_mean_daily = float(pre_c["shock_dot_total"].mean()) if not pre_c.empty else 0.0
        post_mean_daily = float(post_c["shock_dot_total"].mean()) if not post_c.empty else 0.0
        pre_z_mean = float(pre_c["shock_z"].mean()) if not pre_c.empty and "shock_z" in pre_c else 0.0
        post_z_mean = float(post_c["shock_z"].mean()) if not post_c.empty and "shock_z" in post_c else 0.0

        # theme share: which bucket gained most share in pre window vs country baseline
        dom_pre = None
        if not pre_c.empty:
            theme_totals = pre_c[SHOCK_COLS].sum()
            total = float(theme_totals.sum())
            if total > 0:
                shares = theme_totals / total
                dom_pre = str(shares.idxmax()).replace("_rows", "") if shares.max() > 0 else None

        dom_post = None
        if not post_c.empty:
            theme_totals = post_c[SHOCK_COLS].sum()
            total = float(theme_totals.sum())
            if total > 0:
                shares = theme_totals / total
                dom_post = str(shares.idxmax()).replace("_rows", "") if shares.max() > 0 else None

        burst_pre = int((pre_c["shock_z"] >= burst_thr).sum()) if not pre_c.empty and "shock_z" in pre_c else 0
        burst_post = int((post_c["shock_z"] >= burst_thr).sum()) if not post_c.empty and "shock_z" in post_c else 0

        pre_entity_mentions = int(pre_e["entity_mention_rows"].sum()) if not pre_e.empty and "entity_mention_rows" in pre_e else 0
        post_entity_mentions = int(post_e["entity_mention_rows"].sum()) if not post_e.empty and "entity_mention_rows" in post_e else 0

        tone_pre = float(pre_c["mean_tone"].mean()) if not pre_c.empty and "mean_tone" in pre_c.columns else None
        tone_post = float(post_c["mean_tone"].mean()) if not post_c.empty and "mean_tone" in post_c.columns else None

        rows.append(
            {
                "episode_id": int(r["episode_id"]),
                "yahoo_symbol": sym,
                "trigger_date": str(t0.date()),
                "got_pop": got_pop,
                "trigger_cause": r.get("trigger_cause"),
                "pre_mean_daily_country_dots": round(pre_mean_daily, 1),
                "post_mean_daily_country_dots": round(post_mean_daily, 1),
                "country_dot_accel": round(post_mean_daily - pre_mean_daily, 1),
                "pre_country_shock_z_mean": round(pre_z_mean, 3),
                "post_country_shock_z_mean": round(post_z_mean, 3),
                "country_burst_days_pre": burst_pre,
                "country_burst_days_post": burst_post,
                "dominant_country_theme_pre": dom_pre or "no_pre_window",
                "dominant_country_theme_post": dom_post or "no_post_window",
                "pre_entity_mentions": pre_entity_mentions,
                "post_entity_mentions": post_entity_mentions,
                "country_tone_pre": round(tone_pre, 3) if tone_pre is not None and tone_pre == tone_pre else None,
                "country_tone_post": round(tone_post, 3) if tone_post is not None and tone_post == tone_post else None,
                "has_entity_coverage": bool(not ew.empty),
                "has_entity_mention": bool(pre_entity_mentions > 0 or post_entity_mentions > 0),
            }
        )
    return pd.DataFrame(rows)


def cluster_episodes_by_news(features: pd.DataFrame) -> dict[str, Any]:
    """Group episodes by dominant pre-trigger country shock theme share."""
    if features.empty:
        return {"clusters": []}
    clusters = []
    for theme, g in features.groupby("dominant_country_theme_pre", dropna=False):
        label = str(theme) if theme is not None else "unknown"
        pop_rate = float(g["got_pop"].mean()) if len(g) else 0.0
        clusters.append(
            {
                "cluster": label,
                "n_episodes": int(len(g)),
                "pop_rate_pct": round(pop_rate * 100, 1),
                "median_pre_shock_z": round(float(g["pre_country_shock_z_mean"].median()), 3),
                "median_burst_days_pre": float(g["country_burst_days_pre"].median()),
                "pct_with_entity_mention": round(float(g["has_entity_mention"].mean()) * 100, 1),
            }
        )
    clusters.sort(key=lambda x: -x["n_episodes"])
    return {"clusters": clusters}


def compare_pop_news(features: pd.DataFrame) -> dict[str, Any]:
    from idn_signal_stats import benjamini_hochberg

    if features.empty:
        return {}
    metrics = [
        "pre_country_shock_z_mean",
        "post_country_shock_z_mean",
        "country_dot_accel",
        "pre_entity_mentions",
        "post_entity_mentions",
        "country_burst_days_pre",
        "country_burst_days_post",
        "country_tone_pre",
    ]
    rows = []
    pop = features["got_pop"] == 1
    for m in metrics:
        a = features.loc[pop, m].dropna()
        b = features.loc[~pop, m].dropna()
        if len(a) < 20 or len(b) < 20:
            continue
        try:
            from scipy import stats

            u, p = stats.mannwhitneyu(a, b, alternative="two-sided")
        except Exception:
            p = 1.0
            u = 0
        rows.append(
            {
                "metric": m,
                "with_pop_median": round(float(a.median()), 3),
                "no_pop_median": round(float(b.median()), 3),
                "mannwhitney_p": round(float(p), 4),
            }
        )
    fdr = benjamini_hochberg([r["metric"] for r in rows], [r["mannwhitney_p"] for r in rows])
    for r in rows:
        r["fdr_q"] = fdr.get(r["metric"])
    return {"pop_vs_no_pop_news": rows}


def literature_crosswalk() -> dict[str, Any]:
    """Map empirical fry findings to publication anchors in repo docs."""
    return {
        "indonesia_market_structure": {
            "source": "deep-research-report.md",
            "claims": [
                "MSCI ownership/free-float scrutiny and stock-frying concerns (Reuters-cited in report)",
                "Indonesia = banks-first investable sleeve, not broad IHSG",
                "FX/rupiah stress as primary macro transmission channel",
            ],
            "relevance_to_fry": "Fry phenomenon aligns with concentrated-ownership microcaps outside investable core; bandar episodes are structurally distinct from BBCA-style compounder sleeve.",
        },
        "news_shock_literature": {
            "source": "docs/research_handoffs/research_tracks_literature_scan_20260521.md",
            "anchors": [
                {"paper": "Tetlock (2007)", "prediction": "topic-specific negative tone → short-run pressure + volume, then reversion"},
                {"paper": "Baker-Bloom-Davis EPU", "prediction": "policy uncertainty → vol and drawdown risk"},
                {"paper": "Hassan et al. firm political risk", "prediction": "firm-specific risk language → investment/vol sensitivity"},
                {"paper": "Harvey (1994) EM local information", "prediction": "EM returns more sensitive to local shocks than global beta"},
            ],
            "our_test": "GDELT shock-theme dots around fry triggers — do governance/financial_stress clusters precede pop?",
        },
        "repo_empirical_idn": {
            "source": "docs/IDN_RESEARCH.md",
            "note": "Country broadcast GDELT identical across tickers — entity panel required for symbol-specific dots.",
            "fry_price_empirics": "drawdown_vol_spike + return_5d<=-8% → ~42% OOS pop; quiet_accumulation → ~12%",
        },
        "gdelt_taxonomy": {
            "source": "config/news_shock_asia_universe.json",
            "shock_buckets": [c.replace("_rows", "") for c in SHOCK_COLS],
            "idn_terms": ["Indonesia", "Indonesian", "Jakarta", "Rupiah"],
        },
    }


def sample_publication_dots(country: pd.DataFrame, features: pd.DataFrame, n: int = 5) -> list[dict[str, Any]]:
    """High-shock trigger weeks with pop outcomes for qualitative dot inspection."""
    if country.empty or features.empty:
        return []
    cday = country[["date", "shock_dot_total"] + SHOCK_COLS].copy()
    cday["trigger_date"] = cday["date"].dt.strftime("%Y-%m-%d")
    merged = features.merge(cday.drop(columns=["date"]), on="trigger_date", how="left")
    top = merged.nlargest(n, "pre_country_shock_z_mean")
    out = []
    for _, r in top.iterrows():
        out.append(
            {
                "yahoo_symbol": r["yahoo_symbol"],
                "trigger_date": r["trigger_date"],
                "got_pop": int(r["got_pop"]),
                "pre_country_shock_z": float(r.get("pre_country_shock_z_mean", 0)),
                "dominant_theme_pre": r.get("dominant_country_theme_pre"),
                "trigger_day_country_dots": int(r.get("shock_dot_total", 0) or 0),
            }
        )
    return out


def build_gdelt_literature_crossref() -> dict[str, Any]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    trig = pd.read_parquet(FRY_DIR / "trigger_enriched.parquet")
    trig["date"] = pd.to_datetime(trig["date"])

    country = load_idn_country_shocks()
    entity = load_entity_daily()

    features = episode_news_features(trig, country, entity)
    clusters = cluster_episodes_by_news(features)
    pop_cmp = compare_pop_news(features)
    lit = literature_crosswalk()

    # coverage stats
    entity_max = entity["date"].max() if not entity.empty else None
    trig_in_entity = features[features["has_entity_coverage"]]
    trig_post_entity_gap = trig[trig["date"] > entity_max] if entity_max is not None else trig

    # entity-mention subset only
    ent_sub = features[features["has_entity_mention"]]
    entity_mention_pop = None
    if len(ent_sub) >= 30:
        entity_mention_pop = {
            "n": int(len(ent_sub)),
            "pop_rate_pct": round(float(ent_sub["got_pop"].mean() * 100), 1),
            "median_pre_mentions": float(ent_sub["pre_entity_mentions"].median()),
        }

    report = {
        "meta": {
            "n_triggers": int(len(trig)),
            "country_shock_date_min": str(country["date"].min().date()) if not country.empty else None,
            "country_shock_date_max": str(country["date"].max().date()) if not country.empty else None,
            "country_shock_days": int(len(country)),
            "entity_panel_max": str(entity_max.date()) if entity_max is not None else None,
            "triggers_with_entity_window": int(trig_in_entity["has_entity_coverage"].sum()),
            "triggers_after_entity_panel": int(len(trig_post_entity_gap)),
            "coverage_warning": "Entity GDELT dots end 2025-04; 2025-05+ fry episodes lack ticker-specific news dots.",
        },
        "country_shock_baseline": {
            "median_daily_dots": float(country["shock_dot_total"].median()) if not country.empty else None,
            "p90_daily_dots": float(country["shock_dot_total"].quantile(0.9)) if not country.empty else None,
            "theme_share_of_days": {
                c.replace("_rows", ""): round(float((country[c] > 0).mean()) * 100, 1) for c in SHOCK_COLS
            }
            if not country.empty
            else {},
        },
        "entity_mention_subset": entity_mention_pop,
        "episode_news_clusters": clusters,
        "pop_vs_no_pop_news": pop_cmp,
        "literature_crosswalk": lit,
        "sample_high_dot_triggers": sample_publication_dots(country, features),
        "synthesis": _synthesis(clusters, pop_cmp, features, entity_mention_pop),
    }

    features.to_parquet(OUT_DIR / "episode_gdelt_features.parquet", index=False)
    (OUT_DIR / "gdelt_literature_crossref.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def _synthesis(clusters: dict, pop_cmp: dict, features: pd.DataFrame, entity_mention_pop: dict | None) -> dict[str, Any]:
    cl = clusters.get("clusters", [])
    best_cluster = max(cl, key=lambda x: x["pop_rate_pct"]) if cl else None
    sig_news = [r for r in pop_cmp.get("pop_vs_no_pop_news", []) if r.get("fdr_q") is not None and r["fdr_q"] < 0.05]

    # Theme-level pop rates where n sufficient
    theme_pop = []
    if not features.empty:
        for theme, g in features.groupby("dominant_country_theme_pre", dropna=False):
            if len(g) < 50:
                continue
            theme_pop.append(
                {
                    "theme": str(theme),
                    "n": int(len(g)),
                    "pop_rate_pct": round(float(g["got_pop"].mean() * 100), 1),
                }
            )
        theme_pop.sort(key=lambda x: -x["pop_rate_pct"])

    return {
        "headline": "GDELT country dots provide macro context; ticker entity dots are sparse. Fry pop is price-microstructure led, with weak news augmentation.",
        "best_news_cluster_for_pop": best_cluster,
        "entity_mention_subset": entity_mention_pop,
        "fdr_significant_news_gaps": sig_news,
        "theme_pop_ranking": theme_pop[:6],
        "interpretation": [
            "Literature (Tetlock, EPU, Hassan) predicts topic-specific shocks move prices — we test whether shock-theme clusters precede fry pop.",
            "Country shock dot bursts weakly separate pop vs no-pop; drawdown-depth at trigger remains stronger (see robust_empirics_report.json).",
            "Indonesia publications (deep-research-report) frame stock-frying as governance/free-float issue — consistent with fry names being non-investable-core microcaps.",
            "Use entity panel for symbol dots; country panel for macro dot clusters (rupiah, policy, governance).",
        ],
    }
