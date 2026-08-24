#!/usr/bin/env python3
"""Wire unassigned registry dataset_ids into collection_partitions + stamp partition_id."""

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
REGISTRY = ROOT / "config/research_query_registry.json"
PARTITIONS = ROOT / "config/collection_partitions.json"

DERIVED_PANEL_PREFIXES = (
    "idn_",
    "ticker_week_",
    "pit_",
    "jkse_",
)
DERIVED_PANEL_EXACT = {
    "asia_country_week_news_market_primary",
    "asia_entity_ticker_mapping_layer",
    "cross_asset_fused_primary_panel",
    "daily_ticker_entity_shock_panel",
}
REFINITIV_DERIVED_ONLY = {
    "refinitiv_survivorship_universe_panel",
    "refinitiv_us_risk_overlay",
    "refinitiv_estimate_revision_panel",
    "refinitiv_fundamental_annual_panel",
    "refinitiv_entity_market_spine",
    "refinitiv_entity_market_spine_expanded",
}


def _stamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _assigned_map(part_doc: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in part_doc.get("partitions") or []:
        pid = str(part.get("id") or "")
        for did in part.get("registry_dataset_ids") or []:
            out[str(did)] = pid
    return out


def infer_partition_id(dataset_id: str, ds: dict[str, Any]) -> str:
    did = str(dataset_id or "").strip()
    if not did:
        return "catalog.curated-index"

    backend = str(ds.get("backend") or "")
    domain = str(ds.get("domain") or "").lower()

    if did.startswith("refinitiv_"):
        if did in REFINITIV_DERIVED_ONLY:
            return "derived.research-panels"
        return "reference.refinitiv-backfill"

    if did.startswith(DERIVED_PANEL_PREFIXES) or did in DERIVED_PANEL_EXACT:
        return "derived.research-panels"

    if did.startswith("coingecko") or domain == "crypto" and did.startswith("scrape_"):
        return "markets.crypto-coingecko"

    if did.startswith("procured_") or did.startswith("datacite_10."):
        return "acquired.procured"

    if did.startswith("investment_") or did in {
        "collection_queue_status",
        "datacite_local_harvest_status",
        "investment_operator_dashboard",
    }:
        return "ops.collection-queue"

    if did.startswith("sec_") or did in {
        "external_dataset_catalog",
        "external_dataset_catalog_curated",
    }:
        return "catalog.curated-index"

    if did.startswith("gdelt_"):
        if did in {"gdelt_asia_daily_country_panel", "gdelt_gkg_events"}:
            return "news.gdelt-asia"
        return "news.gdelt-expanded"

    if did.startswith("spk_") or "ethereum" in did:
        return "markets.ethereum-usdt"

    if did.startswith("twse_"):
        return "official.exchange-disclosures"
    if did.startswith("mops_"):
        return "official.mops-disclosures"

    if did == "opensea_nft_metadata_layer":
        return "markets.nft-opensea"

    if did.startswith("scrape_"):
        return "catalog.curated-index"

    if did.startswith("public_macro_"):
        return "official.macro-asia"

    if did.startswith("public_equity_"):
        return "reference.crsp-moveit"

    if did.startswith("hf_"):
        return "acquired.procured"

    if backend in {"local_jsonl_catalog", "metadata_catalog"}:
        return "catalog.curated-index"

    return "catalog.curated-index"


def wire_registry(*, dry_run: bool = False) -> dict[str, Any]:
    reg_doc = json.loads(REGISTRY.read_text(encoding="utf-8"))
    part_doc = json.loads(PARTITIONS.read_text(encoding="utf-8"))
    assigned = _assigned_map(part_doc)
    datasets = list(reg_doc.get("datasets") or [])

    routes: dict[str, list[str]] = {}
    stamped = 0
    for ds in datasets:
        did = str(ds.get("dataset_id") or "")
        if not did:
            continue
        if did in assigned:
            pid = assigned[did]
        else:
            pid = infer_partition_id(did, ds)
            routes.setdefault(pid, []).append(did)
            assigned[did] = pid

        if str(ds.get("partition_id") or "") != pid:
            stamped += 1
            if not dry_run:
                ds["partition_id"] = pid
                collection = dict(ds.get("collection") or {})
                collection["partition_id"] = pid
                collection.setdefault("wired_at", _stamp())
                ds["collection"] = collection

    if not dry_run:
        part_by_id = {str(p.get("id")): p for p in part_doc.get("partitions") or []}
        for pid, ids in sorted(routes.items()):
            part = part_by_id.get(pid)
            if not part:
                continue
            cur = {str(x) for x in part.get("registry_dataset_ids") or []}
            cur.update(ids)
            part["registry_dataset_ids"] = sorted(cur)
            part["last_registry_wired_at"] = _stamp()

        reg_doc["datasets"] = datasets
        REGISTRY.write_text(json.dumps(reg_doc, indent=2) + "\n", encoding="utf-8")
        PARTITIONS.write_text(json.dumps(part_doc, indent=2) + "\n", encoding="utf-8")
        final_assigned = _assigned_map(json.loads(PARTITIONS.read_text(encoding="utf-8")))
    else:
        final_assigned = dict(assigned)

    all_ids = {str(d.get("dataset_id")) for d in datasets if d.get("dataset_id")}
    unassigned_remaining = len(all_ids - set(final_assigned))

    return {
        "dry_run": dry_run,
        "registry_datasets": len(datasets),
        "new_routes": {k: len(v) for k, v in sorted(routes.items())},
        "new_route_total": sum(len(v) for v in routes.values()),
        "partition_id_stamped": stamped,
        "unassigned_remaining": unassigned_remaining,
    }

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    summary = wire_registry(dry_run=args.dry_run)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
