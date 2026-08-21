#!/usr/bin/env python3
"""A thread with no mapped evidence starves every producer downstream.

Every synthesis thread on the live desk carries nodes=0, so column profiles,
unit conflicts and join candidates have nothing to run on and the method surface
renders over fields nothing writes. The retrieval to fix that already works:
asked the JKSE thread's own objective, semantic_discover returns the datasets
that thread's blueprint names by hand.
"""

from __future__ import annotations

import pytest

from scripts.research_data_mcp.synthesis.evidence_map import propose_evidence_nodes


class _Gateway:
    def __init__(self, rows, described=None, raises=False):
        self._rows = rows
        self._described = described or {}
        self._raises = raises

    def semantic_discover(self, query, *, limit=12):
        if self._raises:
            raise RuntimeError("index unavailable")
        return {"results": self._rows[:limit]}

    def describe_dataset(self, dataset_id):
        return self._described.get(dataset_id, {})


def test_held_datasets_become_evidence_nodes_the_store_recognises():
    gw = _Gateway(
        [{"dataset_id": "idn_fry_daily_cross_section", "title": "Indonesia FRY daily stock panel"}],
        {"idn_fry_daily_cross_section": {
            "readiness": "query_ready",
            "materialization": {"query_ready": True, "grain": "ticker_day"},
            "coverage": "2020–2026",
        }},
    )
    out = propose_evidence_nodes(gw, "weekly excess return per Indonesian listed equity")
    node = out["nodes"][0]
    # the store treats type=source or layer=evidence as evidence
    assert node["type"] == "source" and node["layer"] == "evidence"
    assert node["dataset_id"] == "idn_fry_daily_cross_section"
    assert node["status"] == "query_ready"
    assert node["query_ready"] is True
    assert node["grain"] == "ticker_day"


def test_registry_state_is_reported_not_improved():
    """A registered-but-not-ready input must still surface, carrying its state."""
    gw = _Gateway(
        [{"dataset_id": "compustat_na_fundamentals_annual", "title": "Compustat fundamentals"}],
        {"compustat_na_fundamentals_annual": {
            "readiness": "registered",
            "materialization": {"query_ready": False},
        }},
    )
    node = propose_evidence_nodes(gw, "company fundamentals")["nodes"][0]
    assert node["status"] == "registered"
    assert node["query_ready"] is False


def test_nothing_is_written():
    gw = _Gateway([{"dataset_id": "a", "title": "A"}])
    out = propose_evidence_nodes(gw, "anything")
    assert out["writes"] is False
    assert out["review_required"] is True


def test_no_match_says_so_and_points_onward():
    out = propose_evidence_nodes(_Gateway([]), "quantum tulip futures")
    assert out["nodes"] == []
    assert "no held dataset matched" in out["reason"]


def test_a_retrieval_failure_is_not_a_finding_of_no_evidence():
    """The distinction the desk keeps getting wrong: broken is not empty."""
    out = propose_evidence_nodes(_Gateway([], raises=True), "anything")
    assert out["nodes"] == []
    assert "retrieval failed" in out["reason"]
    assert "not a finding of no evidence" in out["reason"]


def test_an_empty_objective_maps_nothing():
    out = propose_evidence_nodes(_Gateway([{"dataset_id": "a"}]), "   ")
    assert out["nodes"] == []
    assert "no objective" in out["reason"]


def test_rows_without_a_dataset_id_are_not_evidence():
    """An external candidate is a procurement decision, not an input."""
    gw = _Gateway([{"title": "Some external corpus", "url": "https://example.org"}])
    assert propose_evidence_nodes(gw, "anything")["nodes"] == []


def test_describe_failure_still_yields_a_usable_node():
    class _Flaky(_Gateway):
        def describe_dataset(self, dataset_id):
            raise RuntimeError("registry read failed")

    node = propose_evidence_nodes(_Flaky([{"dataset_id": "x", "title": "X"}]), "q")["nodes"][0]
    assert node["dataset_id"] == "x"
    assert node["status"] == "registered"
