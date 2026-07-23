"""Actionable fry outputs: watchlist, publication dot case book, entity noise filter.

Keeps only what empirics supported:
  - price trigger score (drawdown depth + vol)
  - optional macro news-z boost (deep DD + elevated IDN shock z)
  - GDELT article URLs around exemplar pop episodes (qualitative dots)
"""

from __future__ import annotations

import json
import re
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
TURNAROUND = REPO / "data_lake/research_panels/idn_turnaround/daily_features.parquet"
NEWS_PROCESSED = REPO / "data_lake/news_shock_taxonomy/processed"
NOISE_CFG = REPO / "config/markets/indonesia_fry_entity_noise_tickers.json"
OUT_DIR = FRY_DIR

WINDOW_RE = re.compile(r"asia_gkg_window_(\d{8})_(\d{8})_")


def load_entity_noise_tickers() -> set[str]:
    if not NOISE_CFG.exists():
        return set()
    raw = json.loads(NOISE_CFG.read_text(encoding="utf-8"))
    return set(raw.get("yahoo_symbols", []))


def _window_for_date(dt: pd.Timestamp) -> Path | None:
    if not NEWS_PROCESSED.exists():
        return None
    best: Path | None = None
    for win in NEWS_PROCESSED.glob("asia_gkg_window_*"):
        m = WINDOW_RE.match(win.name)
        if not m:
            continue
        start = pd.Timestamp(m.group(1))
        end = pd.Timestamp(m.group(2))
        if start <= dt < end:
            best = win
    return best


def fetch_idn_publication_dots(start: pd.Timestamp, end: pd.Timestamp, *, limit: int = 25) -> list[dict[str, Any]]:
    """Pull GDELT article dots for IDN in date range (sample CSVs across windows)."""
    rows: list[dict[str, Any]] = []
    if not NEWS_PROCESSED.exists():
        return rows
    seen: set[str] = set()
    sample_names = ("sample_high_priority.csv", "sample_context.csv")
    usecols = {
        "date", "country_iso3", "shock_hints", "tone_avg", "canonical_url",
        "source_domain", "organizations", "themes", "market_relevance_bucket",
    }
    for win in sorted(NEWS_PROCESSED.glob("asia_gkg_window_*")):
        m = WINDOW_RE.match(win.name)
        if not m:
            continue
        wstart = pd.Timestamp(m.group(1))
        wend = pd.Timestamp(m.group(2))
        if wend < start or wstart > end:
            continue
        for fname in sample_names:
            path = win / fname
            if not path.exists():
                continue
            try:
                df = pd.read_csv(path, usecols=lambda c: c in usecols)
            except Exception:
                continue
            if df.empty or "country_iso3" not in df.columns:
                continue
            sub = df[df["country_iso3"] == "IDN"].copy()
            sub["date"] = pd.to_datetime(sub["date"], errors="coerce")
            sub = sub[(sub["date"] >= start) & (sub["date"] <= end)]
            for _, r in sub.sort_values("date").iterrows():
                url = str(r.get("canonical_url") or "")
                if not url or url in seen:
                    continue
                seen.add(url)
                rows.append({
                    "date": str(r["date"].date()) if pd.notna(r["date"]) else None,
                    "shock_hints": r.get("shock_hints"),
                    "tone_avg": round(float(r["tone_avg"]), 2) if pd.notna(r.get("tone_avg")) else None,
                    "source_domain": r.get("source_domain"),
                    "market_relevance": r.get("market_relevance_bucket"),
                    "url": url,
                    "organizations": str(r.get("organizations") or "")[:120],
                    "source_file": fname,
                })
                if len(rows) >= limit:
                    return rows
    return rows


def country_shock_cluster(start: pd.Timestamp, end: pd.Timestamp, country: pd.DataFrame) -> dict[str, Any]:
    """Macro dot cluster summary when article samples are sparse."""
    if country.empty:
        return {"n_days": 0}
    sub = country[(country["date"] >= start) & (country["date"] <= end)]
    if sub.empty:
        return {"n_days": 0}
    from idn_fry_gdelt_crossref_lib import SHOCK_COLS

    theme_totals = {c.replace("_rows", ""): int(sub[c].sum()) for c in SHOCK_COLS if c in sub.columns}
    dominant = max(theme_totals, key=theme_totals.get) if theme_totals else None
    return {
        "n_days": int(len(sub)),
        "total_shock_dots": int(sub["shock_dot_total"].sum()),
        "mean_daily_dots": round(float(sub["shock_dot_total"].mean()), 1),
        "dominant_theme": dominant,
        "theme_totals": theme_totals,
        "mean_tone": round(float(sub["mean_tone"].mean()), 2) if "mean_tone" in sub.columns else None,
    }


