"""Gather full-platform evidence for IDX operator LLM decisions.

Every section reports source path + whether data was found — no silent gaps.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
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
INDEX = "^JKSE"

PATHS = {
    "factor_screen": REPO / "backtests/outputs/platform/idn_factor_screen/latest.json",
    "entity_coverage": REPO / "backtests/outputs/platform/idn_entity_coverage/latest.json",
    "entity_panel": REPO / "data_lake/research_panels/ticker_news_market/ticker_20260611/ticker_week_entity_market_panel.parquet",
    "broadcast_panel": REPO / "data_lake/research_panels/ticker_news_market/ticker_20260610/ticker_week_country_broadcast_panel.parquet",
    "reddit_signals": REPO / "data_lake/sentiment/reddit_daily_signals.parquet",
    "public_sentiment": REPO / "data_lake/sentiment/idn_public_sentiment_latest.json",
    "processed_news": REPO / "data_lake/news_shock_taxonomy/processed",
    "position_sheet_json": REPO / "backtests/outputs/idn_weekly_position_sheet/latest.json",
}


def _src(path: Path, ok: bool, note: str = "") -> dict[str, Any]:
    return {"path": str(path), "available": ok, "note": note}


def _focus_tickers(manifest: dict[str, Any]) -> list[str]:
    focus: set[str] = set()
    for key in ("pick", "avoid", "watch", "movers_up", "movers_down", "spikes_5d"):
        for row in manifest.get(key, []):
            sym = row.get("ticker") or row.get("yahoo_symbol")
            if sym:
                focus.add(str(sym))
    for sym in ("BBCA.JK", "BBRI.JK", "BMRI.JK", "BRIS.JK", "TLKM.JK"):
        focus.add(sym)
    return sorted(focus)


def gather_factor_screen() -> dict[str, Any]:
    path = PATHS["factor_screen"]
    if not path.exists():
        return {"source": _src(path, False), "data": None}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {
        "source": _src(path, True),
        "span": raw.get("span"),
        "recommendation": raw.get("recommendation"),
        "sector_groups": raw.get("sector_group_effects", [])[:8],
        "ticker_mom_picks": raw.get("ticker_mom_picks", [])[:8],
        "ticker_mom_avoids": raw.get("ticker_mom_avoids", [])[:8],
        "ticker_attention_picks": raw.get("ticker_picks_oos", [])[:8],
        "ticker_attention_avoids": raw.get("ticker_avoids_oos", [])[:8],
        "top_factors": [
            {
                "factor": f.get("factor"),
                "verdict": f.get("verdict"),
                "ret_1w_full_t": f.get("ret_1w_full_t"),
                "ret_1w_2024_t": f.get("ret_1w_2024_t"),
            }
            for f in raw.get("factor_summary_liquid", [])[:12]
            if f.get("verdict") not in (None, "skip")
        ],
    }


def gather_research_empirics() -> dict[str, Any]:
    from idn_research_evidence import ARTIFACTS, LANES, gather_metrics, latest_winner_patterns_path, load_json

    metrics = gather_metrics()
    lanes = {
        k: {
            "title": v.get("title"),
            "hypothesis": v.get("hypothesis"),
            "kill_if": v.get("kill_if"),
            "status": "OFF" if k.startswith("off_") else "ACTIVE",
        }
        for k, v in LANES.items()
    }
    wp_path = latest_winner_patterns_path()
    winner = None
    if wp_path:
        wp = load_json(wp_path)
        if isinstance(wp, dict):
            wl = wp.get("winner_loser", {})
            winner = {
                "top10": wl.get("top10_tickers", [])[:10],
                "bottom10": wl.get("bottom10_tickers", [])[:10],
                "horse_race_oos": wp.get("strategy_horse_race_oos", [])[:6],
            }
    artifacts_present = {k: p.exists() for k, p in ARTIFACTS.items()}
    return {
        "metrics": metrics,
        "lanes": lanes,
        "winner_patterns": winner,
        "artifacts_present": artifacts_present,
        "winner_patterns_path": str(wp_path) if wp_path else None,
    }


def gather_entity_coverage() -> dict[str, Any]:
    path = PATHS["entity_coverage"]
    if not path.exists():
        return {"source": _src(path, False), "data": None}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {
        "source": _src(path, True),
        "plain_summary": raw.get("plain_summary"),
        "layers": raw.get("layers"),
        "entity_weeks_holdout": raw.get("entity_panel_liquid", {}).get("weeks_holdout"),
        "entity_holdout_cutoff": raw.get("entity_panel_liquid", {}).get("holdout_cutoff"),
    }


def gather_regime() -> dict[str, Any]:
    from idn_spike_explainer import fetch_history

    end = (datetime.now(UTC).date() + timedelta(days=1)).isoformat()
    start = (datetime.now(UTC).date() - timedelta(days=200)).isoformat()
    close, _ = fetch_history([INDEX], start, end)
    if close.empty or INDEX not in close.columns:
        return {"available": False}
    idx = close[INDEX].dropna()
    if len(idx) < 65:
        return {"available": False}
    last = float(idx.iloc[-1])
    high63 = float(idx.iloc[-63:].max())
    low20 = float(idx.iloc[-20:].min())
    low60 = float(idx.iloc[-60:].min())
    dd63 = last / high63 - 1.0
    bounce20 = last / low20 - 1.0
    ret5 = last / float(idx.iloc[-6]) - 1.0 if len(idx) >= 6 else None
    ret20 = last / float(idx.iloc[-21]) - 1.0 if len(idx) >= 21 else None

    regime = "neutral"
    if dd63 <= -0.10 and bounce20 < 0.08:
        regime = "washout"
    elif dd63 <= -0.10 and bounce20 >= 0.08:
        regime = "recovery"
    elif bounce20 >= 0.12 and ret5 is not None and ret5 >= 0.05:
        regime = "extended_bounce"

    return {
        "available": True,
        "as_of": str(idx.index[-1].date()),
        "dd_63d_pct": round(dd63 * 100, 2),
        "bounce_20d_pct": round(bounce20 * 100, 2),
        "ret_5d_pct": round(ret5 * 100, 2) if ret5 is not None else None,
        "ret_20d_pct": round(ret20 * 100, 2) if ret20 is not None else None,
        "dist_from_60d_low_pct": round((last / low60 - 1) * 100, 2),
        "regime_label": regime,
        "interpretation": {
            "washout": "Deep drawdown, bounce not extended → banks/core beta favored",
            "recovery": "Post-drawdown recovery in progress",
            "extended_bounce": "Sharp relief rally — chase risk elevated",
            "neutral": "No extreme regime flag",
        }.get(regime, ""),
    }


def gather_entity_news_layer(manifest: dict[str, Any], liquid: list[str]) -> dict[str, Any]:
    path = PATHS["entity_panel"]
    if not path.exists():
        return {"source": _src(path, False), "per_ticker": [], "country_week": None}

    focus = [t for t in _focus_tickers(manifest) if t in liquid]
    e = pd.read_parquet(path)
    e["week_end"] = pd.to_datetime(e["week_end"])
    e = e[(e["country_iso3"] == "IDN") & (e["yahoo_symbol"].isin(focus))].copy()
    if e.empty:
        return {"source": _src(path, True, "no rows for focus tickers"), "per_ticker": [], "country_week": None}

    last_week = e["week_end"].max()
    snap = e[e["week_end"] == last_week]
    cols = [
        "yahoo_symbol",
        "entity_mention_rows",
        "entity_news_days",
        "mean_tone_avg",
        "mean_market_relevance_score",
        "return_1w",
        "financial_stress_per_1k_entity_rows",
        "health_per_1k_entity_rows",
        "natural_environment_per_1k_entity_rows",
    ]
    per = []
    for _, r in snap.iterrows():
        row = {c: (None if pd.isna(r.get(c)) else float(r[c]) if c != "yahoo_symbol" else r[c]) for c in cols if c in snap.columns}
        per.append(row)

    # country broadcast aggregate for same week
    bpath = PATHS["broadcast_panel"]
    country_week = None
    if bpath.exists():
        b = pd.read_parquet(bpath)
        b["week_end"] = pd.to_datetime(b["week_end"])
        bl = b[(b["country_iso3"] == "IDN") & (b["yahoo_symbol"].isin(liquid))]
        if not bl.empty:
            wk = bl["week_end"].max()
            sub = bl[bl["week_end"] == wk]
            country_week = {
                "week_end": str(wk.date()),
                "liquid_names": int(sub["yahoo_symbol"].nunique()),
                "sum_news_rows": float(sub["news_rows"].sum()) if "news_rows" in sub.columns else None,
                "mean_return_1w_pct": round(float(sub["return_1w"].mean()) * 100, 2),
                "top_news_rows": sub.nlargest(5, "news_rows")[["yahoo_symbol", "news_rows", "return_1w"]].to_dict(orient="records")
                if "news_rows" in sub.columns
                else [],
            }

    from idn_eval_splits import time_cutoff

    holdout_cut = time_cutoff(e["week_end"])
    return {
        "source": _src(path, True),
        "entity_week_end": str(last_week.date()),
        "entity_holdout_cutoff": str(holdout_cut.date()),
        "entity_weeks_holdout": int(e[e["week_end"] >= holdout_cut]["week_end"].nunique()),
        "per_ticker": sorted(per, key=lambda x: -(x.get("entity_mention_rows") or 0))[:20],
        "country_week": country_week,
    }


def gather_retail_signals(liquid: list[str]) -> dict[str, Any]:
    from idn_retail_strategies import PLAYBOOK, build_all_signals
    from idn_spike_explainer import fetch_history

    end = (datetime.now(UTC).date() + timedelta(days=1)).isoformat()
    close, vol = fetch_history(liquid + [INDEX], "2024-06-01", end)
    if close.empty:
        return {"available": False}
    signals = build_all_signals(close, vol, liquid)
    last_dt = close.index[-1]
    active: list[dict[str, Any]] = []
    for strat in PLAYBOOK:
        hits = signals.get(strat.id, {}).get(last_dt, [])
        if hits:
            active.append(
                {
                    "id": strat.id,
                    "jargon": strat.retail_jargon,
                    "tickers": hits,
                    "hold_days": strat.hold_days,
                    "tags": strat.tags,
                }
            )
    return {
        "available": True,
        "as_of": str(last_dt.date()),
        "active_signals": active,
        "playbook_size": len(PLAYBOOK),
    }


def gather_spike_intelligence(manifest: dict[str, Any], liquid: list[str]) -> dict[str, Any]:
    from idn_bandar_lite import bandar_lite_features, bandar_lite_hypotheses
    from idn_spike_explainer import fetch_history, load_groups

    spikes = manifest.get("spikes_5d", [])[:8]
    if not spikes:
        return {"spikes": [], "groups": load_groups()}

    symbols = sorted({s["ticker"] for s in spikes if s["ticker"] in liquid})
    end = (datetime.now(UTC).date() + timedelta(days=1)).isoformat()
    close, vol = fetch_history(symbols, "2025-01-01", end)
    groups = load_groups()
    rows = []
    for sp in spikes[:6]:
        sym = sp["ticker"]
        dt = pd.Timestamp(sp["date"])
        item = dict(sp)
        if sym in close.columns and dt in close.index:
            bl = bandar_lite_features(close[sym], vol[sym] if sym in vol.columns else pd.Series(), dt)
            item["bandar_lite"] = bl
            item["bandar_hypotheses"] = bandar_lite_hypotheses({"bandar_lite": bl})
            for gname, meta in groups.items():
                if sym in meta.get("tickers", []):
                    item["theme_group"] = gname
                    break
        rows.append(item)
    return {"spikes": rows, "group_sync_note": "tactical_group_sync lane: spike +2 peers >=8% in theme"}


def gather_news_samples(limit: int = 8) -> dict[str, Any]:
    root = PATHS["processed_news"]
    if not root.exists():
        return {"source": _src(root, False), "articles": []}
    rows: list[dict] = []
    for path in sorted(root.glob("*/sample_high_priority.csv"), reverse=True):
        try:
            df = pd.read_csv(path, usecols=["date", "country_iso3", "canonical_url", "shock_hints"], nrows=5000)
        except Exception:
            continue
        sub = df[df["country_iso3"] == "IDN"].head(3)
        for _, r in sub.iterrows():
            rows.append(
                {
                    "date": str(r["date"]),
                    "url": str(r["canonical_url"]),
                    "shock_hints": str(r.get("shock_hints", ""))[:200],
                }
            )
        if len(rows) >= limit:
            break
    return {"source": _src(root, True), "articles": rows[:limit]}


def gather_public_sentiment(liquid: list[str]) -> dict[str, Any]:
    """IDX retail/public sentiment — RapidAPI trending, Reddit IDX, GDELT pulse, macro mood."""
    path = PATHS["public_sentiment"]
    if not path.exists():
        return {
            "source": _src(path, False),
            "ok": False,
            "reason": "not_collected",
            "hint": "Run: python scripts/idn_social_sentiment_collector.py",
            "ticker_pulse": [],
        }
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {"source": _src(path, True, str(exc)), "ok": False, "ticker_pulse": []}

    providers = raw.get("providers", {})
    catalog = {
        "rapidapi_trending": providers.get("rapidapi_trending", {}).get("ok", False),
        "rapidapi_market_flow": providers.get("rapidapi_market_flow", {}).get("ok", False),
        "rapidapi_symbol_intel": providers.get("rapidapi_symbol_intel", {}).get("ok", False),
        "reddit_idx": providers.get("reddit_idx", {}).get("ok", False),
        "stocktwits_macro": providers.get("stocktwits_macro", {}).get("ok", False),
        "gdelt_entity_pulse": providers.get("entity_mention_pulse", {}).get("ok", False),
    }
    pulse = [r for r in raw.get("ticker_pulse", []) if r.get("yahoo_symbol") in liquid]
    top = sorted(pulse, key=lambda x: -float(x.get("attention_score", 0)))[:20]
    return {
        "source": _src(path, True),
        "ok": True,
        "collected_at_utc": raw.get("collected_at_utc"),
        "provider_status": catalog,
        "retail_mood_macro": raw.get("retail_mood_macro"),
        "ticker_pulse": top,
        "notes": raw.get("notes"),
        "reddit_errors": providers.get("reddit_idx", {}).get("errors"),
        "reddit_sample_posts": (providers.get("reddit_idx", {}).get("posts") or [])[:5],
        "rapidapi_trending_top10": (providers.get("rapidapi_trending", {}).get("items") or [])[:10],
        "rapidapi_market_flow": {
            "top_broker_ok": (providers.get("rapidapi_market_flow", {}).get("top_broker") or {}).get("ok"),
            "top_stock_ok": (providers.get("rapidapi_market_flow", {}).get("top_stock") or {}).get("ok"),
        },
        "rapidapi_symbol_intel": (providers.get("rapidapi_symbol_intel", {}).get("symbols") or [])[:12],
        "capability_report": str(REPO / "backtests/outputs/platform/idn_rapidapi_capability/latest.json"),
    }


def gather_reddit_sentiment(liquid: list[str]) -> dict[str, Any]:
    """Legacy US reddit panel — kept for discovery scripts, not IDX operator."""
    path = PATHS["reddit_signals"]
    if not path.exists():
        return {"source": _src(path, False), "rows": []}
    try:
        df = pd.read_parquet(path)
    except Exception as exc:
        return {"source": _src(path, True, str(exc)), "rows": []}
    # flexible column detection
    sym_col = next((c for c in df.columns if "symbol" in c.lower() or c == "ticker"), None)
    if sym_col is None:
        return {"source": _src(path, True, "no symbol column"), "rows": []}
    sub = df[df[sym_col].isin(liquid)].copy()
    if "date" in sub.columns:
        sub["date"] = pd.to_datetime(sub["date"])
        sub = sub.sort_values("date").groupby(sym_col).tail(1)
    rows = sub.head(15).to_dict(orient="records")
    return {"source": _src(path, True), "rows": rows}


def gather_position_sheet_detail() -> dict[str, Any]:
    path = PATHS["position_sheet_json"]
    if not path.exists():
        return {"source": _src(path, False), "data": None}
    raw = json.loads(path.read_text(encoding="utf-8"))
    slim = {
        k: raw.get(k)
        for k in (
            "as_of_week",
            "regime",
            "weight_mode",
            "retail_active",
            "weights",
            "why",
            "avoid",
            "strategies_off",
            "retail_signals",
            "actions",
        )
        if k in raw
    }
    return {"source": _src(path, True), "data": slim}


def gather_full_platform_evidence(manifest: dict[str, Any], *, liquid: list[str]) -> dict[str, Any]:
    """Aggregate all platform lanes into one evidence object for the LLM."""
    sections = {
        "factor_screen": gather_factor_screen(),
        "research_empirics": gather_research_empirics(),
        "entity_coverage": gather_entity_coverage(),
        "regime_ihsg": gather_regime(),
        "entity_news_layer": gather_entity_news_layer(manifest, liquid),
        "retail_playbook_signals": gather_retail_signals(liquid),
        "spike_intelligence": gather_spike_intelligence(manifest, liquid),
        "news_headlines": gather_news_samples(),
        "public_sentiment": gather_public_sentiment(liquid),
        "reddit_us_legacy": gather_reddit_sentiment(liquid),
        "position_sheet_detail": gather_position_sheet_detail(),
    }
    catalog = []
    for name, block in sections.items():
        if isinstance(block, dict):
            src = block.get("source", {})
            if src:
                catalog.append({"section": name, **src})
            elif block.get("available") is False:
                catalog.append({"section": name, "available": False})
            else:
                catalog.append({"section": name, "available": True})
    return {
        "gathered_at_utc": datetime.now(UTC).isoformat(),
        "evidence_catalog": catalog,
        "sections": sections,
    }
