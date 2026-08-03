#!/usr/bin/env python3
"""Post-hoc narrative context: why did this asset move this week?

Uses fused / ticker / crypto panels + high-priority URL samples.
Explanation layer only — not a forecast or causal claim.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

import importlib.util as _ilu
from pathlib import Path as _Path

_bspec = _ilu.spec_from_file_location("sr_bootstrap", _Path(__file__).resolve().parent / "_repo_bootstrap.py")
_bmod = _ilu.module_from_spec(_bspec)
_bspec.loader.exec_module(_bmod)
REPO = _bmod.repo_root_from_file(__file__)
FUSED_RUN = REPO / "data_lake/research_panels/cross_asset_fused/fused_20260610_v2"
TICKER_RUN = REPO / "data_lake/research_panels/ticker_news_market/ticker_20260610"
PROCESSED = REPO / "data_lake/news_shock_taxonomy/processed"
OUT = REPO / "backtests/outputs/explain_week_move"

MACRO_SHOCKS = [
    "political_instability",
    "governance_corruption",
    "financial_stress",
    "geopolitical_security",
    "macro_policy",
    "trade_supply_chain",
    "health",
    "natural_environment",
]
CRYPTO_EVENTS = [
    "event_regulation_enforcement",
    "event_security_exploit",
    "event_market_stress",
    "event_institutional_adoption",
]

# Historical associations from research sprints (weak priors for narrative text).
CHANNEL_HINTS = {
    "political_instability": "Often coincides with higher country equity volatility.",
    "governance_corruption": "Mixed return signal; governance-heavy weeks can weigh on sentiment.",
    "financial_stress": "Typically aligns with risk-off and higher vol.",
    "geopolitical_security": "Security/geopolitical headline weeks; watch vol more than direction.",
    "macro_policy": "Rate/fiscal/policy narrative; direction depends on surprise vs priced.",
    "trade_supply_chain": "Trade/supply-chain stress; export-heavy markets sensitive.",
    "health": "Health-shock weeks tended to show lower 4w country returns in horse-race work.",
    "natural_environment": "Disaster/climate headlines; episodic sector/country effects.",
    "event_regulation_enforcement": "Asia crypto regulation news: ETH headwind (esp. IND/HKG) in panel work.",
    "event_security_exploit": "Hack/exploit headlines: mixed; HKG exploit weeks leaned +ETH historically.",
    "event_market_stress": "Crypto stress headlines often coincided with lower subsequent BTC |return|.",
    "event_institutional_adoption": "Adoption headlines often coincided with muted BTC vol/returns.",
}


def _parse_week(s: str) -> pd.Timestamp:
    return pd.to_datetime(s).normalize() + pd.Timedelta(days=(4 - pd.to_datetime(s).weekday()) % 7)


def _z_hist(series: pd.Series, value: float) -> tuple[float, float]:
    s = pd.to_numeric(series, errors="coerce").dropna()
    if len(s) < 20 or not np.isfinite(value):
        return float("nan"), float("nan")
    mu, sd = s.mean(), s.std(ddof=0)
    z = (value - mu) / sd if sd > 0 else 0.0
    pct = float((s <= value).mean())
    return float(z), pct


def _col_name(shock: str, scope: str) -> str:
    if scope == "crypto":
        return f"{shock}_per_1k_crypto_rows"
    if scope == "entity":
        return f"{shock}_per_1k_entity_rows"
    return f"{shock}_per_1k_rows"


def _shock_rank(row: pd.Series, history: pd.DataFrame, cols: list[str], scope: str = "macro") -> list[dict]:
    ranked = []
    for shock in cols:
        col = _col_name(shock, scope)
        if col not in row.index or col not in history.columns:
            continue
        val = float(row[col]) if pd.notna(row[col]) else 0.0
        z, pct = _z_hist(history[col], val)
        ranked.append(
            {
                "channel": shock,
                "intensity": val,
                "z_vs_history": z,
                "percentile": pct,
                "hint": CHANNEL_HINTS.get(shock, ""),
            }
        )
    ranked.sort(key=lambda x: abs(x["z_vs_history"]) if np.isfinite(x["z_vs_history"]) else 0, reverse=True)
    return ranked


def _find_articles(week_end: pd.Timestamp, country: str | None, shocks: list[str], limit: int = 5) -> list[dict]:
    start = (week_end - pd.Timedelta(days=6)).date()
    end = week_end.date()
    shock_terms = set(shocks)
    rows: list[dict] = []
    for path in sorted(PROCESSED.glob("*/sample_high_priority.csv"), reverse=True):
        try:
            df = pd.read_csv(
                path,
                usecols=["date", "country_iso3", "canonical_url", "shock_hints", "source_domain", "tone_avg"],
                low_memory=False,
            )
        except Exception:
            continue
        df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date
        mask = (df["date"] >= start) & (df["date"] <= end)
        if country:
            mask &= df["country_iso3"].astype(str) == country
        sub = df[mask]
        if sub.empty:
            continue
        if shock_terms:
            hints = sub["shock_hints"].astype(str).str.lower()
            hit = False
            for s in shock_terms:
                hit = hit | hints.str.contains(s.replace("event_", "").replace("_enforcement", ""), na=False)
            sub = sub[hit] if hit.any() else sub
        for _, r in sub.head(limit).iterrows():
            rows.append(
                {
                    "date": str(r["date"]),
                    "country": str(r["country_iso3"]),
                    "url": str(r["canonical_url"]),
                    "domain": str(r.get("source_domain", "")),
                    "shock_hints": str(r.get("shock_hints", "")),
                    "tone_avg": float(r["tone_avg"]) if pd.notna(r.get("tone_avg")) else None,
                }
            )
        if len(rows) >= limit:
            break
    return rows[:limit]


def _move_label(ret: float) -> str:
    if not np.isfinite(ret):
        return "unknown"
    if ret > 0.02:
        return "up sharply"
    if ret > 0.005:
        return "up"
    if ret < -0.02:
        return "down sharply"
    if ret < -0.005:
        return "down"
    return "flat"


def explain_country(country: str, week_end: pd.Timestamp) -> dict:
    fused = pd.read_parquet(FUSED_RUN / "cross_asset_fused_primary_panel.parquet")
    fused["week_end"] = pd.to_datetime(fused["week_end"])
    hist = fused[fused["country_iso3"] == country].copy()
    row = hist[hist["week_end"] == week_end]
    if row.empty:
        raise SystemExit(f"No fused row for {country} week {week_end.date()}")
    row = row.iloc[0]
    ret = float(row.get("return_1w", np.nan))
    shocks = _shock_rank(row, hist, MACRO_SHOCKS)
    crypto = pd.read_parquet(FUSED_RUN / "country_week_crypto_news_panel.parquet")
    crypto["week_end"] = pd.to_datetime(crypto["week_end"])
    cr = crypto[(crypto["country_iso3"] == country) & (crypto["week_end"] == week_end)]
    crypto_hist = crypto[crypto["country_iso3"] == country]
    crypto_shocks = []
    if not cr.empty:
        crypto_shocks = _shock_rank(cr.iloc[0], crypto_hist, CRYPTO_EVENTS, scope="crypto")
    top = [s["channel"] for s in shocks[:3]]
    articles = _find_articles(week_end, country, top + [s["channel"] for s in crypto_shocks[:2]])
    return {
        "mode": "country_index",
        "asset": country,
        "benchmark": str(row.get("top_yahoo_symbols", "")),
        "week_end": str(week_end.date()),
        "return_1w": ret,
        "move": _move_label(ret),
        "news_days": int(row.get("news_days", 0)),
        "news_rows": int(row.get("news_rows", 0)),
        "mean_tone": float(row.get("mean_tone_weighted", np.nan)),
        "vix_close": float(row.get("vix_close", np.nan)) if "vix_close" in row.index else None,
        "macro_shocks": shocks[:6],
        "crypto_shocks": crypto_shocks[:4],
        "sample_articles": articles,
        "narrative": _build_narrative(country, ret, shocks, crypto_shocks, articles, kind="country"),
    }


def _norm_crypto(asset: str) -> str:
    a = asset.upper().strip()
    if a in {"BTC", "BITCOIN"}:
        return "BTC-USD"
    if a in {"ETH", "ETHEREUM"}:
        return "ETH-USD"
    if "-USD" not in a:
        return f"{a}-USD"
    return a


def explain_crypto(asset: str, week_end: pd.Timestamp) -> dict:
    asset = _norm_crypto(asset)
    global_p = pd.read_parquet(FUSED_RUN / "global_assets_week_panel.parquet")
    global_p["week_end"] = pd.to_datetime(global_p["week_end"])
    g = global_p[global_p["week_end"] == week_end]
    if g.empty:
        raise SystemExit(f"No global week {week_end.date()}")
    ret_col = f"global_{asset}_return_1w"
    ret = float(g.iloc[0][ret_col])
    crypto = pd.read_parquet(FUSED_RUN / "country_week_crypto_news_panel.parquet")
    crypto["week_end"] = pd.to_datetime(crypto["week_end"])
    asia = crypto.groupby("week_end", as_index=False)[[f"{e}_per_1k_crypto_rows" for e in CRYPTO_EVENTS]].sum()
    hist = asia.copy()
    row = asia[asia["week_end"] == week_end].iloc[0]
    shocks = _shock_rank(row, hist, CRYPTO_EVENTS, scope="crypto")
    by_country = []
    for iso in ["IND", "HKG", "CHN", "SGP", "KOR"]:
        sub = crypto[(crypto["country_iso3"] == iso) & (crypto["week_end"] == week_end)]
        if sub.empty:
            continue
        r = sub.iloc[0]
        reg = float(r.get("event_regulation_enforcement_per_1k_crypto_rows", 0))
        exp = float(r.get("event_security_exploit_per_1k_crypto_rows", 0))
        by_country.append({"country": iso, "regulation": reg, "exploit": exp})
    by_country.sort(key=lambda x: x["regulation"] + x["exploit"], reverse=True)
    top = [s["channel"] for s in shocks[:2]]
    articles = _find_articles(week_end, None, top, limit=6)
    return {
        "mode": "crypto",
        "asset": asset,
        "week_end": str(week_end.date()),
        "return_1w": ret,
        "move": _move_label(ret),
        "asia_crypto_shocks": shocks,
        "country_breakdown": by_country[:5],
        "sample_articles": articles,
        "narrative": _build_narrative(asset, ret, shocks, [], articles, kind="crypto"),
    }


def explain_global(asset: str, week_end: pd.Timestamp) -> dict:
    asset = asset.upper()
    global_p = pd.read_parquet(FUSED_RUN / "global_assets_week_panel.parquet")
    global_p["week_end"] = pd.to_datetime(global_p["week_end"])
    g = global_p[global_p["week_end"] == week_end]
    if g.empty:
        raise SystemExit(f"No global week {week_end.date()}")
    ret = float(g.iloc[0][f"global_{asset}_return_1w"])
    fused = pd.read_parquet(FUSED_RUN / "cross_asset_fused_primary_panel.parquet")
    fused["week_end"] = pd.to_datetime(fused["week_end"])
    wk = fused[fused["week_end"] == week_end]
    asia_macro = (
        wk.groupby("week_end", as_index=False)[[f"{s}_per_1k_rows" for s in MACRO_SHOCKS]].mean().iloc[0]
        if not wk.empty
        else None
    )
    shocks = []
    if asia_macro is not None:
        hist = fused.groupby("week_end")[[f"{s}_per_1k_rows" for s in MACRO_SHOCKS]].mean().reset_index()
        shocks = _shock_rank(asia_macro, hist, MACRO_SHOCKS)
    articles = _find_articles(week_end, None, [s["channel"] for s in shocks[:2]], limit=5)
    return {
        "mode": "global_equity",
        "asset": asset,
        "week_end": str(week_end.date()),
        "return_1w": ret,
        "move": _move_label(ret),
        "asia_avg_macro_shocks": shocks[:6],
        "sample_articles": articles,
        "narrative": _build_narrative(asset, ret, shocks, [], articles, kind="global"),
    }


def explain_symbol(symbol: str, week_end: pd.Timestamp) -> dict:
    symbol = symbol.upper()
    rets = pd.read_parquet(TICKER_RUN / "ticker_week_returns_panel.parquet")
    rets["week_end"] = pd.to_datetime(rets["week_end"])
    hist = rets[rets["yahoo_symbol"] == symbol].copy()
    row = hist[hist["week_end"] == week_end]
    if row.empty:
        raise SystemExit(f"No return row for {symbol} week {week_end.date()}")
    row = row.iloc[0]
    ret = float(row["return_1w"])
    country = str(row.get("country_iso3", ""))
    name = str(row.get("name", symbol))
    if name.lower() in {"nan", "none", ""}:
        name = symbol

    broadcast = pd.read_parquet(TICKER_RUN / "ticker_week_country_broadcast_panel.parquet")
    broadcast["week_end"] = pd.to_datetime(broadcast["week_end"])
    bhist = broadcast[broadcast["yahoo_symbol"] == symbol]
    brow = bhist[bhist["week_end"] == week_end]
    macro_shocks = []
    if not brow.empty:
        macro_shocks = _shock_rank(brow.iloc[0], bhist, MACRO_SHOCKS)

    entity_shocks = []
    entity_rows = 0
    ent_path = TICKER_RUN / "ticker_week_entity_news_panel.parquet"
    if ent_path.exists():
        ent = pd.read_parquet(ent_path)
        ent["week_end"] = pd.to_datetime(ent["week_end"])
        ehist = ent[ent["yahoo_symbol"] == symbol]
        erow = ehist[ehist["week_end"] == week_end]
        if not erow.empty:
            entity_rows = int(erow.iloc[0].get("entity_mention_rows", 0))
            entity_shocks = _shock_rank(erow.iloc[0], ehist, MACRO_SHOCKS, scope="entity")

    top = [s["channel"] for s in (entity_shocks or macro_shocks)[:3]]
    articles = _find_articles(week_end, country or None, top, limit=5)
    return {
        "mode": "stock",
        "asset": symbol,
        "name": name,
        "country_iso3": country,
        "week_end": str(week_end.date()),
        "return_1w": ret,
        "move": _move_label(ret),
        "country_broadcast_shocks": macro_shocks[:6],
        "entity_mention_rows": entity_rows,
        "entity_shocks": entity_shocks[:4],
        "sample_articles": articles,
        "narrative": _build_narrative(name or symbol, ret, macro_shocks, entity_shocks, articles, kind="stock"),
    }


def _build_narrative(
    label: str,
    ret: float,
    macro: list[dict],
    entity_or_crypto: list[dict],
    articles: list[dict],
    kind: str,
) -> str:
    lines = [
        f"{label} was {_move_label(ret)} ({ret * 100:+.2f}% that week).",
        "This is post-hoc context from GDELT taxonomy — plausible narrative, not proven causation.",
    ]
    if macro:
        top = macro[0]
        z = top.get("z_vs_history", float("nan"))
        if np.isfinite(z) and abs(z) >= 0.5:
            level = "Elevated" if z > 0 else "Unusually low"
            lines.append(
                f"{level} {top['channel'].replace('_', ' ')} news for this scope "
                f"(z={z:+.1f} vs own history, ~{top['percentile']:.0%} percentile)."
            )
            if top.get("hint"):
                lines.append(top["hint"])
    extra = entity_or_crypto
    if extra:
        t = extra[0]
        z = t.get("z_vs_history", float("nan"))
        if np.isfinite(z) and abs(z) >= 0.5:
            prefix = "Entity-level" if kind == "stock" else "Crypto"
            lines.append(f"{prefix} channel {t['channel'].replace('_', ' ')} also elevated (z={z:+.1f}).")
    if articles:
        lines.append("Sample headlines that week:")
        for a in articles[:3]:
            lines.append(f"  - [{a.get('country','?')}] {a['url']}")
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser(description="Explain a weekly move with news-shock context (crypto + stocks).")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--crypto", metavar="ASSET", help="e.g. BTC-USD, ETH-USD")
    g.add_argument("--country", metavar="ISO3", help="Country index, e.g. IND, HKG, JPN")
    g.add_argument("--symbol", metavar="TICKER", help="Yahoo symbol, e.g. 0700.HK")
    g.add_argument("--global", dest="global_asset", metavar="ASSET", help="e.g. SPY, IWM, EEM")
    p.add_argument("--week", required=True, help="Week ending date YYYY-MM-DD (any day in week ok)")
    p.add_argument("--json-out", type=Path, help="Optional output JSON path")
    args = p.parse_args()

    week_end = _parse_week(args.week)
    if args.crypto:
        result = explain_crypto(args.crypto, week_end)
    elif args.country:
        result = explain_country(args.country.upper(), week_end)
    elif args.symbol:
        result = explain_symbol(args.symbol, week_end)
    else:
        result = explain_global(args.global_asset, week_end)

    print(result["narrative"])
    print()
    print(json.dumps({k: v for k, v in result.items() if k != "narrative"}, indent=2, default=str))

    out_path = args.json_out
    if out_path is None:
        OUT.mkdir(parents=True, exist_ok=True)
        slug = re.sub(r"[^A-Za-z0-9]+", "_", result.get("asset", "asset"))
        out_path = OUT / f"{slug}_{week_end.strftime('%Y%m%d')}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(f"\nWrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