def _country_shock_z(country: pd.DataFrame, dt: pd.Timestamp) -> float:
    if country.empty or dt not in set(country["date"]):
        sub = country[country["date"] <= dt].tail(30)
    else:
        sub = country[country["date"] <= dt].tail(30)
    if sub.empty:
        return 0.0
    med = float(sub["shock_dot_total"].median())
    std = float(sub["shock_dot_total"].std()) or 1.0
    today = country.loc[country["date"] == dt, "shock_dot_total"]
    val = float(today.iloc[0]) if len(today) else med
    return round((val - med) / std, 3)


def _sink_risk_from_features(
    *,
    r5: float,
    vol: float,
    quiet: bool,
    vol_dd: bool,
    broker_ctx: dict[str, Any],
) -> tuple[int, str, list[str]]:
    """Sink/grind risk from bilateral empirics (not short signal — risk flag)."""
    flags: list[str] = []
    score = 0
    if quiet and not vol_dd:
        score += 35
        flags.append("quiet_only_high_false_positive")
    if r5 > -0.04 and vol >= 1.6:
        score += 25
        flags.append("shallow_dd_grind_risk")
    if r5 > -0.08:
        score += 10
        flags.append("not_deep_dd")
    tags = broker_ctx.get("broker_tags") or []
    if "foreign_sell_heavy" in tags:
        score += 20
        flags.append("foreign_sell_on_trigger")
    if "more_selling_brokers" in tags:
        score += 15
        flags.append("more_selling_brokers")
    if broker_ctx.get("broker_accdist") == "Dist" and "net_sell_value" in tags:
        score += 10
        flags.append("dist_plus_net_sell")
    if score >= 40:
        tier = "high"
    elif score >= 20:
        tier = "elevated"
    else:
        tier = "low"
    return score, tier, flags


def _load_symbol_prior_maps() -> tuple[dict[str, float], set[str]]:
    """Walk-forward symbol pop prior + dead-name blocklist from strategic indicator research."""
    frame_path = FRY_DIR / "strategic_indicator_frame.parquet"
    report_path = FRY_DIR / "strategic_indicator_report.json"
    prior_map: dict[str, float] = {}
    dead: set[str] = set()
    if report_path.exists():
        raw = json.loads(report_path.read_text(encoding="utf-8"))
        dead = set(raw.get("false_trigger_taxonomy", {}).get("dead_symbols_n20plus", []))
    if frame_path.exists():
        hist = pd.read_parquet(frame_path, columns=["yahoo_symbol", "got_pop", "date"])
        hist["date"] = pd.to_datetime(hist["date"])
        hist = hist.sort_values("date")
        rolling: dict[str, list[int]] = {}
        for _, row in hist.iterrows():
            sym = row["yahoo_symbol"]
            past = rolling.get(sym, [])
            if past:
                prior_map[sym] = float(np.mean(past))
            past.append(int(row["got_pop"]))
            rolling[sym] = past
    return prior_map, dead


def _load_structural_map() -> dict[str, dict[str, Any]]:
    path = FRY_DIR / "fry_structural_panel.parquet"
    if not path.exists():
        return {}
    try:
        df = pd.read_parquet(path)
        return df.set_index("yahoo_symbol").to_dict("index")
    except Exception:
        return {}


def _load_attention_map() -> dict[str, dict[str, Any]]:
    path = FRY_DIR / "fry_attention_panel.parquet"
    if not path.exists():
        return {}
    try:
        df = pd.read_parquet(path)
        return df.set_index("yahoo_symbol").to_dict("index")
    except Exception:
        return {}


def _load_technical_map() -> dict[str, dict[str, Any]]:
    path = FRY_DIR / "fry_technical_panel.parquet"
    if not path.exists():
        return {}
    try:
        df = pd.read_parquet(path)
        return df.set_index("yahoo_symbol").to_dict("index")
    except Exception:
        return {}


