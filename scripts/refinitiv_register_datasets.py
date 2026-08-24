#!/usr/bin/env python3
"""Register Refinitiv value-harvest datasets in research_query_registry.json."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
REGISTRY = REPO / "config/research_query_registry.json"
DEFAULT_RUN = "2026-07-06-value-v2"

REFINITIV_DATASETS = [
    {
        "dataset_id": "refinitiv_security_master",
        "name": "Refinitiv Security Master (Value Harvest)",
        "backend": "local_parquet_panel",
        "access_shape": "local_derived_tables",
        "analysis_readiness": "instant",
        "grain": "instrument_snapshot",
        "time_field": "pulled_at",
        "entity_fields": ["ric", "trbc_sector", "trbc_industry", "country_code"],
        "local_root": "data_lake/refinitiv_backfill",
        "local_file": "processed/refinitiv_security_master.parquet",
        "default_run_id": DEFAULT_RUN,
        "description": "LSEG security master spine: RIC, TRBC, mcap, float, country. Join hub for Refinitiv panels.",
        "capabilities": ["filter_ticker", "column_projection", "limit", "export_json"],
        "join_keys": ["ric"],
        "recommended_use": "Universe construction and cross-panel joins for equity research.",
        "limitations": "ISIN often empty on YZU EDP; snapshot not point-in-time.",
    },
    {
        "dataset_id": "refinitiv_index_membership_pit",
        "name": "Refinitiv Point-in-Time Index Membership",
        "backend": "local_parquet_panel",
        "access_shape": "local_derived_tables",
        "analysis_readiness": "instant",
        "grain": "index_constituent_asof",
        "time_field": "as_of_date",
        "entity_fields": ["index_ric", "constituent_ric", "constituent_name"],
        "local_root": "data_lake/refinitiv_backfill",
        "local_file": "processed/index_membership_pit.parquet",
        "default_run_id": DEFAULT_RUN,
        "description": "PIT index constituents via 0#.INDEX + SDate. Survivorship-aware universe construction.",
        "capabilities": ["filter_date_range", "filter_ticker", "order", "limit", "export_json"],
        "join_keys": ["index_ric", "as_of_date", "constituent_ric"],
        "recommended_use": "Survivorship-correct backtests; S&P and IDX membership history.",
        "limitations": "Asia indices beyond .JKSE may require separate entitlement probe.",
    },
    {
        "dataset_id": "refinitiv_corporate_actions_snapshot",
        "name": "Refinitiv Corporate Actions Snapshot",
        "backend": "local_parquet_panel",
        "access_shape": "local_derived_tables",
        "analysis_readiness": "instant",
        "grain": "instrument_snapshot",
        "time_field": "pulled_at",
        "entity_fields": ["ric"],
        "local_root": "data_lake/refinitiv_backfill",
        "local_file": "processed/corporate_actions_snapshot.parquet",
        "default_run_id": DEFAULT_RUN,
        "description": "Adjustment factor snapshot per RIC; seed for total-return infrastructure.",
        "capabilities": ["filter_ticker", "column_projection", "limit", "export_json"],
        "join_keys": ["ric"],
        "recommended_use": "Return adjustment joins; expand to event feed when entitled.",
        "limitations": "Snapshot only; dividend/split event history sparse on EDP.",
    },
    {
        "dataset_id": "refinitiv_risk_tape_daily",
        "name": "Refinitiv US Risk Tape (SI + Vol Snapshot)",
        "backend": "local_parquet_panel",
        "access_shape": "local_derived_tables",
        "analysis_readiness": "instant",
        "grain": "instrument_day_metric",
        "time_field": "date",
        "entity_fields": ["ric", "metric"],
        "local_root": "data_lake/refinitiv_backfill",
        "local_file": "processed/vol_surface_metrics_daily.parquet",
        "default_run_id": DEFAULT_RUN,
        "description": "US risk metrics: short-interest % history (partial) + vol 30/90 and put/call snapshot cross-section.",
        "capabilities": ["filter_date_range", "filter_ticker", "order", "limit", "column_projection", "export_json"],
        "join_keys": ["ric", "date", "metric"],
        "recommended_use": "Crowding and risk-regime research; complement GDELT news shocks.",
        "limitations": "Vol 30/90 daily history sparse on YZU EDP; use desktop RESCUED pull for full vol/skew history.",
    },
    {
        "dataset_id": "refinitiv_estimate_revisions_daily",
        "name": "Refinitiv EPS Mean Daily History",
        "backend": "local_parquet_panel",
        "access_shape": "local_derived_tables",
        "analysis_readiness": "instant",
        "grain": "instrument_day_metric",
        "time_field": "date",
        "entity_fields": ["ric", "metric"],
        "local_root": "data_lake/refinitiv_backfill",
        "local_file": "processed/estimate_revisions_daily.parquet",
        "default_run_id": DEFAULT_RUN,
        "description": "TR.EPSMean daily history panel (estimate revision proxy on EDP).",
        "capabilities": ["filter_date_range", "filter_ticker", "order", "limit", "column_projection", "export_json"],
        "join_keys": ["ric", "date", "metric"],
        "recommended_use": "Analyst expectation drift and earnings momentum research.",
        "limitations": "Not full I/B/E/S revision tape; coverage varies by listing.",
    },
]


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", default=DEFAULT_RUN)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    reg = json.loads(REGISTRY.read_text(encoding="utf-8"))
    existing = {d["dataset_id"] for d in reg.get("datasets", [])}
    added = 0
    updated = 0
    for ds in REFINITIV_DATASETS:
        entry = dict(ds)
        entry["default_run_id"] = args.run_id
        if entry["dataset_id"] in existing:
            reg["datasets"] = [entry if d.get("dataset_id") == entry["dataset_id"] else d for d in reg["datasets"]]
            updated += 1
        else:
            reg["datasets"].append(entry)
            added += 1
    reg["updated_at"] = datetime.now(timezone.utc).isoformat()
    if args.dry_run:
        print(json.dumps({"added": added, "updated": updated, "run_id": args.run_id}, indent=2))
        return 0
    REGISTRY.write_text(json.dumps(reg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Registry updated: added={added} updated={updated} run_id={args.run_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
