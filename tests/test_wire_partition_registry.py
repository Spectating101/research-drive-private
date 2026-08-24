"""Partition registry wiring — all catalog cards map to a collection partition."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


def _assigned_ids() -> set[str]:
    parts = json.loads((REPO / "config/collection_partitions.json").read_text(encoding="utf-8"))
    out: set[str] = set()
    for part in parts.get("partitions") or []:
        out.update(str(x) for x in part.get("registry_dataset_ids") or [])
    return out


def _registry_ids() -> set[str]:
    reg = json.loads((REPO / "config/research_query_registry.json").read_text(encoding="utf-8"))
    return {str(d["dataset_id"]) for d in reg.get("datasets") or [] if d.get("dataset_id")}


def test_all_registry_datasets_assigned_to_partition():
    reg = _registry_ids()
    assigned = _assigned_ids()
    missing = sorted(reg - assigned)
    assert not missing, f"unassigned registry ids: {missing[:10]}"


@pytest.mark.parametrize(
    "dataset_id,partition",
    [
        ("refinitiv_security_master", "reference.refinitiv-backfill"),
        ("jkse_pit_idn_microstructure_revisions", "derived.research-panels"),
        ("gdelt_high_priority_urls", "news.gdelt-expanded"),
    ],
)
def test_partition_id_stamped_on_registry(dataset_id: str, partition: str):
    reg = json.loads((REPO / "config/research_query_registry.json").read_text(encoding="utf-8"))
    row = next(d for d in reg["datasets"] if d["dataset_id"] == dataset_id)
    assert row.get("partition_id") == partition