def build_watchlist(country: pd.DataFrame | None = None) -> list[dict[str, Any]]:
    """Latest-day fry symbols matching actionable pre-pop signature."""
    if not TURNAROUND.exists():
        return []
    cols = ["date", "yahoo_symbol", "name_type", "return_5d", "vol_ratio_20d", "return_1d", "bandar_lite_label", "rsi14", "dd_60d"]
    df = pd.read_parquet(TURNAROUND, columns=cols)
    df["date"] = pd.to_datetime(df["date"])
    noise = load_entity_noise_tickers()
    prior_map, dead_syms = _load_symbol_prior_maps()
    structural_map = _load_structural_map()
    attention_map = _load_attention_map()
    technical_map = _load_technical_map()
    latest_dt = df["date"].max()
    day = df[(df["date"] == latest_dt) & (df["name_type"] == "fry")].copy()

    if country is None:
        from idn_fry_gdelt_crossref_lib import load_idn_country_shocks

        country = load_idn_country_shocks()

    from idn_fry_outcome_certainty_lib import certainty_blurb_for_tier

    rows: list[dict[str, Any]] = []
    live_fetches = 0
    max_live_fetches = 5
    for _, r in day.iterrows():
        sym = r["yahoo_symbol"]
        if sym in dead_syms:
            continue
        r5 = float(r["return_5d"]) if pd.notna(r["return_5d"]) else 0.0
        vol = float(r["vol_ratio_20d"]) if pd.notna(r["vol_ratio_20d"]) else 0.0
        r1 = float(r["return_1d"]) if pd.notna(r["return_1d"]) else 0.0
        if r1 >= 0.08:
            continue
        vol_dd = vol >= 1.6 and r5 <= -0.04
        quiet = str(r.get("bandar_lite_label") or "") == "quiet_volume_build"
        if not (vol_dd or quiet):
            continue

        from idn_fry_pop_pattern_lib import score_fry_pop_row

        pop_score, pop_matched, pop_cause = score_fry_pop_row(r.to_dict())
        score = 0.0
        tier = "monitor"
        if r5 <= -0.12:
            score += 45
            tier = "high"
        elif r5 <= -0.08:
            score += 35
            tier = "elevated"
        elif vol_dd:
            score += 20
        else:
            score += 8
            tier = "low"

        if pop_score > 0:
            score += pop_score * 25
            if pop_score >= 2.0:
                tier = "high"
            elif pop_score >= 1.2 and tier not in ("high",):
                tier = "elevated"

        news_z = _country_shock_z(country, latest_dt) if not country.empty else 0.0
        if r5 <= -0.08 and news_z > 0.5:
            score += 10
            tier = "high" if tier != "low" else "elevated"

        sym_prior = prior_map.get(sym)
        if sym_prior is not None and sym_prior >= 0.25 and r5 <= -0.08 and vol >= 1.6:
            score += 15
            tier = "high" if tier in {"elevated", "high"} else "elevated"

        struct = structural_map.get(sym, {})
        free_float = struct.get("free_float_pct")
        struct_flags: list[str] = []
        if free_float is not None and pd.notna(free_float):
            if float(free_float) < 1.0:
                score += 10
                struct_flags.append("ultra_low_free_float")
            elif float(free_float) < 5.0:
                score += 5
                struct_flags.append("low_free_float")
            elif float(free_float) > 25.0:
                score -= 5
                struct_flags.append("high_free_float_less_fryable")
        if struct.get("is_watchlist_board"):
            score += 5
            struct_flags.append("watchlist_board")
        if struct.get("is_trading_limit"):
            score += 4
            struct_flags.append("trading_limit_index")
        if struct.get("is_acceleration_board"):
            score += 3
            struct_flags.append("acceleration_board")
        top_holder = struct.get("top_holder_pct")
        if top_holder is not None and pd.notna(top_holder) and float(top_holder) > 90.0:
            struct_flags.append("controller_gt_90pct")
        if struct.get("latest_insider_buy"):
            score += 3
            struct_flags.append("recent_controller_buy")
        if struct.get("controller_is_foreign"):
            struct_flags.append("foreign_controller")

        tech = technical_map.get(sym, {})
        api_rsi = tech.get("rsi")
        if tech.get("rsi_deep_oversold"):
            score += 8
            struct_flags.append("api_rsi_deep_oversold")
        elif tech.get("rsi_oversold"):
            score += 5
            struct_flags.append("api_rsi_oversold")
        sup_dist = tech.get("support_distance_pct")
        if sup_dist is not None and pd.notna(sup_dist) and float(sup_dist) <= 5.0:
            score += 3
            struct_flags.append("near_api_support")

        att = attention_map.get(sym, {})
        if att.get("in_trending_top50"):
            score -= 8
            struct_flags.append("already_trending_chase_risk")
        elif att.get("low_app_attention") or (att.get("app_followers") or 0) < 50_000:
            score += 3
            struct_flags.append("low_pre_pop_attention")

        broker_ctx: dict[str, Any] = {}
        try:
            from idn_bandar_collector import _cache_path, fetch_broker_summary_rapidapi
            from idn_fry_broker_lib import broker_context_for_symbol

            dstr = str(latest_dt.date())
            if tier in {"elevated", "high"} and live_fetches < max_live_fetches and not _cache_path(sym, dstr).exists():
                fetch_broker_summary_rapidapi(sym, dstr, use_cache=True)
                live_fetches += 1
            broker_ctx = broker_context_for_symbol(sym, dstr)
            if broker_ctx.get("available"):
                boost = int(broker_ctx.get("broker_score_boost") or 0)
                score += boost
                if boost >= 15 and tier in {"elevated", "monitor"}:
                    tier = "high"
                elif boost <= -10 and tier == "high":
                    tier = "elevated"
        except Exception:
            broker_ctx = {"available": False}

        sink_score, sink_tier, sink_flags = _sink_risk_from_features(
            r5=r5, vol=vol, quiet=quiet, vol_dd=vol_dd, broker_ctx=broker_ctx
        )

        if r5 <= -0.12:
            prior_txt = "~50% pop within 12d OOS; ~55% within 30d (T2)"
        elif r5 <= -0.08 and vol >= 1.6:
            prior_txt = "~42% pop within 12d OOS; ~50% within 30d (T1)"
        elif quiet:
            prior_txt = "~12% pop — quiet-only triggers mostly false"
        else:
            prior_txt = "~22% baseline — shallow trigger"

        rows.append({
            "yahoo_symbol": sym,
            "name_type": "fry",
            "as_of": str(latest_dt.date()),
            "return_5d_pct": round(r5 * 100, 2),
            "vol_ratio_20d": round(vol, 2),
            "bandar_lite_label": r.get("bandar_lite_label"),
            "rsi14": round(float(r["rsi14"]), 1) if pd.notna(r.get("rsi14")) else None,
            "dd_60d_pct": round(float(r["dd_60d"]) * 100, 1) if pd.notna(r.get("dd_60d")) else None,
            "country_news_z": news_z,
            "entity_noise_ticker": sym in noise,
            "action_score": int(score),
            "tier": tier,
            "symbol_pop_prior_wf": round(sym_prior * 100, 1) if sym_prior is not None else None,
            "broker_accdist": broker_ctx.get("broker_accdist"),
            "broker_tags": broker_ctx.get("broker_tags"),
            "broker_data_available": bool(broker_ctx.get("available")),
            "sink_risk_score": sink_score,
            "sink_risk_tier": sink_tier,
            "sink_risk_flags": sink_flags,
            "free_float_pct": round(float(free_float), 2) if free_float is not None and pd.notna(free_float) else None,
            "listing_board": struct.get("listing_board"),
            "top_holder_pct": round(float(top_holder), 2) if top_holder is not None and pd.notna(top_holder) else None,
            "app_followers": struct.get("app_followers"),
            "trending_rank": att.get("trending_rank"),
            "api_rsi": round(float(api_rsi), 1) if api_rsi is not None and pd.notna(api_rsi) else None,
            "api_overall_trend": tech.get("overall_trend"),
            "structural_flags": struct_flags,
            "historical_pop_rate_prior": prior_txt,
            "outcome_certainty_menu": certainty_blurb_for_tier(t1=(r5 <= -0.08 and vol >= 1.6)),
            "multi_year_pop_score": pop_score,
            "matched_pop_patterns": pop_matched[:5],
            "pop_trigger_cause": pop_cause,
            "note": "Monitor for ARA pop day (0-30d window) — not a hold signal.",
        })
    rows.sort(key=lambda x: -x["action_score"])
    return rows


