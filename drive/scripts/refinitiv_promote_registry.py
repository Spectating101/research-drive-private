#!/usr/bin/env python3
"""Update Refinitiv dataset registry entries and build backfill INDEX.json."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
REGISTRY = REPO / "config/research_query_registry.json"
BACKFILL_ROOT = REPO / "data_lake/refinitiv_backfill"

CANONICAL_RUN = "2026-07-06-complete"
DERIVED_RUN = CANONICAL_RUN
DERIVED_ROOT = "data_lake/research_panels/refinitiv"

RUN_BY_DATASET = {
    "refinitiv_security_master": CANONICAL_RUN,
    "refinitiv_corporate_actions_snapshot": CANONICAL_RUN,
    "refinitiv_index_membership_pit": CANONICAL_RUN,
    "refinitiv_risk_tape_daily": CANONICAL_RUN,
    "refinitiv_estimate_revisions_daily": CANONICAL_RUN,
    "refinitiv_fundamentals_snapshot": CANONICAL_RUN,
    "refinitiv_index_membership_current": CANONICAL_RUN,
    "refinitiv_analyst_consensus_snapshot": CANONICAL_RUN,
    "refinitiv_esg_snapshot": CANONICAL_RUN,
    "refinitiv_rescued_us_risk_desktop": "rescued_desktop_20251215",
    "refinitiv_survivorship_universe_panel": DERIVED_RUN,
    "refinitiv_us_risk_overlay": DERIVED_RUN,
    "refinitiv_estimate_revision_panel": DERIVED_RUN,
    "refinitiv_fundamental_annual_panel": DERIVED_RUN,
    "refinitiv_entity_market_spine": DERIVED_RUN,
}

GDRIVE_ROOT = "gdrive:Machine_Archive/molina_workbench/Sharpe-Renaissance-data/refinitiv_backfill"

EXTRA_DATASETS = [
    {
        "dataset_id": "refinitiv_index_membership_current",
        "name": "Refinitiv Current Index Membership",
        "backend": "local_parquet_panel",
        "access_shape": "local_derived_tables",
        "analysis_readiness": "instant",
        "grain": "index_constituent_snapshot",
        "time_field": "pulled_at",
        "entity_fields": ["index_ric", "constituent_ric"],
        "local_root": "data_lake/refinitiv_backfill",
        "local_file": "processed/index_membership_current.parquet",
        "default_run_id": CANONICAL_RUN,
        "canonical_remote": f"{GDRIVE_ROOT}/{CANONICAL_RUN}",
        "source_of_truth": "gdrive",
        "description": "Current index constituents for SPX, JKSE, TWII, N225, KS11, STI.",
        "capabilities": ["filter_ticker", "column_projection", "limit", "export_json"],
        "join_keys": ["index_ric", "constituent_ric"],
        "recommended_use": "Live universe seeding; compare against PIT panel.",
        "limitations": "Snapshot only.",
    },
    {
        "dataset_id": "refinitiv_analyst_consensus_snapshot",
        "name": "Refinitiv Analyst Consensus Snapshot",
        "backend": "local_parquet_panel",
        "access_shape": "local_derived_tables",
        "analysis_readiness": "instant",
        "grain": "instrument_snapshot",
        "time_field": "pulled_at",
        "entity_fields": ["ric"],
        "local_root": "data_lake/refinitiv_backfill",
        "local_file": "processed/analyst_consensus_snapshot.parquet",
        "default_run_id": CANONICAL_RUN,
        "canonical_remote": f"{GDRIVE_ROOT}/{CANONICAL_RUN}",
        "source_of_truth": "gdrive",
        "description": "EPS/Revenue/Price target consensus snapshot (E1-E3).",
        "capabilities": ["filter_ticker", "column_projection", "limit", "export_json"],
        "join_keys": ["ric"],
        "recommended_use": "Screening; pair with estimate_revisions_daily for history.",
        "limitations": "Snapshot not revision history.",
    },
    {
        "dataset_id": "refinitiv_esg_snapshot",
        "name": "Refinitiv ESG Pillar Snapshot",
        "backend": "local_parquet_panel",
        "access_shape": "local_derived_tables",
        "analysis_readiness": "instant",
        "grain": "instrument_snapshot",
        "time_field": "pulled_at",
        "entity_fields": ["ric"],
        "local_root": "data_lake/refinitiv_backfill",
        "local_file": "processed/esg_snapshot.parquet",
        "default_run_id": CANONICAL_RUN,
        "canonical_remote": f"{GDRIVE_ROOT}/{CANONICAL_RUN}",
        "source_of_truth": "gdrive",
        "description": "LSEG/TR ESG pillar scores snapshot.",
        "capabilities": ["filter_ticker", "column_projection", "limit", "export_json"],
        "join_keys": ["ric"],
        "recommended_use": "ESG factor overlays on equity panels.",
        "limitations": "Snapshot only; not time series.",
    },
]

FUNDAMENTALS_DATASET = {
    "dataset_id": "refinitiv_fundamentals_snapshot",
    "name": "Refinitiv Fundamentals Panel (FRQ=FY)",
    "backend": "local_parquet_panel",
    "access_shape": "local_derived_tables",
    "analysis_readiness": "instant",
    "grain": "instrument_fiscal_year",
    "time_field": "pulled_at",
    "entity_fields": ["ric"],
    "local_root": "data_lake/refinitiv_backfill",
    "local_file": "processed/fundamentals_panel.parquet",
    "default_run_id": CANONICAL_RUN,
    "canonical_remote": f"{GDRIVE_ROOT}/{CANONICAL_RUN}",
    "source_of_truth": "gdrive",
    "description": "Multi-year fundamentals via fundamental_and_reference FRQ=FY on YZU EDP.",
    "capabilities": ["filter_ticker", "column_projection", "limit", "export_json"],
    "join_keys": ["ric"],
    "recommended_use": "Factor and screening joins with FY history panels.",
    "limitations": "Not full PIT accounting; quarterly FQ period blocked on EDP.",
}

RESCUED_DATASET = {
    "dataset_id": "refinitiv_rescued_us_risk_desktop",
    "name": "Refinitiv Desktop US Risk Vol/Skew Panel (RESCUED)",
    "backend": "local_parquet_panel",
    "access_shape": "local_derived_tables",
    "analysis_readiness": "instant",
    "grain": "instrument_day_metric",
    "time_field": "date",
    "entity_fields": ["ric", "metric"],
    "local_root": "data_lake/refinitiv_backfill",
    "local_file": "processed/us_risk_vol_skew_daily.parquet",
    "default_run_id": "rescued_desktop_20251215",
    "canonical_remote": f"{GDRIVE_ROOT}/rescued_desktop_20251215",
    "source_of_truth": "gdrive",
    "description": "Dec 2025 desktop Eikon S&P panel: vol 30/90/360, skew, put/call, short interest ratio.",
    "capabilities": ["filter_date_range", "filter_ticker", "order", "limit", "column_projection", "export_json"],
    "join_keys": ["ric", "date", "metric"],
    "recommended_use": "US crash/risk research where YZU EDP vol history is empty.",
    "limitations": "Desktop pull 2025-12-15; US S&P universe; not refreshed automatically.",
}

CAVEAT_METADATA: dict[str, dict[str, str]] = {
    "refinitiv_security_master": {
        "entitlement_status": "collected",
        "field_coverage": "query-ready",
        "known_gap": "ISIN often empty on YZU EDP",
        "best_use": "Join hub for all Refinitiv panels",
        "collection_status": "frozen_release",
    },
    "refinitiv_index_membership_pit": {
        "entitlement_status": "collected",
        "field_coverage": "query-ready",
        "known_gap": "Constituent names sparse (~93% null)",
        "best_use": "Survivorship-correct backtests; GDELT shock joins",
        "collection_status": "frozen_release",
    },
    "refinitiv_index_membership_current": {
        "entitlement_status": "collected",
        "field_coverage": "query-ready",
        "known_gap": ".STI current snapshot blocked on EDP",
        "best_use": "Live universe seed vs PIT panel",
        "collection_status": "frozen_release",
    },
    "refinitiv_corporate_actions_snapshot": {
        "entitlement_status": "collected",
        "field_coverage": "partial",
        "known_gap": "Adjustment-factor snapshot only; not full CA event feed",
        "best_use": "Return adjustment seed infrastructure",
        "collection_status": "frozen_release",
    },
    "refinitiv_risk_tape_daily": {
        "entitlement_status": "collected",
        "field_coverage": "query-ready",
        "known_gap": "EDP vol 30/90 daily history empty; use rescued desktop for US",
        "best_use": "SI% history + vol/put-call snapshot overlays",
        "collection_status": "frozen_release",
    },
    "refinitiv_estimate_revisions_daily": {
        "entitlement_status": "collected",
        "field_coverage": "query-ready",
        "known_gap": "EPS mean only; sparse for non-covered names",
        "best_use": "News shock → revision response studies",
        "collection_status": "frozen_release",
    },
    "refinitiv_fundamentals_snapshot": {
        "entitlement_status": "collected",
        "field_coverage": "partial",
        "known_gap": "FY via FRQ=FY; FQ PIT accounting blocked",
        "best_use": "Annual factor joins; not full PIT accounting",
        "collection_status": "frozen_release",
    },
    "refinitiv_analyst_consensus_snapshot": {
        "entitlement_status": "collected",
        "field_coverage": "snapshot",
        "known_gap": "Cross-section only; pair with revisions daily for history",
        "best_use": "Screening and consensus level joins",
        "collection_status": "frozen_release",
    },
    "refinitiv_esg_snapshot": {
        "entitlement_status": "collected",
        "field_coverage": "snapshot",
        "known_gap": "Snapshot only; not ESG time series",
        "best_use": "ESG factor overlays on equity panels",
        "collection_status": "frozen_release",
    },
    "refinitiv_rescued_us_risk_desktop": {
        "entitlement_status": "collected",
        "field_coverage": "query-ready",
        "known_gap": "Desktop Eikon Dec 2025; US S&P only; not auto-refreshed",
        "best_use": "US vol/skew/SI history where EDP is empty",
        "collection_status": "frozen_release",
    },
}

DERIVED_DATASETS = [
    {
        "dataset_id": "refinitiv_survivorship_universe_panel",
        "name": "Refinitiv Survivorship Universe Panel",
        "backend": "local_parquet_panel",
        "access_shape": "local_derived_tables",
        "analysis_readiness": "instant",
        "grain": "index_constituent_month",
        "time_field": "as_of_month",
        "entity_fields": ["index_ric", "constituent_ric", "country_code", "trbc_sector"],
        "local_root": DERIVED_ROOT,
        "local_file": "survivorship_universe_panel.parquet",
        "default_run_id": DERIVED_RUN,
        "canonical_remote": f"{GDRIVE_ROOT}/{CANONICAL_RUN}",
        "source_of_truth": "local_derived",
        "description": "PIT index membership enriched with country and TRBC sector.",
        "capabilities": ["filter_date_range", "filter_ticker", "order", "limit", "export_json"],
        "join_keys": ["index_ric", "as_of_month", "constituent_ric"],
        "entitlement_status": "derived",
        "field_coverage": "query-ready",
        "known_gap": "Built from frozen 2026-07-06-complete PIT + spine",
        "best_use": "Survivorship-correct GDELT/news shock event studies",
        "collection_status": "derived_release",
    },
    {
        "dataset_id": "refinitiv_us_risk_overlay",
        "name": "Refinitiv US Risk Overlay (SI + rescued vol/skew)",
        "backend": "local_parquet_panel",
        "access_shape": "local_derived_tables",
        "analysis_readiness": "instant",
        "grain": "instrument_day",
        "time_field": "date",
        "entity_fields": ["ric"],
        "local_root": DERIVED_ROOT,
        "local_file": "us_risk_overlay.parquet",
        "default_run_id": DERIVED_RUN,
        "description": "Short-interest history merged with desktop rescued US vol/skew/SI.",
        "join_keys": ["ric", "date"],
        "entitlement_status": "derived",
        "field_coverage": "query-ready",
        "known_gap": "US-centric; Asia vol history still thin on EDP",
        "best_use": "Crowding and crash-risk overlays on US names",
        "collection_status": "derived_release",
    },
    {
        "dataset_id": "refinitiv_estimate_revision_panel",
        "name": "Refinitiv Estimate Revision Panel",
        "backend": "local_parquet_panel",
        "access_shape": "local_derived_tables",
        "analysis_readiness": "instant",
        "grain": "instrument_day",
        "time_field": "date",
        "entity_fields": ["ric"],
        "local_root": DERIVED_ROOT,
        "local_file": "estimate_revision_panel.parquet",
        "default_run_id": DERIVED_RUN,
        "description": "EPS mean with 1m/3m/6m revision deltas (trading-day lags).",
        "join_keys": ["ric", "date"],
        "entitlement_status": "derived",
        "field_coverage": "query-ready",
        "known_gap": "Revision windows are trading-day approximations",
        "best_use": "GDELT shock → analyst revision response",
        "collection_status": "derived_release",
    },
    {
        "dataset_id": "refinitiv_fundamental_annual_panel",
        "name": "Refinitiv Fundamental Annual Panel",
        "backend": "local_parquet_panel",
        "access_shape": "local_derived_tables",
        "analysis_readiness": "instant",
        "grain": "instrument_fiscal_year",
        "time_field": "fiscal_year",
        "entity_fields": ["ric"],
        "local_root": DERIVED_ROOT,
        "local_file": "fundamental_annual_panel.parquet",
        "default_run_id": DERIVED_RUN,
        "description": "Tidy FY fundamentals: revenue, income, debt, FCF.",
        "join_keys": ["ric", "fiscal_year"],
        "entitlement_status": "derived",
        "field_coverage": "partial",
        "known_gap": "FY only; not FQ PIT accounting",
        "best_use": "Annual factor screening and joins",
        "collection_status": "derived_release",
    },
    {
        "dataset_id": "refinitiv_entity_market_spine",
        "name": "Refinitiv Entity Market Spine",
        "backend": "local_parquet_panel",
        "access_shape": "local_derived_tables",
        "analysis_readiness": "instant",
        "grain": "instrument_snapshot",
        "time_field": "built_at",
        "entity_fields": ["ric", "gdelt_entity_id", "country_code", "in_spx", "in_jkse", "in_twii", "in_n225", "in_ks11", "in_sti"],
        "local_root": DERIVED_ROOT,
        "local_file": "entity_market_spine.parquet",
        "default_run_id": DERIVED_RUN,
        "description": "RIC spine + GDELT entity_id + current index membership flags.",
        "join_keys": ["ric", "gdelt_entity_id"],
        "entitlement_status": "derived",
        "field_coverage": "query-ready",
        "known_gap": "GDELT entity join via Asia entity master; US coverage partial",
        "best_use": "Cross-lane joins: GDELT ↔ Refinitiv ↔ index membership",
        "collection_status": "derived_release",
    },
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_index() -> dict:
    runs = []
    for path in sorted(BACKFILL_ROOT.iterdir()):
        if not path.is_dir():
            continue
        manifest = path / "manifest.json"
        validated = path / "VALIDATED.json"
        entry = {"run_id": path.name, "path": str(path.relative_to(REPO))}
        if manifest.exists():
            entry["manifest"] = json.loads(manifest.read_text(encoding="utf-8"))
        if validated.exists():
            entry["validated"] = json.loads(validated.read_text(encoding="utf-8"))
        runs.append(entry)
    return {"generated_at": utc_now(), "gdrive_root": GDRIVE_ROOT, "runs": runs}


def main() -> int:
    reg = json.loads(REGISTRY.read_text(encoding="utf-8"))
    by_id = {d["dataset_id"]: d for d in reg.get("datasets", [])}

    for extra in [FUNDAMENTALS_DATASET, RESCUED_DATASET, *EXTRA_DATASETS, *DERIVED_DATASETS]:
        if extra["dataset_id"] not in by_id:
            reg["datasets"].append(extra)
            by_id[extra["dataset_id"]] = extra

    for ds_id, run_id in RUN_BY_DATASET.items():
        if ds_id not in by_id:
            continue
        entry = by_id[ds_id]
        entry["default_run_id"] = run_id
        if ds_id.startswith("refinitiv_") and ds_id not in {
            "refinitiv_survivorship_universe_panel",
            "refinitiv_us_risk_overlay",
            "refinitiv_estimate_revision_panel",
            "refinitiv_fundamental_annual_panel",
            "refinitiv_entity_market_spine",
        }:
            entry["canonical_remote"] = f"{GDRIVE_ROOT}/{run_id}"
            entry["source_of_truth"] = "gdrive"
        entry["analysis_readiness"] = entry.get("analysis_readiness") or "instant"
        if ds_id in CAVEAT_METADATA:
            entry.update(CAVEAT_METADATA[ds_id])
        if "processed/" in entry.get("local_file", ""):
            entry["local_file"] = entry["local_file"].split("processed/", 1)[-1]
            if not entry["local_file"].startswith("processed/") and not entry["local_file"].startswith(DERIVED_RUN):
                entry["local_file"] = f"processed/{entry['local_file']}"

    reg["datasets"] = [by_id.get(d["dataset_id"], d) for d in reg["datasets"]]
    # refresh entries we touched
    for i, d in enumerate(reg["datasets"]):
        if d["dataset_id"] in RUN_BY_DATASET:
            reg["datasets"][i] = by_id[d["dataset_id"]]
        for extra in [FUNDAMENTALS_DATASET, RESCUED_DATASET, *EXTRA_DATASETS, *DERIVED_DATASETS]:
            if d["dataset_id"] == extra["dataset_id"]:
                reg["datasets"][i] = by_id[extra["dataset_id"]]

    reg["updated_at"] = utc_now()
    REGISTRY.write_text(json.dumps(reg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    index = build_index()
    (BACKFILL_ROOT / "INDEX.json").write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"registry_updated": True, "runs_indexed": len(index["runs"])}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
