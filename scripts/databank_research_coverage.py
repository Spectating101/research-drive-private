#!/usr/bin/env python3
"""Research-axis databank coverage + synthesis proxy catalog (no UI, no partition lanes).

Scores geography × research-capability cells from probed panels and registry metadata.
Emits JSON + markdown with heatmap, time-depth bars, join-graph stats, and synthesis recipes.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO / "kernel") not in sys.path:
    sys.path.insert(0, str(REPO / "kernel"))

from sharpe_kernel.paths import repo_root_from_file

ROOT = repo_root_from_file(__file__)

# 0=absent 1=thin/metadata 2=partial 3=thick instant panel
SCORE_LABEL = {0: "—", 1: "thin", 2: "partial", 3: "strong"}

CAPABILITIES = [
    "daily_prices",
    "country_news_shocks",
    "entity_news_shocks",
    "fundamentals",
    "estimates_revisions",
    "index_pit_survivorship",
    "risk_overlay",
    "entity_join_gdelt_ric",
    "governance_regulatory",
    "social_sentiment",
    "onchain_crypto",
]

GEOGRAPHIES = [
    "US",
    "Taiwan",
    "Indonesia",
    "Japan",
    "Korea",
    "HK_SG_ASEAN",
    "Asia_multi_13",
    "Crypto_global",
    "Macro_global",
]


def _stamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _try_import_pandas():
    import pandas as pd

    return pd


def _read_parquet(path: Path, pd: Any):
    if not path.exists():
        return None
    return pd.read_parquet(path)


def _probe_panels(pd: Any) -> dict[str, Any]:
    """Load key panels; return numeric facts for scoring."""
    facts: dict[str, Any] = {"paths": {}, "missing": []}

    def load(rel: str, key: str) -> Any:
        p = ROOT / rel
        facts["paths"][key] = str(p)
        if not p.exists():
            facts["missing"].append(key)
            return None
        return pd.read_parquet(p)

    spine = load(
        "data_lake/research_panels/refinitiv/2026-07-06-complete/entity_market_spine.parquet",
        "entity_spine",
    )
    pit = load(
        "data_lake/refinitiv_backfill/2026-07-06-complete/processed/index_membership_pit.parquet",
        "pit",
    )
    est = load(
        "data_lake/research_panels/refinitiv/2026-07-06-complete/estimate_revision_panel.parquet",
        "estimate_rev",
    )
    fund = load(
        "data_lake/research_panels/refinitiv/2026-07-06-complete/fundamental_annual_panel.parquet",
        "fund_annual",
    )
    idn = load("data_lake/research_panels/idn_fry_episode/daily_cross_section.parquet", "idn_daily")
    idn_gdelt = load(
        "data_lake/research_panels/idn_fry_episode/episode_gdelt_features.parquet",
        "idn_gdelt",
    )
    asia = load(
        "data_lake/research_panels/asia_news_market/asia_news_market_auto_latest/"
        "asia_country_week_news_market_primary_panel.parquet",
        "asia_week",
    )
    cross = load(
        "data_lake/research_panels/cross_asset_fused/fused_20260610_v2/"
        "cross_asset_fused_primary_panel.parquet",
        "cross_asset",
    )
    ticker_shock = load(
        "data_lake/research_panels/ticker_news_market/ticker_20260615/"
        "daily_ticker_entity_shock_panel.parquet",
        "ticker_shock",
    )

    if spine is not None:
        bridged = int(spine["gdelt_entity_id"].notna().sum()) if "gdelt_entity_id" in spine.columns else 0
        facts["spine_rics"] = len(spine)
        facts["spine_gdelt_bridged"] = bridged
        facts["spine_bridge_pct"] = round(100.0 * bridged / max(len(spine), 1), 1)
        for col in [c for c in spine.columns if c.startswith("in_")]:
            facts[f"spine_{col}"] = int(spine[col].sum())

    if pit is not None:
        facts["pit_by_index"] = pit["index_ric"].value_counts().to_dict()
        facts["pit_rows"] = len(pit)
        if "as_of_date" in pit.columns:
            facts["pit_date_min"] = str(pit["as_of_date"].min())
            facts["pit_date_max"] = str(pit["as_of_date"].max())

    if est is not None and spine is not None:
        merged = est.merge(spine[["ric", "country_code"]], on="ric", how="left")
        facts["estimate_rev_rows"] = len(est)
        facts["estimate_rev_rics"] = int(est["ric"].nunique())
        facts["estimate_rev_by_country"] = merged["country_code"].value_counts().head(12).to_dict()
        if "date" in est.columns:
            facts["estimate_rev_date_min"] = str(est["date"].min())
            facts["estimate_rev_date_max"] = str(est["date"].max())

    if fund is not None:
        facts["fund_annual_rows"] = len(fund)
        facts["fund_annual_rics"] = int(fund["ric"].nunique())

    if idn is not None:
        facts["idn_daily_rows"] = len(idn)
        facts["idn_tickers"] = int(idn["yahoo_symbol"].nunique())
        facts["idn_date_min"] = str(idn["date"].min())
        facts["idn_date_max"] = str(idn["date"].max())

    if idn_gdelt is not None:
        facts["idn_gdelt_episodes"] = len(idn_gdelt)

    for key, df, week_col in [
        ("asia_week", asia, "week_end"),
        ("cross_asset", cross, "week_end"),
    ]:
        if df is not None:
            facts[f"{key}_rows"] = len(df)
            facts[f"{key}_countries"] = sorted(df["country_iso3"].unique().tolist()) if "country_iso3" in df.columns else []
            if week_col in df.columns:
                facts[f"{key}_week_min"] = str(df[week_col].min())
                facts[f"{key}_week_max"] = str(df[week_col].max())
                facts[f"{key}_weeks"] = int(df[week_col].nunique())

    if ticker_shock is not None:
        facts["ticker_shock_rows"] = len(ticker_shock)
        facts["ticker_shock_days"] = int(ticker_shock["date"].nunique()) if "date" in ticker_shock.columns else 0
        sym_col = next(
            (c for c in ("ticker", "yahoo_symbol", "ric", "exchange_ticker") if c in ticker_shock.columns),
            None,
        )
        facts["ticker_shock_tickers"] = int(ticker_shock[sym_col].nunique()) if sym_col else 0
        if "date" in ticker_shock.columns:
            facts["ticker_shock_date_min"] = str(ticker_shock["date"].min())
            facts["ticker_shock_date_max"] = str(ticker_shock["date"].max())

    alpha = ROOT / "data_lake/daily_alpha_panel.csv"
    if alpha.exists():
        ap = pd.read_csv(alpha)
        facts["alpha_panel_rows"] = len(ap)
        if "Instrument" in ap.columns:
            facts["alpha_instruments"] = int(ap["Instrument"].nunique())

    return facts


def _score_matrix(facts: dict[str, Any]) -> dict[str, dict[str, int]]:
    """Hand-tuned from probed facts; 0–3 per cell."""
    m = {g: {c: 0 for c in CAPABILITIES} for g in GEOGRAPHIES}

    # US
    m["US"]["daily_prices"] = 2  # yfinance alpha + refinitiv sample, not full CRSP
    m["US"]["country_news_shocks"] = 1
    m["US"]["entity_news_shocks"] = 1  # 4 SPX bridged; ticker shock slice thin
    m["US"]["fundamentals"] = 2
    m["US"]["estimates_revisions"] = 3
    m["US"]["index_pit_survivorship"] = 3
    m["US"]["risk_overlay"] = 2
    m["US"]["entity_join_gdelt_ric"] = 1
    m["US"]["governance_regulatory"] = 2  # SEC EDGAR lane
    m["US"]["social_sentiment"] = 1
    m["US"]["onchain_crypto"] = 2

    # Indonesia — deepest non-US equity lane
    m["Indonesia"]["daily_prices"] = 3
    m["Indonesia"]["country_news_shocks"] = 2
    m["Indonesia"]["entity_news_shocks"] = 2
    m["Indonesia"]["fundamentals"] = 2
    m["Indonesia"]["estimates_revisions"] = 2
    m["Indonesia"]["index_pit_survivorship"] = 3
    m["Indonesia"]["risk_overlay"] = 2  # bandar_lite in idn panel
    m["Indonesia"]["entity_join_gdelt_ric"] = 2
    m["Indonesia"]["governance_regulatory"] = 2
    m["Indonesia"]["social_sentiment"] = 2
    m["Indonesia"]["onchain_crypto"] = 1

    # Taiwan
    m["Taiwan"]["daily_prices"] = 2
    m["Taiwan"]["country_news_shocks"] = 2
    m["Taiwan"]["entity_news_shocks"] = 1
    m["Taiwan"]["fundamentals"] = 1
    m["Taiwan"]["estimates_revisions"] = 2
    m["Taiwan"]["index_pit_survivorship"] = 3
    m["Taiwan"]["risk_overlay"] = 1
    m["Taiwan"]["entity_join_gdelt_ric"] = 1
    m["Taiwan"]["governance_regulatory"] = 2  # MOPS/TWSE connectors
    m["Taiwan"]["social_sentiment"] = 1
    m["Taiwan"]["onchain_crypto"] = 1

    # Japan / Korea — PIT + revisions moderate, IDN-scale microstructure absent
    for geo, cc_est, pit_key in [
        ("Japan", "JP", "spine_in_n225"),
        ("Korea", "KR", "spine_in_ks11"),
    ]:
        m[geo]["daily_prices"] = 2
        m[geo]["country_news_shocks"] = 2
        m[geo]["entity_news_shocks"] = 1
        m[geo]["fundamentals"] = 1
        m[geo]["estimates_revisions"] = 2
        m[geo]["index_pit_survivorship"] = 3
        m[geo]["risk_overlay"] = 1
        m[geo]["entity_join_gdelt_ric"] = 1
        m[geo]["governance_regulatory"] = 1
        m[geo]["social_sentiment"] = 1
        m[geo]["onchain_crypto"] = 1

    # HK / SG / ASEAN hub
    m["HK_SG_ASEAN"]["daily_prices"] = 2
    m["HK_SG_ASEAN"]["country_news_shocks"] = 2
    m["HK_SG_ASEAN"]["entity_news_shocks"] = 1
    m["HK_SG_ASEAN"]["fundamentals"] = 1
    m["HK_SG_ASEAN"]["estimates_revisions"] = 2
    m["HK_SG_ASEAN"]["index_pit_survivorship"] = 2  # STI in PIT; HK not index in pit set
    m["HK_SG_ASEAN"]["risk_overlay"] = 1
    m["HK_SG_ASEAN"]["entity_join_gdelt_ric"] = 1
    m["HK_SG_ASEAN"]["governance_regulatory"] = 1
    m["HK_SG_ASEAN"]["social_sentiment"] = 1
    m["HK_SG_ASEAN"]["onchain_crypto"] = 1

    # Asia multi-country fused panels
    m["Asia_multi_13"]["daily_prices"] = 2
    m["Asia_multi_13"]["country_news_shocks"] = 3
    m["Asia_multi_13"]["entity_news_shocks"] = 2
    m["Asia_multi_13"]["fundamentals"] = 1
    m["Asia_multi_13"]["estimates_revisions"] = 1
    m["Asia_multi_13"]["index_pit_survivorship"] = 2
    m["Asia_multi_13"]["risk_overlay"] = 2
    m["Asia_multi_13"]["entity_join_gdelt_ric"] = 2
    m["Asia_multi_13"]["governance_regulatory"] = 1
    m["Asia_multi_13"]["social_sentiment"] = 1
    m["Asia_multi_13"]["onchain_crypto"] = 2

    m["Crypto_global"]["daily_prices"] = 2
    m["Crypto_global"]["country_news_shocks"] = 2
    m["Crypto_global"]["entity_news_shocks"] = 2
    m["Crypto_global"]["fundamentals"] = 0
    m["Crypto_global"]["estimates_revisions"] = 0
    m["Crypto_global"]["index_pit_survivorship"] = 0
    m["Crypto_global"]["risk_overlay"] = 2
    m["Crypto_global"]["entity_join_gdelt_ric"] = 2
    m["Crypto_global"]["governance_regulatory"] = 1
    m["Crypto_global"]["social_sentiment"] = 2
    m["Crypto_global"]["onchain_crypto"] = 3

    m["Macro_global"]["daily_prices"] = 2
    m["Macro_global"]["country_news_shocks"] = 2
    m["Macro_global"]["entity_news_shocks"] = 1
    m["Macro_global"]["fundamentals"] = 0
    m["Macro_global"]["estimates_revisions"] = 0
    m["Macro_global"]["index_pit_survivorship"] = 0
    m["Macro_global"]["risk_overlay"] = 1
    m["Macro_global"]["entity_join_gdelt_ric"] = 0
    m["Macro_global"]["governance_regulatory"] = 0
    m["Macro_global"]["social_sentiment"] = 0
    m["Macro_global"]["onchain_crypto"] = 1

    return m


def _time_depth(facts: dict[str, Any]) -> list[dict[str, Any]]:
    rows = [
        {
            "source": "Refinitiv estimate revisions",
            "start": facts.get("estimate_rev_date_min"),
            "end": facts.get("estimate_rev_date_max"),
            "entities": facts.get("estimate_rev_rics"),
            "note": "222 RICs; US-heavy",
        },
        {
            "source": "Refinitiv index membership PIT",
            "start": facts.get("pit_date_min"),
            "end": facts.get("pit_date_max"),
            "entities": 6,
            "note": ".SPX .JKSE .TWII .N225 .KS11 .STI",
        },
        {
            "source": "IDN FRY daily cross-section",
            "start": facts.get("idn_date_min"),
            "end": facts.get("idn_date_max"),
            "entities": facts.get("idn_tickers"),
            "note": "635 IDX yahoo symbols",
        },
        {
            "source": "Asia country-week news+market",
            "start": facts.get("asia_week_week_min"),
            "end": facts.get("asia_week_week_max"),
            "entities": len(facts.get("asia_week_countries") or []),
            "note": "13 ISO3 countries",
        },
        {
            "source": "Cross-asset fused primary",
            "start": facts.get("cross_asset_week_min"),
            "end": facts.get("cross_asset_week_max"),
            "entities": len(facts.get("cross_asset_countries") or []),
            "note": "112 feature cols",
        },
        {
            "source": "Daily ticker entity shock (slice)",
            "start": facts.get("ticker_shock_date_min"),
            "end": facts.get("ticker_shock_date_max"),
            "entities": facts.get("ticker_shock_tickers"),
            "note": f"{facts.get('ticker_shock_days', 0)} trading days only",
        },
        {
            "source": "GDELT normalized bulk",
            "start": "2015",
            "end": "2026",
            "entities": None,
            "note": "~165 GiB events/GKG; not all rolled to instant country CSV",
        },
    ]
    return rows


def _synthesis_catalog(facts: dict[str, Any]) -> list[dict[str, Any]]:
    bridge_pct = facts.get("spine_bridge_pct", 0)
    return [
        {
            "id": "jkse_pit_idn_microstructure_revisions",
            "title": "JKSE PIT universe × IDN microstructure × estimate revisions",
            "status": "built",
            "inputs": [
                "refinitiv_index_membership_pit (.JKSE)",
                "idn_fry_daily_cross_section",
                "refinitiv_estimate_revision_panel",
                "refinitiv_entity_market_spine (country_code=ID)",
            ],
            "output_grain": "ric × as_of_month",
            "output_path": "data_lake/research_panels/jkse_pit_idn/jkse_pit_idn_microstructure_revisions.parquet",
            "join_keys": ["constituent_ric", "yahoo_symbol", "as_of_month"],
            "assumptions": [
                "JKSE PIT membership defines investable IDX set at rebalance.",
                "IDN FRY bandar/volume features proxy local informed-flow regime.",
                "Refinitiv revisions for ID names reflect sell-side reaction to same regime.",
            ],
            "known_bias": "RIC↔yahoo symbol map needed; no GDELT entity bridge required.",
            "priority": "high",
        },
        {
            "id": "pit_survivorship_revision_momentum",
            "title": "PIT survivorship × estimate revision momentum factor",
            "status": "built",
            "inputs": [
                "refinitiv_index_membership_pit",
                "refinitiv_estimate_revision_panel",
                "refinitiv_entity_market_spine",
            ],
            "output_grain": "index_ric × constituent_ric × as_of_month",
            "output_path": "data_lake/research_panels/pit_revision_momentum/pit_index_revision_momentum.parquet",
            "join_keys": ["constituent_ric", "date", "index_ric"],
            "assumptions": [
                "Revision momentum is a valid alpha signal within PIT-filtered universes.",
            ],
            "known_bias": "Pure institutional lane; no event overlay.",
            "priority": "high",
        },
        {
            "id": "gdelt_shock_to_estimate_revision",
            "title": "GDELT entity shock → analyst revision response",
            "status": "recipe",
            "inputs": [
                "daily_ticker_entity_shock_panel (extend history)",
                "refinitiv_entity_market_spine",
                "refinitiv_estimate_revision_panel",
                "refinitiv_index_membership_pit",
            ],
            "output_grain": "ric × shock_event × window_day",
            "join_keys": ["ric", "shock_date", "gdelt_entity_id"],
            "assumptions": [
                "Entity bridge from GDELT to RIC is correct for the shocked name.",
                "Analyst EPSMean revisions within [-5, +30] days proxy information absorption.",
                "PIT index filter defines investable universe at shock date.",
            ],
            "known_bias": f"US bridge thin ({bridge_pct}% of spine); short ticker-shock window today.",
            "priority": "high",
        },
        {
            "id": "country_shock_broadcast_returns",
            "title": "Country-week macro shock → ticker return attribution",
            "status": "partial",
            "inputs": [
                "asia_country_week_news_market_primary",
                "idn_fry_daily_cross_section / yfinance panels",
                "ticker_week_country_broadcast_panel",
            ],
            "output_grain": "ticker × week",
            "join_keys": ["country_iso3", "week_end"],
            "assumptions": [
                "Country-level shock score loads on all liquid domestic equities equally (broadcast proxy).",
                "Not name-specific attribution — use for macro beta, not single-name alpha.",
            ],
            "known_bias": "Ticker-level entity panel only 25 days; broadcast panels need run_id refresh.",
            "priority": "medium",
        },
        {
            "id": "pit_event_study_universe",
            "title": "Survivorship-correct event-study universe",
            "status": "ready",
            "inputs": ["refinitiv_index_membership_pit", "any event panel with date + ric or index"],
            "output_grain": "constituent_ric × event_date",
            "join_keys": ["index_ric", "as_of_date", "constituent_ric"],
            "assumptions": [
                "Index membership at month-end defines who was investable when the event fired.",
            ],
            "known_bias": "Monthly PIT granularity; delistings between month-ends not captured intra-month.",
            "priority": "high",
        },
        {
            "id": "idn_fry_episode_outcome",
            "title": "IDN bandar episode + GDELT regime → forward reward",
            "status": "built",
            "inputs": [
                "idn_fry_episode_gdelt_features",
                "idn_fry_daily_cross_section",
                "idn_episode_reward_daily",
            ],
            "output_grain": "episode × horizon_day",
            "join_keys": ["episode_id", "yahoo_symbol", "trigger_date"],
            "assumptions": [
                "GDELT country dot acceleration around trigger proxies information/noise regime.",
                "Bandar labels from broker-flow heuristics approximate informed-flow episodes.",
            ],
            "known_bias": f"{facts.get('idn_gdelt_episodes', 0)} episodes; IDX-specific, not portable.",
            "priority": "medium",
        },
        {
            "id": "cross_asset_country_risk_factor",
            "title": "Cross-asset country risk factor panel",
            "status": "built",
            "inputs": ["cross_asset_fused_primary_panel"],
            "output_grain": "country_iso3 × week",
            "join_keys": ["country_iso3", "week_end"],
            "assumptions": [
                "Fused news, equity, FX, rates, and crypto columns share a common weekly calendar.",
                "Factors are comparable across the 13-country Asia set.",
            ],
            "known_bias": "No US/EU; macro cols are proxy not official national accounts.",
            "priority": "medium",
        },
        {
            "id": "estimate_revision_momentum",
            "title": "Estimate revision momentum factor",
            "status": "built",
            "inputs": ["refinitiv_estimate_revision_panel"],
            "output_grain": "ric × date",
            "join_keys": ["ric", "date"],
            "assumptions": [
                "Δ EPSMean is a slow-moving analyst sentiment proxy.",
            ],
            "known_bias": "US-dominated sample; sparse Asia names.",
            "priority": "low",
        },
        {
            "id": "us_si_risk_overlay",
            "title": "US short-interest + vol risk overlay",
            "status": "built",
            "inputs": ["refinitiv_us_risk_overlay", "refinitiv_rescued_us_risk_desktop"],
            "output_grain": "ric × date",
            "join_keys": ["ric", "date"],
            "assumptions": [
                "SI% and vol skew proxy crowding and tail risk for US equities in sample.",
            ],
            "known_bias": "Rescued desktop merge; not full StarMine entitlement.",
            "priority": "low",
        },
        {
            "id": "stablecoin_trust_engagement",
            "title": "Stablecoin trust ↔ engagement multi-source synthesis",
            "status": "profile_defined",
            "inputs": [
                "skynet_stablecoin_harvest",
                "etherscan scrapes",
                "defillama maps",
                "gdelt_crypto_overlay",
                "github/wikipedia/incident configs",
            ],
            "output_grain": "entity_id × week",
            "join_keys": ["entity_id", "primary_ethereum_address"],
            "assumptions": [
                "Security score + on-chain adoption + attention proxies jointly measure trust vs hype.",
            ],
            "known_bias": "Skynet/Etherscan join gaps; GDELT entity coverage uneven per coin.",
            "priority": "medium",
        },
        {
            "id": "pit_constituent_country_shock",
            "title": "Index constituent × country-week shock (broadcast, no entity bridge)",
            "status": "recipe",
            "inputs": [
                "refinitiv_index_membership_pit",
                "asia_country_week_news_market_primary",
                "entity_market_spine (country_code only)",
            ],
            "output_grain": "constituent_ric × week",
            "join_keys": ["country_code", "week_end", "constituent_ric"],
            "assumptions": [
                "All index members in a country share the country shock (weaker than entity join).",
                "Uses fused country-week panel (news + market), not GDELT bulk directly.",
            ],
            "known_bias": "Ecological fallacy for single-name events; good for macro index hedging studies.",
            "priority": "medium",
        },
        {
            "id": "sec_filing_drift_proxy",
            "title": "SEC filing date → short-horizon return drift",
            "status": "metadata_only",
            "inputs": ["sec_edgar index (metadata)", "yfinance / alpha price panel"],
            "output_grain": "cik × filing_date",
            "join_keys": ["ticker", "filing_date"],
            "assumptions": [
                "Filing publication date is the information event (ignores leak/anticipation).",
            ],
            "known_bias": "No PIT link at scale; US only; metadata not instant panel.",
            "priority": "low",
        },
        {
            "id": "bigquery_usdt_liquidity_regime",
            "title": "BigQuery USDT flow → crypto liquidity regime",
            "status": "live_query",
            "inputs": ["desk BigQuery ADC", "coingecko prices"],
            "output_grain": "day",
            "join_keys": ["date"],
            "assumptions": [
                "Stablecoin mint/burn aggregates signal crypto liquidity conditions.",
            ],
            "known_bias": "Not materialized in registry instant layer; query cost + cache discipline.",
            "priority": "low",
        },
        {
            "id": "expand_entity_spine_fuzzy",
            "title": "Expand GDELT↔RIC bridge via ticker/name fuzzy match",
            "status": "recipe",
            "inputs": [
                "entity_market_spine",
                "gdelt entity master",
                "ticker_entity_aliases_v2",
            ],
            "output_grain": "ric × gdelt_entity_id",
            "join_keys": ["exchange_ticker", "country_code", "company_name"],
            "assumptions": [
                "Same ticker in same country maps to same economic entity (false positives possible).",
            ],
            "known_bias": f"Current bridge {bridge_pct}%; US SPX needs this most.",
            "priority": "high",
        },
    ]


def _heatmap_md(matrix: dict[str, dict[str, int]]) -> str:
    caps_short = [
        "Prices",
        "CtyNews",
        "EntNews",
        "Fund",
        "Est/Rev",
        "PIT",
        "Risk",
        "Join",
        "Gov",
        "Social",
        "Chain",
    ]
    lines = [
        "| Geography | " + " | ".join(caps_short) + " | Avg |",
        "|" + "---|" * (len(caps_short) + 2),
    ]
    for geo in GEOGRAPHIES:
        scores = [matrix[geo][c] for c in CAPABILITIES]
        cells = [SCORE_LABEL[s] for s in scores]
        avg = round(sum(scores) / len(scores), 2)
        lines.append(f"| {geo} | " + " | ".join(cells) + f" | {avg} |")
    return "\n".join(lines)


def _bar(score: int, width: int = 12) -> str:
    filled = int(round(score / 3.0 * width))
    return "█" * filled + "░" * (width - filled)


def _time_bars_md(depth: list[dict[str, Any]]) -> str:
    lines = ["| Source | Span | Entities | Note |", "|---|---|---|---|"]
    for row in depth:
        span = f"{row.get('start', '?')} → {row.get('end', '?')}"
        ent = row.get("entities") if row.get("entities") is not None else "—"
        lines.append(f"| {row['source']} | {span} | {ent} | {row.get('note', '')} |")
    return "\n".join(lines)


def _registry_family_counts(datasets: list[dict[str, Any]]) -> dict[str, int]:
    def bucket(d: dict[str, Any]) -> str:
        did = str(d.get("dataset_id") or "")
        dom = str(d.get("domain") or "")
        if did.startswith("refinitiv_"):
            return "refinitiv_institutional"
        if did.startswith("idn_") or "indonesia" in did.lower():
            return "indonesia_regional"
        if "gdelt" in did.lower() or "news_shock" in did.lower():
            return "gdelt_news"
        if any(x in did.lower() for x in ("asia", "twse", "mops", "cross_asset", "ticker_")):
            return "asia_derived_panels"
        if any(x in did.lower() for x in ("stablecoin", "crypto", "coingecko", "skynet")):
            return "crypto_security"
        if dom == "web_scrape":
            return "web_scrape_catalog"
        if dom == "procured":
            return "procured_catalog"
        if str(d.get("backend") or "") in ("coingecko_simple_price_api", "usdt_bigquery_catalogue"):
            return "live_api"
        return "ops_metadata_other"

    c: dict[str, int] = {}
    for d in datasets:
        k = bucket(d)
        c[k] = c.get(k, 0) + 1
    return c


def _join_graph_mermaid(facts: dict[str, Any]) -> str:
    b = facts.get("spine_gdelt_bridged", 0)
    r = facts.get("spine_rics", 0)
    return f"""```mermaid
flowchart TB
  subgraph catalog["Catalog layers — peer components"]
    REG["research_query_registry\\n150 cards"]
    PART["collection_partitions\\n22 professor-visible"]
    LIVE["desk_sources\\n14 live connectors"]
  end
  subgraph materialized["Materialized query layers"]
    REF["Refinitiv institutional\\n15 instant cards"]
    GDELT["GDELT / news shock\\n3 instant + bulk archive"]
    ASIA["Asia derived panels\\n7 instant"]
    IDN["Indonesia regional\\n3 instant"]
    OPS["Ops / investment JSON\\n14 instant"]
    SYN["Cross-lane synthesis\\n2 parquet panels"]
  end
  subgraph joins["Shared join infrastructure"]
    SPINE["entity_market_spine\\n{r} RICs"]
    PIT["index_membership_pit\\n548k rows"]
    BRIDGE["event↔instrument bridge\\n{b}/{r} ({facts.get('spine_bridge_pct',0)}%)"]
  end
  REG --> materialized
  PART --> REG
  LIVE --> REG
  REF --> SPINE
  REF --> PIT
  GDELT --> BRIDGE
  ASIA --> PIT
  IDN --> PIT
  SYN --> PIT
  SYN --> SPINE
  BRIDGE -.-> SPINE
```"""


def build_report() -> dict[str, Any]:
    pd = _try_import_pandas()
    reg = json.loads((ROOT / "config/research_query_registry.json").read_text(encoding="utf-8"))
    datasets: list[dict[str, Any]] = list(reg.get("datasets") or [])
    desk = json.loads((ROOT / "config/desk_sources.json").read_text(encoding="utf-8"))
    family_counts = _registry_family_counts(datasets)
    instant_families = _registry_family_counts(
        [d for d in datasets if d.get("analysis_readiness") == "instant"]
    )
    facts = _probe_panels(pd)
    matrix = _score_matrix(facts)
    depth = _time_depth(facts)
    synthesis = _synthesis_catalog(facts)

    geo_avg = {g: round(sum(matrix[g].values()) / len(CAPABILITIES), 2) for g in GEOGRAPHIES}
    cap_avg = {
        c: round(sum(matrix[g][c] for g in GEOGRAPHIES) / len(GEOGRAPHIES), 2) for c in CAPABILITIES
    }

    return {
        "generated_at": _stamp(),
        "headline": {
            "registry_datasets": len(datasets),
            "instant_datasets": sum(1 for d in datasets if d.get("analysis_readiness") == "instant"),
            "registry_family_counts": family_counts,
            "instant_family_counts": instant_families,
            "entity_bridge_pct": facts.get("spine_bridge_pct"),
        },
        "coverage_matrix": matrix,
        "coverage_score_legend": SCORE_LABEL,
        "geography_average": geo_avg,
        "capability_average": cap_avg,
        "time_depth": depth,
        "probe_facts": facts,
        "join_graph": {
            "spine_rics": facts.get("spine_rics"),
            "gdelt_bridged": facts.get("spine_gdelt_bridged"),
            "pit_indices": facts.get("pit_by_index"),
            "estimate_rev_by_country": facts.get("estimate_rev_by_country"),
        },
        "live_connectors": [s.get("id") for s in desk.get("sources") or []],
        "synthesis_catalog": synthesis,
        "synthesis_built": [s["id"] for s in synthesis if s["status"] == "built"],
        "synthesis_recipes": [s["id"] for s in synthesis if s["status"] in ("recipe", "partial")],
        "top_gaps": [
            "Event-source ↔ market-instrument bridge is thin (10.9% of spine); not a GDELT-only problem.",
            "Instant-query center of gravity is Refinitiv institutional (15/39 cards), not GDELT (3/39).",
            "US entity-linked event coverage lags Asia despite strong estimate/PIT lanes.",
            "Ticker entity shock panel is a 25-day slice — not yet a longitudinal series.",
            "104 registry cards are metadata/search — coverage score counts instant panels only.",
        ],
    }


def _markdown(report: dict[str, Any]) -> str:
    h = report["headline"]
    md = [
        "# Databank research coverage (axis view)",
        "",
        f"Generated: {report['generated_at']}",
        "",
        "## Headline",
        "",
        f"- Registry: **{h['registry_datasets']}** datasets, **{h['instant_datasets']}** instant-query",
        f"- Event↔instrument bridge: **{h.get('entity_bridge_pct')}%** of entity spine",
        "",
        "## Registry families (equal weight)",
        "",
    ]
    for fam, n in sorted(h.get("registry_family_counts", {}).items(), key=lambda x: -x[1]):
        inst = h.get("instant_family_counts", {}).get(fam, 0)
        md.append(f"- `{fam}`: {n} registry · {inst} instant")
    md.extend([
        "",
        "## Coverage heatmap (geography × capability)",
        "",
        "Scores: **—** absent · **thin** metadata/short · **partial** · **strong** thick instant panel",
        "",
        _heatmap_md(report["coverage_matrix"]),
        "",
        "## Capability averages",
        "",
    ])
    for cap, avg in sorted(report["capability_average"].items(), key=lambda x: -x[1]):
        bar = _bar(int(round(avg)))
        md.append(f"- `{cap}` {bar} {avg}/3")
    md.extend(["", "## Time depth", "", _time_bars_md(report["time_depth"]), ""])
    md.append(_join_graph_mermaid(report["probe_facts"]))
    md.extend(["", "## Synthesis proxy catalog", ""])
    for s in report["synthesis_catalog"]:
        md.append(f"### {s['title']} (`{s['id']}`) — **{s['status']}**")
        md.append(f"- **Inputs:** {', '.join(s['inputs'])}")
        md.append(f"- **Grain:** {s['output_grain']}")
        md.append(f"- **Assumptions:** " + "; ".join(s["assumptions"]))
        md.append(f"- **Bias / ceiling:** {s['known_bias']}")
        md.append("")
    md.extend(["## Top gaps", ""])
    for g in report["top_gaps"]:
        md.append(f"- {g}")
    md.append("")
    return "\n".join(md)


def _print_text(report: dict[str, Any]) -> None:
    print(_markdown(report))


def main() -> int:
    ap = argparse.ArgumentParser(description="Research-axis coverage matrix + synthesis catalog")
    ap.add_argument("--json", action="store_true")
    ap.add_argument(
        "--out",
        default="",
        help="JSON output path (default docs/status/generated/databank_research_coverage.json)",
    )
    ap.add_argument(
        "--md-out",
        default="",
        help="Markdown output path (default docs/status/generated/databank_research_coverage.md)",
    )
    args = ap.parse_args()

    report = build_report()
    json_out = Path(args.out) if args.out else ROOT / "docs/status/generated/databank_research_coverage.json"
    md_out = Path(args.md_out) if args.md_out else ROOT / "docs/status/generated/databank_research_coverage.md"
    json_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md_out.write_text(_markdown(report), encoding="utf-8")

    if args.json:
        print(json_out)
    else:
        _print_text(report)
        print(f"\nWrote {json_out}")
        print(f"Wrote {md_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