def build_pop_case_book(n: int = 8) -> list[dict[str, Any]]:
    """Exemplar popped episodes with GDELT publication dots (macro context)."""
    from idn_fry_gdelt_crossref_lib import load_idn_country_shocks

    country = load_idn_country_shocks()
    ep_path = FRY_DIR / "fry_episodes.parquet"
    if not ep_path.exists():
        return []
    ep = pd.read_parquet(ep_path)
    ep["trigger_date"] = pd.to_datetime(ep["trigger_date"])
    ep["pop_date"] = pd.to_datetime(ep["pop_date"], errors="coerce")
    noise = load_entity_noise_tickers()
    pop = ep[ep["pop_date"].notna() & ~ep["yahoo_symbol"].isin(noise)].copy()
    pop = pop[(pop["pop_return_1d_pct"] >= 12) & (pop["pop_return_1d_pct"] <= 45)]
    # GDELT sample_high_priority currently through ~2026-05; prefer in-coverage episodes for dots
    covered = pop[pop["trigger_date"] <= pd.Timestamp("2025-04-30")]
    pool = covered if len(covered) >= n else pop
    pool = pool.sort_values("trigger_date", ascending=False)

    # diversify symbols
    picked: list[pd.Series] = []
    seen_sym: set[str] = set()
    for _, row in pool.iterrows():
        if row["yahoo_symbol"] in seen_sym:
            continue
        picked.append(row)
        seen_sym.add(row["yahoo_symbol"])
        if len(picked) >= n:
            break

    cases: list[dict[str, Any]] = []
    for row in picked:
        t0 = row["trigger_date"]
        pop_dt = row["pop_date"]
        dots = fetch_idn_publication_dots(t0 - pd.Timedelta(days=3), pop_dt + pd.Timedelta(days=2), limit=8)
        macro_cluster = country_shock_cluster(t0 - pd.Timedelta(days=7), pop_dt + pd.Timedelta(days=2), country)
        cases.append({
            "yahoo_symbol": row["yahoo_symbol"],
            "trigger_date": str(t0.date()),
            "pop_date": str(pop_dt.date()),
            "trigger_to_pop_days": int(row["trigger_to_pop_days"]) if pd.notna(row["trigger_to_pop_days"]) else None,
            "pop_return_1d_pct": float(row["pop_return_1d_pct"]),
            "max_fwd_5d_from_trigger_pct": float(row["max_fwd_5d_from_trigger_pct"])
            if pd.notna(row.get("max_fwd_5d_from_trigger_pct"))
            else None,
            "idn_publication_dots": dots,
            "dot_cluster_summary": _summarize_dots(dots),
            "idn_macro_shock_cluster": macro_cluster,
        })
    return cases


