"""Honest evidence placement — no canned why, no semantic filler as hits."""

from __future__ import annotations

from scripts.research_data_mcp.evidence_placement import (
    PLACEMENT_HELD,
    PLACEMENT_ROUTE,
    clean_why,
    drop_semantic_filler,
    evidence_placement,
    stamp_evidence_fields,
)


def test_canned_why_is_stripped():
    assert clean_why("matched on meaning, not wording") == ""
    assert clean_why("On-chain USDT during peg stress") == "On-chain USDT during peg stress"


def test_semantic_filler_without_why_is_dropped():
    rows = drop_semantic_filler(
        [
            {"dataset_id": "a", "selected_by": "semantic", "selection_reason": "matched on meaning, not wording"},
            {"dataset_id": "b", "selected_by": "catalog_reader", "selection_reason": "peg events"},
            {"dataset_id": "c", "selected_by": "lexical"},
        ]
    )
    assert [r["dataset_id"] for r in rows] == ["b", "c"]


def test_registry_dataset_places_as_held():
    assert evidence_placement({"kind": "registry_dataset", "dataset_id": "x", "local_ready": True}) == PLACEMENT_HELD


def test_collectable_external_places_as_route():
    assert evidence_placement({"title": "X", "url": "https://example.org", "collect_via": "http"}) == PLACEMENT_ROUTE


def test_stamp_attaches_placement_and_why():
    out = stamp_evidence_fields(
        {
            "dataset_id": "peg",
            "kind": "dataset",
            "local_ready": True,
            "selection_reason": "USDT flows during de-pegs",
        }
    )
    assert out["placement"] == PLACEMENT_HELD
    assert out["why"] == "USDT flows during de-pegs"
    assert "matched on meaning" not in (out.get("selection_reason") or "")
