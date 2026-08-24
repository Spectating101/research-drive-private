"""Databank canonical source map — registry cards resolve to source systems."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def audit():
    from scripts.research_data_mcp.source_map import build_source_map_audit

    return build_source_map_audit(REPO)


def test_all_registry_datasets_mapped_to_source(audit):
    unmapped = audit.get("unmapped_registry_ids") or []
    assert not unmapped, f"unmapped: {unmapped}"


def test_wrds_source_planned_not_ingested(audit):
    wrds = next(s for s in audit["sources"] if s["id"] == "wrds_crsp_compustat")
    assert wrds["access_mode"] == "planned"
    assert wrds["materialization"]["ingested"] is False
    assert wrds["registry_dataset_count"] == 0


def test_lseg_edp_materialized(audit):
    lseg = next(s for s in audit["sources"] if s["id"] == "lseg_edp")
    assert lseg["registry_dataset_count"] >= 9
    assert lseg["instant_dataset_count"] >= 9
    assert lseg["materialization"]["ingested"] is True


def test_bigquery_and_datacite_sources_present(audit):
    ids = {s["id"] for s in audit["sources"]}
    assert "bigquery_public" in ids
    assert "datacite_harvest" in ids
    assert "datacite_procured" in ids
    bq = next(s for s in audit["sources"] if s["id"] == "bigquery_public")
    assert bq["access_mode"] == "live_connector"
    assert "ethereum_usdt_transfers" in bq["registry_dataset_ids"]


def test_source_map_config_loads():
    path = REPO / "config/databank_source_map.json"
    assert path.is_file()
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert doc.get("version") == 1
    assert len(doc.get("sources") or []) >= 15


def test_synthesis_outputs_map_to_derived_synthesis_not_upstream_vendors(audit):
    """synthesis_* cards are derived thread outputs — not raw vendor lineage."""
    synth = next(s for s in audit["sources"] if s["id"] == "derived_synthesis")
    assert synth["access_mode"] == "derived_internal"
    ids = set(synth.get("registry_dataset_ids") or [])
    assert "synthesis_smoke_stablecoin_weekly_20260713" in ids
    assert "synthesis_stablecoin_weekly_v2_20260713" in ids
    # Must not silently absorb into vendor or generic research-panel buckets
    for sid in ("ethereum_onchain", "coingecko", "bigquery_public", "derived_research_panels"):
        other = next(s for s in audit["sources"] if s["id"] == sid)
        overlap = ids & set(other.get("registry_dataset_ids") or [])
        assert not overlap, f"{sid} incorrectly claims synthesis cards: {sorted(overlap)}"


def test_synthesis_registry_cards_preserve_upstream_lineage():
    path = REPO / "config/research_query_registry.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    by_id = {str(ds.get("dataset_id")): ds for ds in doc.get("datasets") or []}
    for did in (
        "synthesis_smoke_stablecoin_weekly_20260713",
        "synthesis_stablecoin_weekly_v2_20260713",
    ):
        ds = by_id[did]
        assert ds.get("source_id") == "derived_synthesis"
        lineage = ds.get("lineage") or {}
        assert "stablecoin_trust_engagement_weekly" in (lineage.get("upstream_dataset_ids") or [])
        assert lineage.get("derived_via") == "synthesis_execute"
        # Drive / partition provenance stays intact (raw remote lineage preserved)
        assert lineage.get("canonical_remote")
        assert lineage.get("partition_id") == "derived.research-panels"