def _summarize_dots(dots: list[dict[str, Any]]) -> dict[str, Any]:
    if not dots:
        return {"n": 0}
    hints: dict[str, int] = {}
    for d in dots:
        for h in str(d.get("shock_hints") or "").split("|"):
            h = h.strip()
            if h:
                hints[h] = hints.get(h, 0) + 1
    top = sorted(hints.items(), key=lambda x: -x[1])[:4]
    return {
        "n": len(dots),
        "dominant_shock_hints": [k for k, _ in top],
        "median_tone": round(float(np.median([d["tone_avg"] for d in dots if d.get("tone_avg") is not None])), 2)
        if any(d.get("tone_avg") is not None for d in dots)
        else None,
    }


def entity_noise_impact() -> dict[str, Any]:
    """Before/after excluding generic-word ticker false entity dots."""
    from idn_fry_gdelt_crossref_lib import load_entity_daily

    noise = load_entity_noise_tickers()
    ent = load_entity_daily()
    if ent.empty:
        return {"sufficient": False}
    feat = pd.read_parquet(FRY_DIR / "episode_gdelt_features.parquet")
    merged = feat.merge(
        ent.groupby("yahoo_symbol")["entity_mention_rows"].sum().rename("lifetime_entity_rows"),
        on="yahoo_symbol",
        how="left",
    )
    merged["lifetime_entity_rows"] = merged["lifetime_entity_rows"].fillna(0)
    clean = merged[~merged["yahoo_symbol"].isin(noise)]
    noisy = merged[merged["yahoo_symbol"].isin(noise)]
    return {
        "noise_tickers": sorted(noise),
        "episodes_on_noise_tickers": int(len(noisy)),
        "pop_rate_noise_tickers_pct": round(float(noisy["got_pop"].mean() * 100), 1) if len(noisy) else None,
        "pop_rate_clean_tickers_pct": round(float(clean["got_pop"].mean() * 100), 1) if len(clean) else None,
        "pop_rate_clean_with_entity_mention_pct": round(
            float(clean[clean["has_entity_mention"]]["got_pop"].mean() * 100), 1
        )
        if (clean["has_entity_mention"]).any()
        else None,
        "interpretation": "After removing generic-word tickers, entity mention subset is more trustworthy for case studies.",
    }


