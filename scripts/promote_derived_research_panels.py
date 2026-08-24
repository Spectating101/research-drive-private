#!/usr/bin/env python3
"""Promote flagship IDN/Asia derived panels into the query registry + partition map."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
REGISTRY = REPO / "config/research_query_registry.json"
PARTITIONS = REPO / "config/collection_partitions.json"
PARTITION_ID = "derived.research-panels"


def _stamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _upsert(doc: dict[str, Any], spec: dict[str, Any]) -> None:
    did = spec["dataset_id"]
    for i, row in enumerate(doc.get("datasets") or []):
        if str(row.get("dataset_id")) == did:
            merged = dict(row)
            merged.update(spec)
            doc["datasets"][i] = merged
            return
    doc.setdefault("datasets", []).append(spec)


def _wire_partition(cfg: dict[str, Any], dataset_id: str) -> None:
    for row in cfg.get("partitions") or []:
        if str(row.get("id")) != PARTITION_ID:
            continue
        ids = {str(x) for x in row.get("registry_dataset_ids") or []}
        ids.add(dataset_id)
        row["registry_dataset_ids"] = sorted(ids)
        row["last_registry_wired_at"] = _stamp()
        break


def _panel(path: Path) -> bool:
    return path.is_file() and path.stat().st_size > 0


def main() -> int:
    doc = json.loads(REGISTRY.read_text(encoding="utf-8"))
    cfg = json.loads(PARTITIONS.read_text(encoding="utf-8"))
    promoted: list[str] = []

    specs: list[dict[str, Any]] = [
        {
            "dataset_id": "idn_fry_daily_cross_section",
            "name": "Indonesia FRY daily cross-section",
            "backend": "local_parquet_panel",
            "access_shape": "local_derived_tables",
            "analysis_readiness": "instant",
            "grain": "ticker_day",
            "time_field": "date",
            "ticker_field": "yahoo_symbol",
            "entity_fields": ["yahoo_symbol"],
            "local_root": "data_lake/research_panels/idn_fry_episode",
            "local_file": "daily_cross_section.parquet",
            "default_run_id": "",
            "description": "Indonesia retail-flow (FRY) daily cross-section with broker, bandar, and technical features.",
            "join_keys": ["date", "yahoo_symbol"],
            "partition_id": PARTITION_ID,
            "recommended_use": "IDX episode studies, bandar/broker attribution.",
            "path": REPO / "data_lake/research_panels/idn_fry_episode/daily_cross_section.parquet",
        },
        {
            "dataset_id": "idn_fry_episode_gdelt_features",
            "name": "Indonesia FRY episode GDELT features",
            "backend": "local_parquet_panel",
            "access_shape": "local_derived_tables",
            "analysis_readiness": "instant",
            "grain": "episode",
            "time_field": "episode_start",
            "ticker_field": "symbol",
            "entity_fields": ["symbol", "emiten"],
            "local_root": "data_lake/research_panels/idn_fry_episode",
            "local_file": "episode_gdelt_features.parquet",
            "description": "GDELT entity features aligned to Indonesia FRY episodes.",
            "join_keys": ["symbol", "episode_start"],
            "partition_id": PARTITION_ID,
            "recommended_use": "News-shock → IDX episode outcome research.",
            "path": REPO / "data_lake/research_panels/idn_fry_episode/episode_gdelt_features.parquet",
        },
        {
            "dataset_id": "idn_episode_reward_daily",
            "name": "Indonesia episode reward daily",
            "backend": "local_parquet_panel",
            "access_shape": "local_derived_tables",
            "analysis_readiness": "instant",
            "grain": "episode_day",
            "time_field": "date",
            "ticker_field": "symbol",
            "entity_fields": ["symbol"],
            "local_root": "data_lake/research_panels/idn_episode_reward",
            "local_file": "daily_episodes.parquet",
            "description": "Daily episode reward labels for Indonesia turnaround research.",
            "join_keys": ["date", "symbol"],
            "partition_id": PARTITION_ID,
            "path": REPO / "data_lake/research_panels/idn_episode_reward/daily_episodes.parquet",
        },
        {
            "dataset_id": "asia_country_week_news_market_primary",
            "name": "Asia country-week news-market primary panel",
            "backend": "local_parquet_panel",
            "access_shape": "local_derived_tables",
            "analysis_readiness": "instant",
            "grain": "country_week",
            "time_field": "week_end",
            "country_field": "country_iso3",
            "entity_fields": ["country_iso3"],
            "local_root": "data_lake/research_panels/asia_news_market",
            "local_file": "asia_country_week_news_market_primary_panel.parquet",
            "default_run_id": "asia_news_market_auto_latest",
            "description": "Primary Asia country-week panel merging GDELT news shocks with market returns.",
            "join_keys": ["country_iso3", "week_end"],
            "partition_id": PARTITION_ID,
            "path": REPO
            / "data_lake/research_panels/asia_news_market/asia_news_market_auto_latest/asia_country_week_news_market_primary_panel.parquet",
        },
        {
            "dataset_id": "daily_ticker_entity_shock_panel",
            "name": "Daily ticker entity shock panel",
            "backend": "local_parquet_panel",
            "access_shape": "local_derived_tables",
            "analysis_readiness": "instant",
            "grain": "ticker_day",
            "time_field": "date",
            "ticker_field": "yahoo_symbol",
            "entity_fields": ["yahoo_symbol", "entity_id", "country_iso3"],
            "local_root": "data_lake/research_panels/ticker_news_market",
            "local_file": "daily_ticker_entity_shock_panel.parquet",
            "default_run_id": "ticker_20260615",
            "description": "Daily GDELT entity shocks mapped to liquid tickers with market context.",
            "join_keys": ["yahoo_symbol", "date", "entity_id"],
            "partition_id": PARTITION_ID,
            "recommended_use": "Ticker-level event studies; precursor to GDELT→revision cross-lane panel.",
            "path": REPO
            / "data_lake/research_panels/ticker_news_market/ticker_20260615/daily_ticker_entity_shock_panel.parquet",
        },
        {
            "dataset_id": "jkse_pit_idn_microstructure_revisions",
            "name": "JKSE PIT × IDN microstructure × estimate revisions",
            "backend": "local_parquet_panel",
            "access_shape": "local_derived_tables",
            "analysis_readiness": "instant",
            "grain": "instrument_month",
            "time_field": "as_of_month",
            "ticker_field": "yahoo_symbol",
            "entity_fields": ["ric", "yahoo_symbol", "company_name"],
            "local_root": "data_lake/research_panels/jkse_pit_idn",
            "local_file": "jkse_pit_idn_microstructure_revisions.parquet",
            "default_run_id": "",
            "description": "Regional cross-lane panel: JKSE PIT membership + IDN FRY microstructure + Refinitiv estimate revisions.",
            "join_keys": ["ric", "as_of_month", "yahoo_symbol"],
            "partition_id": PARTITION_ID,
            "recommended_use": "Regional IDX proof panel: JKSE PIT + IDN FRY + revisions (Indonesia depth lane only).",
            "path": REPO
            / "data_lake/research_panels/jkse_pit_idn/jkse_pit_idn_microstructure_revisions.parquet",
        },
        {
            "dataset_id": "pit_index_revision_momentum",
            "name": "Multi-index PIT × estimate revision momentum",
            "backend": "local_parquet_panel",
            "access_shape": "local_derived_tables",
            "analysis_readiness": "instant",
            "grain": "instrument_month",
            "time_field": "as_of_month",
            "entity_fields": ["ric", "index_ric", "company_name"],
            "local_root": "data_lake/research_panels/pit_revision_momentum",
            "local_file": "pit_index_revision_momentum.parquet",
            "default_run_id": "",
            "description": "Institutional cross-lane panel: PIT survivorship across six indices joined to estimate revision momentum.",
            "join_keys": ["index_ric", "ric", "as_of_month"],
            "partition_id": PARTITION_ID,
            "recommended_use": "Primary cross-lane proof: survivorship × sell-side revisions across SPX/JKSE/TWII/N225/KS11/STI.",
            "path": REPO / "data_lake/research_panels/pit_revision_momentum/pit_index_revision_momentum.parquet",
        },
    ]

    for spec in specs:
        path = spec.pop("path")
        if not _panel(path):
            print(f"skip {spec['dataset_id']}: missing {path}")
            continue
        _upsert(doc, spec)
        _wire_partition(cfg, spec["dataset_id"])
        promoted.append(spec["dataset_id"])
        print(f"promoted {spec['dataset_id']}")

    # Pin latest ticker week run when present
    for ds in doc.get("datasets") or []:
        if str(ds.get("dataset_id", "")).startswith("ticker_week_") and (
            REPO / "data_lake/research_panels/ticker_news_market/ticker_20260615"
        ).is_dir():
            ds["default_run_id"] = "ticker_20260615"

    REGISTRY.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    PARTITIONS.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"promoted": promoted, "total_registry": len(doc.get("datasets") or [])}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
