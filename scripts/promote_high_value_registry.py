#!/usr/bin/env python3
"""Promote high-value registry cards + collection partitions (CRSP, Compustat, macro, bridge)."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
REGISTRY = REPO / "config/research_query_registry.json"
PARTITIONS = REPO / "config/collection_partitions.json"


def _stamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


NEW_DATASETS = [
    {
        "dataset_id": "public_equity_us_sp500_yfinance_daily",
        "name": "US SP500 daily prices (yfinance proxy)",
        "backend": "local_parquet_panel",
        "access_shape": "local_derived_tables",
        "analysis_readiness": "instant",
        "grain": "symbol_day",
        "time_field": "date",
        "entity_fields": ["yahoo_symbol"],
        "local_root": "data_lake/research_panels/public_equity",
        "local_file": "us_sp500_yfinance_daily.parquet",
        "description": "Interim US equity lane from yfinance until CRSP us_stock_daily is ingested.",
        "capabilities": ["filter_date_range", "order", "limit", "export_json"],
        "join_keys": ["date", "yahoo_symbol"],
        "recommended_use": "US price research proxy; replace with CRSP when on disk.",
        "limitations": "yfinance adj close; not CRSP-compliant; survivorship differs from PIT CRSP.",
        "partition_id": "reference.crsp-moveit",
        "source_id": "yfinance_public",
        "source_system": "Yahoo Finance (public proxy)",
        "source_access_mode": "materialized_instant",
        "field_coverage": "query-ready",
        "entitlement_status": "public",
        "collection_status": "active",
        "known_gap": "Proxy until CRSP MOVEit ingest completes",
    },
    {
        "dataset_id": "public_macro_ff_factors_daily",
        "name": "Ken French Fama-French daily factors (FF3)",
        "backend": "local_parquet_panel",
        "access_shape": "local_derived_tables",
        "analysis_readiness": "instant",
        "grain": "factor_day",
        "time_field": "date",
        "entity_fields": [],
        "local_root": "data_lake/research_panels/public_macro",
        "local_file": "ff_factors_daily.parquet",
        "description": "US Mkt-RF, SMB, HML, RF daily from Ken French — built from public_macro_market_baseline.",
        "capabilities": ["filter_date_range", "order", "limit", "export_json"],
        "join_keys": ["date"],
        "recommended_use": "US factor risk model baseline; macro regime controls.",
        "limitations": "US factors only; rebuild after download_public_macro_market_baseline.",
        "partition_id": "official.macro-asia",
        "source_id": "public_macro",
        "source_system": "Public macro baselines (Ken French etc.)",
        "source_access_mode": "materialized_instant",
        "field_coverage": "query-ready",
        "entitlement_status": "public",
        "collection_status": "active",
    },
    {
        "dataset_id": "crsp_moveit_catalog_status",
        "name": "CRSP MOVEit product catalog (manifest)",
        "backend": "ops_json_manifest",
        "access_shape": "operator_manifest",
        "analysis_readiness": "metadata_search",
        "grain": "file_catalog",
        "description": "Authenticated listing of CRSP MOVEit Product_Downloads folders.",
        "local_root": "data_lake/crsp",
        "local_file": "manifest_latest.json",
        "capabilities": ["describe"],
        "partition_id": "reference.crsp-moveit",
        "source_id": "crsp_moveit",
        "source_system": "CRSP MOVEit Cloud",
        "source_access_mode": "materialized_bulk",
        "entitlement_status": "active",
        "collection_status": "wired",
    },
    {
        "dataset_id": "crsp_us_stock_daily_ciz",
        "name": "CRSP US Stock 2.5 daily (CIZ ASCII)",
        "backend": "local_parquet_panel",
        "access_shape": "local_derived_tables",
        "analysis_readiness": "instant",
        "grain": "permno_day",
        "time_field": "date",
        "entity_fields": ["permno", "permco", "ticker"],
        "local_root": "data_lake/crsp",
        "local_file": "processed/us_stock_daily_ciz.parquet",
        "description": "Authoritative US equity daily history from CRSP MOVEit STOCK_25i subscription.",
        "capabilities": ["filter_date_range", "filter_ticker", "order", "limit", "export_json"],
        "join_keys": ["permno", "date"],
        "recommended_use": "US survivorship-aware price research; replaces yfinance for US lane.",
        "limitations": "Pending MOVEit download + CIZ parse pipeline.",
        "partition_id": "reference.crsp-moveit",
        "source_id": "crsp_moveit",
        "source_system": "CRSP MOVEit Cloud",
        "source_access_mode": "materialized_bulk",
        "entitlement_status": "active",
        "field_coverage": "pending_ingest",
        "known_gap": "Not on disk yet — run crsp_moveit_sync_priority after manifest",
        "collection_status": "pending_ingest",
    },
    {
        "dataset_id": "crsp_us_index_history",
        "name": "CRSP US index history (1925+)",
        "backend": "local_parquet_panel",
        "access_shape": "local_derived_tables",
        "analysis_readiness": "instant",
        "grain": "index_day",
        "time_field": "date",
        "entity_fields": ["index_code"],
        "local_root": "data_lake/crsp",
        "local_file": "processed/us_index_history.parquet",
        "partition_id": "reference.crsp-moveit",
        "source_id": "crsp_moveit",
        "source_system": "CRSP MOVEit Cloud",
        "source_access_mode": "materialized_bulk",
        "entitlement_status": "active",
        "field_coverage": "pending_ingest",
        "known_gap": "Pending MOVEit download",
        "collection_status": "pending_ingest",
    },
    {
        "dataset_id": "compustat_na_fundamentals_annual",
        "name": "Compustat North America fundamentals (annual)",
        "backend": "local_parquet_panel",
        "access_shape": "local_derived_tables",
        "analysis_readiness": "instant",
        "grain": "gvkey_fyear",
        "time_field": "datadate",
        "entity_fields": ["gvkey", "tic", "cusip"],
        "local_root": "data_lake/compustat",
        "local_file": "processed/na_fundamentals_annual.parquet",
        "description": "US GAAP fundamentals from Capital IQ / Compustat export.",
        "capabilities": ["filter_ticker", "filter_date_range", "column_projection", "limit", "export_json"],
        "join_keys": ["gvkey", "datadate"],
        "recommended_use": "US fundamental factors; pair with CRSP via CCM link.",
        "limitations": "Manual Capital IQ export required — no WRDS on desk.",
        "partition_id": "reference.compustat-capitaliq",
        "source_id": "capital_iq_compustat",
        "source_system": "S&P Capital IQ / Compustat",
        "source_access_mode": "materialized_bulk",
        "entitlement_status": "active",
        "field_coverage": "pending_export",
        "known_gap": "Export from Capital IQ Fundamentals screen to data_lake/compustat/raw/",
        "collection_status": "pending_export",
    },
    {
        "dataset_id": "crsp_compustat_ccm_link",
        "name": "CRSP/Compustat CCM link table",
        "backend": "local_parquet_panel",
        "access_shape": "local_derived_tables",
        "analysis_readiness": "instant",
        "grain": "gvkey_permno_link",
        "time_field": "linkdt",
        "entity_fields": ["gvkey", "permno", "lpermno"],
        "local_root": "data_lake/crsp",
        "local_file": "processed/ccm_link.parquet",
        "description": "CRSP-Compustat Merged link — PERMNO/GVKEY bridge for US equity+fundamental joins.",
        "join_keys": ["gvkey", "permno", "linkdt"],
        "partition_id": "reference.crsp-moveit",
        "source_id": "crsp_moveit",
        "source_system": "CRSP MOVEit Cloud",
        "source_access_mode": "materialized_bulk",
        "entitlement_status": "active",
        "field_coverage": "pending_ingest",
        "known_gap": "Requires CRSP + Compustat base tables",
        "collection_status": "blocked",
    },
    {
        "dataset_id": "refinitiv_entity_market_spine_expanded",
        "name": "Refinitiv entity spine (GDELT bridge expanded)",
        "backend": "local_parquet_panel",
        "access_shape": "local_derived_tables",
        "analysis_readiness": "instant",
        "grain": "ric_entity",
        "time_field": "as_of_date",
        "entity_fields": ["ric", "gdelt_entity_id", "exchange_ticker"],
        "local_root": "data_lake/research_panels/refinitiv/2026-07-06-complete",
        "local_file": "entity_market_spine_expanded.parquet",
        "description": "Entity spine with alias-assisted GDELT entity bridge expansion.",
        "capabilities": ["filter_ticker", "column_projection", "limit", "export_json"],
        "join_keys": ["ric", "gdelt_entity_id"],
        "recommended_use": "Entity-resolved GDELT shock joins; run build_gdelt_entity_bridge_expansion.py to refresh.",
        "limitations": "Alias peer-copy heuristic — not ground-truth GDELT master match.",
        "partition_id": "reference.refinitiv-backfill",
        "source_id": "derived_research_panels",
        "source_system": "In-house derived research panels",
        "source_access_mode": "derived_internal",
        "field_coverage": "partial",
        "collection_status": "active",
    },
]

NEW_PARTITIONS = [
    {
        "id": "reference.crsp-moveit",
        "domain": "reference",
        "path": "reference/crsp-moveit",
        "title": "CRSP US Stock & Index (MOVEit)",
        "description": "CRSP subscriber bulk delivery: US Stock 2.5 CIZ, index history, CCM link. Licensed via crsp.moveitcloud.com.",
        "legacy_drive_path": "collection/reference/crsp-moveit",
        "target_drive_path": "collection/reference/crsp-moveit",
        "legacy_local_path": "data_lake/crsp",
        "tier": "hot",
        "status": "wired",
        "professor_label": "US equity history (CRSP)",
        "subfolders": ["raw", "processed", "manifests"],
        "registry_dataset_ids": [
            "crsp_moveit_catalog_status",
            "crsp_us_stock_daily_ciz",
            "crsp_us_index_history",
            "crsp_compustat_ccm_link",
        ],
    },
    {
        "id": "reference.compustat-capitaliq",
        "domain": "reference",
        "path": "reference/compustat-capitaliq",
        "title": "Compustat fundamentals (Capital IQ export)",
        "description": "US GAAP fundamentals exported from S&P Capital IQ / Compustat. Manual or scripted export — no WRDS on this desk.",
        "legacy_drive_path": "collection/reference/compustat-capitaliq",
        "target_drive_path": "collection/reference/compustat-capitaliq",
        "legacy_local_path": "data_lake/compustat",
        "tier": "hot",
        "status": "pending_export",
        "professor_label": "US fundamentals (Compustat)",
        "subfolders": ["raw", "processed"],
        "registry_dataset_ids": ["compustat_na_fundamentals_annual"],
    },
]


def _upsert_dataset(reg: dict, row: dict) -> bool:
    datasets = reg.setdefault("datasets", [])
    by_id = {str(d.get("dataset_id")): d for d in datasets}
    did = row["dataset_id"]
    if did in by_id:
        by_id[did].update(row)
        return False
    datasets.append(row)
    return True


def _upsert_partition(cfg: dict, row: dict) -> bool:
    parts = cfg.setdefault("partitions", [])
    by_id = {str(p.get("id")): p for p in parts}
    pid = row["id"]
    if pid in by_id:
        by_id[pid].update(row)
        return False
    parts.append(row)
    return True


def main() -> int:
    reg = json.loads(REGISTRY.read_text(encoding="utf-8"))
    parts = json.loads(PARTITIONS.read_text(encoding="utf-8"))

    added_ds = sum(1 for row in NEW_DATASETS if _upsert_dataset(reg, row))
    added_pt = sum(1 for row in NEW_PARTITIONS if _upsert_partition(parts, row))

    reg["updated_at"] = _stamp()
    REGISTRY.write_text(json.dumps(reg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    PARTITIONS.write_text(json.dumps(parts, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # stamp source map on new cards
    from scripts.research_data_mcp.source_map import load_source_map, stamp_registry_sources

    stamp_registry_sources(REPO, dry_run=False)

    print(
        json.dumps(
            {
                "added_datasets": added_ds,
                "updated_datasets": len(NEW_DATASETS) - added_ds,
                "added_partitions": added_pt,
                "registry_total": len(reg.get("datasets") or []),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