def build_actionable_pack() -> dict[str, Any]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    from idn_fry_ara_alert_lib import build_ara_alert_pack
    from idn_fry_best_pick_lib import pick_best_fry_candidates
    from idn_fry_gdelt_crossref_lib import load_idn_country_shocks
    from idn_fry_outcome_certainty_lib import certainty_blurb_for_tier

    country = load_idn_country_shocks()
    watchlist = build_watchlist(country)
    best_picks = pick_best_fry_candidates(watchlist, top_k=3)
    ara_pack = build_ara_alert_pack(watchlist=watchlist)
    certainty_blurb = certainty_blurb_for_tier(t1=True)
    cases = build_pop_case_book()
    noise_report = entity_noise_impact()

    bilateral_path = OUT_DIR / "fry_bilateral_report.json"
    playbook = {}
    if bilateral_path.exists():
        playbook = json.loads(bilateral_path.read_text(encoding="utf-8")).get("playbook", {})

    pack = {
        "generated": pd.Timestamp.utcnow().isoformat(),
        "watchlist": watchlist,
        "watchlist_summary": {
            "n": len(watchlist),
            "high_tier": sum(1 for w in watchlist if w["tier"] == "high"),
            "elevated_tier": sum(1 for w in watchlist if w["tier"] == "elevated"),
            "high_sink_risk": sum(1 for w in watchlist if w.get("sink_risk_tier") == "high"),
        },
        "pop_case_book": cases,
        "entity_noise_filter": noise_report,
        "fry_playbook_summary": playbook,
        "outcome_certainty_blurb": certainty_blurb,
        "ara_alerts": ara_pack,
        "best_picks": best_picks,
        "usage": {
            "watchlist": "Pre-pop monitors — alert for ARA pop day (0-30d). 0% weight.",
            "best_picks": "Gated top-3 selective fry checks — hard pass/fail + rank score.",
            "ara_alerts": "Today's ARA/pop session flags on watched names — 0% weight, not close-entry.",
            "outcome_certainty": "Historical win/loss menu: pop vs stagnant vs sink vs grind.",
            "sink_risk": "Bilateral sink/grind flags — do not hold from trigger; not a short signal.",
            "case_book": "Recent pops with IDN GDELT dots (macro context).",
            "scoring": "pop action_score = DD depth + symbol prior + broker; sink_risk_score = quiet/shallow/foreign sell.",
        },
    }
    (OUT_DIR / "fry_actionable_pack.json").write_text(json.dumps(pack, indent=2) + "\n", encoding="utf-8")
    return pack


TIER_RANK = {"high": 3, "elevated": 2, "monitor": 1, "low": 0}


def load_fry_watch_monitors(*, min_tier: str = "monitor", rebuild: bool = False) -> list[dict[str, Any]]:
    """Load fry pre-pop monitors for weekly sheet — never assigns portfolio weight."""
    path = OUT_DIR / "fry_actionable_pack.json"
    if rebuild or not path.exists():
        build_actionable_pack()
    pack = json.loads(path.read_text(encoding="utf-8"))
    floor = TIER_RANK.get(min_tier, 1)
    monitors = [w for w in pack.get("watchlist", []) if TIER_RANK.get(w.get("tier", "low"), 0) >= floor]
    for m in monitors:
        m["watch_only"] = True
        m["target_weight"] = 0.0
    return monitors
