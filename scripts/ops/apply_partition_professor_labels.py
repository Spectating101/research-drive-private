#!/usr/bin/env python3
"""Apply professor-readable domain blurbs and partition titles/descriptions."""

from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PARTITIONS_PATH = REPO / "config/collection_partitions.json"

DOMAINS = {
    "markets": "What traded — stock/crypto prices, universes, DeFi & NFT snapshots",
    "news": "What happened in the world — GDELT news graph & country shock panels",
    "official": "Authoritative filings — TWSE exchange data, macro baselines, MOPS-style governance",
    "reference": "Join keys & lookup tables — tickers, entities, SEC IDs (not time-series panels)",
    "social": "Crowd text — Reddit ingest and sentiment archives",
    "catalog": "Browsable dataset indexes (curated lists; not operator bulk harvest)",
    "acquired": "Lab downloads — DOI collects, chat procurement, campaign one-offs",
    "derived": "Ready-to-model tables — merged panels and saved trial outputs",
    "ops": "Pipeline operator files — manifests & job logs (skip unless you run jobs)",
    "backend": "Operator-only bulk metadata (DataCite harvest) — never share with professors",
}

LABELS: dict[str, dict[str, str]] = {
    "news.gdelt-asia": {
        "title": "GDELT Asia news graph & shock panels",
        "professor_label": "Asia news events (GDELT)",
        "description": "Global news articles and themes for Asia: raw GKG pulls, normalized monthly shards, scored runs, and daily country shock panels. Use for event studies, news-risk overlays, and Asia headline research.",
    },
    "catalog.datacite-harvest": {
        "title": "DataCite metadata harvest (operator bulk)",
        "professor_label": "DataCite bulk (backend)",
        "description": "Sharded JSONL of DataCite records for procurement search — operator desk only. Professors use curated indexes or live DOI collect instead.",
    },
    "catalog.curated-index": {
        "title": "Curated dataset index (human-readable)",
        "professor_label": "Curated dataset lists",
        "description": "Hand-picked and promoted dataset cards (tiered), watchdog/quarantine lists, and external catalog seeds — the readable face of the library.",
    },
    "markets.crypto-landscape": {
        "title": "Crypto protocol & token landscape snapshots",
        "professor_label": "Crypto landscape runs",
        "description": "Periodic snapshots of protocols, tokens, and DeFi landscape metrics. Use for taxonomy, regime, and cross-protocol comparison studies.",
    },
    "markets.crypto-coingecko": {
        "title": "CoinGecko daily price archive (local cache)",
        "professor_label": "CoinGecko prices (local)",
        "description": "Off-chain daily market history from CoinGecko — join to on-chain token panels for taxonomy and return studies. Mirrored to Drive when scheduled.",
    },
    "markets.ethereum-usdt": {
        "title": "Ethereum USDT on-chain flows (professor package)",
        "professor_label": "USDT on-chain (BigQuery)",
        "description": "Tether (USDT) transfer panels on Ethereum: daily/monthly CSV packages and optional raw Parquet. Primary source for stablecoin flow and FinTech grant work.",
    },
    "markets.equities-asia": {
        "title": "Asia equity prices & ticker universes",
        "professor_label": "Asia stock panels",
        "description": "Daily prices and investable universes for Taiwan, Indonesia, and broader Asia (yfinance and sourced broker lists). Use for momentum, ML, and cross-market equity research.",
    },
    "markets.nft-opensea": {
        "title": "OpenSea NFT collection metadata",
        "professor_label": "NFT metadata (OpenSea)",
        "description": "Collection-level NFT metadata and graph exports for rarity, network, and return studies (SSRN-style NFT asset pricing).",
    },
    "official.exchange-disclosures": {
        "title": "Taiwan TWSE exchange OpenAPI snapshots",
        "professor_label": "TWSE official market data",
        "description": "Official Taiwan Stock Exchange OpenAPI dumps: listings, sectors, material information, penalties, income statements, and ESG board fields. Base layer for Taiwan equity and disclosure research.",
    },
    "official.mops-disclosures": {
        "title": "Taiwan MOPS & governance procured files",
        "professor_label": "MOPS / governance procured",
        "description": "Governance and misconduct-related files landed by the procurement desk (filings, panels, web collects). Grows automatically when you ask for MOPS or Taiwan governance data.",
    },
    "official.macro-asia": {
        "title": "Asia public macro & market baselines",
        "professor_label": "Asia macro baselines",
        "description": "Downloaded public macro and cross-market baseline packs for Asia research — rates, risk proxies, and comparable market indicators.",
    },
    "reference.entity-mapping-asia": {
        "title": "Asia ticker & entity resolution maps",
        "professor_label": "Asia entity mapping",
        "description": "Maps news tickers, venues, and instruments across Asia sources. Use before joining GDELT headlines to price panels.",
    },
    "reference.sec-edgar": {
        "title": "US SEC EDGAR ticker ↔ CIK reference",
        "professor_label": "SEC ticker map",
        "description": "Public SEC company_tickers.json and related EDGAR reference extracts. Required join key before pulling US filing histories.",
    },
    "reference.refinitiv-backfill": {
        "title": "Refinitiv/LSEG backfill (local USB only)",
        "professor_label": "Refinitiv cache (local)",
        "description": "Local Refinitiv backfill on USB — not mirrored to the shared Drive vault yet.",
    },
    "social.reddit": {
        "title": "Reddit raw ingest & sentiment archive",
        "professor_label": "Reddit sentiment",
        "description": "Historical Reddit posts/comments ingest and derived sentiment panels for alt-data and crypto-equity sentiment studies.",
    },
    "acquired.procured": {
        "title": "Chat & DOI procured downloads",
        "professor_label": "Procured one-offs",
        "description": "Everything the research desk downloaded on your behalf: DataCite DOIs, web collects, and campaign artifacts. Each subfolder is one dataset_id.",
    },
    "derived.research-panels": {
        "title": "Merged research panels (analysis-ready)",
        "professor_label": "Research panels",
        "description": "Derived tables built in-house — e.g. Asia news × market trial panels. Start here when reproducing internal empirical notebooks.",
    },
    "derived.research-models": {
        "title": "Saved model outputs & trial artifacts",
        "professor_label": "Model trial outputs",
        "description": "Checkpointed model runs and trial exports (e.g. Asia news-market modeling). Drive-only until hydrated locally.",
    },
    "ops.pipeline-manifests": {
        "title": "Pipeline & queue operator manifests",
        "professor_label": "Ops manifests",
        "description": "JSON manifests for scheduled data jobs — operator visibility only.",
    },
    "ops.spectator-archives": {
        "title": "Web scrape archives (local USB)",
        "professor_label": "Scrape archives (local)",
        "description": "Historical Spectator scrape bundles on local USB — not in the shared Drive map.",
    },
    "ops.collection-queue": {
        "title": "Scheduled collection job outputs",
        "professor_label": "Collection job archives",
        "description": "Per-task outputs from the data collection queue (SEC tickers, TWSE refresh, etc.).",
    },
    "ops.cluster-jobs": {
        "title": "YZU cluster job state (local only)",
        "professor_label": "Cluster jobs (local)",
        "description": "Worker SQLite and logs — never part of the research vault.",
    },
}


def main() -> int:
    doc = json.loads(PARTITIONS_PATH.read_text(encoding="utf-8"))
    doc["domains"] = DOMAINS
    doc["summary"] = (
        "Professor-facing Drive tree under collection/ only. "
        "Open collection/ in Drive — each subfolder has a plain-English README. "
        "Backend DataCite bulk lives in datacite_catalog/ at vault root (not shared)."
    )
    for part in doc.get("partitions") or []:
        pid = str(part.get("id") or "")
        patch = LABELS.get(pid)
        if not patch:
            continue
        part.update(patch)
    PARTITIONS_PATH.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    print(f"Updated {len(LABELS)} partitions + domains in {PARTITIONS_PATH.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
