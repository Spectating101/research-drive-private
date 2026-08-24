#!/usr/bin/env python3
"""Register official Taiwan + OpenSea panels in the query registry and partition map."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
REGISTRY = REPO / "config/research_query_registry.json"
PARTITIONS = REPO / "config/collection_partitions.json"


def _stamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _upsert_dataset(doc: dict[str, Any], spec: dict[str, Any]) -> bool:
    datasets = doc.setdefault("datasets", [])
    did = str(spec["dataset_id"])
    for i, row in enumerate(datasets):
        if str(row.get("dataset_id")) == did:
            merged = dict(row)
            merged.update(spec)
            datasets[i] = merged
            return True
    datasets.append(spec)
    return True


def _wire_partition(cfg: dict[str, Any], partition_id: str, dataset_id: str) -> bool:
    updated = False
    for row in cfg.get("partitions") or []:
        if str(row.get("id")) != partition_id:
            continue
        existing = {str(x) for x in row.get("registry_dataset_ids") or []}
        if dataset_id not in existing:
            row["registry_dataset_ids"] = sorted(existing | {dataset_id})
            row["last_registry_wired_at"] = _stamp()
            updated = True
        break
    return updated


def main() -> int:
    from scripts.research_data_mcp.procurement_fast import local_path_has_data

    doc = json.loads(REGISTRY.read_text(encoding="utf-8"))
    cfg = json.loads(PARTITIONS.read_text(encoding="utf-8"))

    panels: list[dict[str, Any]] = [
        {
            "dataset_id": "mops_governance_panel",
            "name": "Taiwan MOPS governance misconduct panel",
            "backend": "local_json_glob",
            "access_shape": "local_file_tree",
            "analysis_readiness": "sample_now_full_later",
            "grain": "governance_event",
            "local_path": "data_lake/official_disclosures/taiwan_mops/*",
            "description": "Official TWSE OpenAPI governance feeds: penalty cases, material information, ESG board structure — MOPS-adjacent misconduct panel.",
            "capabilities": ["limit", "export_json"],
            "recommended_use": "Corporate governance, misconduct, and trust-premium research on Taiwan listed firms.",
            "keywords": ["mops", "taiwan", "governance", "misconduct", "trust", "penalty"],
            "partition_id": "official.mops-disclosures",
            "procurement": {
                "source_task_id": "mops_governance_panel",
                "promoted_at": _stamp(),
                "job_type": "collection_queue",
            },
        },
        {
            "dataset_id": "opensea_nft_metadata_layer",
            "name": "OpenSea NFT collection metadata",
            "backend": "local_json_glob",
            "access_shape": "local_file_tree",
            "analysis_readiness": "metadata_search",
            "grain": "collection_snapshot",
            "local_path": "data_lake/opensea/*",
            "description": "Collection-level NFT metadata and image manifests for rarity, network, and emotional-dividend replication studies.",
            "capabilities": ["limit", "export_json"],
            "recommended_use": "NFT asset pricing, OpenSea metadata graph, and SSRN-style replication panels.",
            "keywords": ["nft", "opensea", "emotional", "non-fungible", "cryptopunk", "replication"],
            "partition_id": "markets.nft-opensea",
            "procurement": {
                "source_task_id": "opensea_nft_metadata_layer",
                "promoted_at": _stamp(),
                "job_type": "vault_partition",
            },
        },
    ]

    for spec in panels:
        did = spec["dataset_id"]
        lp = str(spec.get("local_path") or "")
        if not local_path_has_data(REPO, lp):
            print(f"skip {did}: no local bytes at {lp}")
            continue
        _upsert_dataset(doc, spec)
        pid = str(spec.get("partition_id") or "")
        if pid:
            _wire_partition(cfg, pid, did)
        print(f"registered {did} -> {pid or '(no partition)'}")

    REGISTRY.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    PARTITIONS.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")

    from scripts.research_data_mcp.collection_dictionary import write_dictionary
    from scripts.research_data_mcp.collection_index import build_index

    write_dictionary(REPO)
    stats = build_index(REPO)
    print("index", stats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
