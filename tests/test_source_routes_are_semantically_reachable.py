#!/usr/bin/env python3
"""Procurement is judged on routes, not on the datasets already materialised.

The registry's held datasets are residue; the offering is the 21 routes the desk can
obtain through. Measured, route discovery named a usable route for only 6 of 13 research
needs, and the misses were the differentiating ones: Compustat, OpenAlex, Zenodo,
HuggingFace, BigQuery patents, Fama-French, LSEG vol/skew. The semantic index built only
`registry_dataset` and `queue_task` docs, so no meaning-based path to a source existed.
"""

from __future__ import annotations

from pathlib import Path

from scripts.research_data_mcp.semantic_index import SemanticCatalogIndex


class _Engine:
    @staticmethod
    def list_datasets() -> list[dict]:
        return [{"dataset_id": "held_thing", "name": "Held", "description": "already on disk"}]


class _Orchestrator:
    @staticmethod
    def queue_tasks(runnable_only: bool = False) -> list[dict]:
        return []


class _Gateway:
    engine = _Engine()
    orchestrator = _Orchestrator()
    repo_root = Path(".")

    @staticmethod
    def source_routes_for_index() -> list[dict]:
        return [
            {
                "id": "capital_iq_compustat",
                "label": "S&P Capital IQ / Compustat",
                "provider": "S&P Global",
                "capabilities": ["fundamentals", "index_pit_survivorship"],
                "access_mode": "materialized_bulk",
            },
            {
                "id": "openalex",
                "label": "OpenAlex works search",
                "provider": "OpenAlex",
                "capabilities": ["scholarly_metadata"],
                "access_mode": "live_connector",
            },
        ]


def _index() -> SemanticCatalogIndex:
    index = SemanticCatalogIndex(Path('.'))
    index.build(_Gateway())
    return index


def test_sources_are_indexed_as_their_own_kind() -> None:
    index = _index()
    kinds = {str(doc.get("kind")) for doc in index._docs}
    assert "source_route" in kinds
    ids = {doc["id"] for doc in index._docs if doc["kind"] == "source_route"}
    assert ids == {"capital_iq_compustat", "openalex"}


def test_capability_tokens_are_searchable_as_words() -> None:
    """`index_pit_survivorship` must not be one opaque token."""
    index = _index()
    doc = next(d for d in index._docs if d["id"] == "capital_iq_compustat")
    text = doc["text"].lower()
    for word in ("fundamentals", "survivorship", "compustat"):
        assert word in text, f"{word!r} missing from indexed text"


def test_a_source_search_never_returns_held_datasets() -> None:
    index = _index()
    hits = index.semantic_search("company fundamentals", limit=5, kinds={"source_route"})
    assert hits
    assert all(h.get("kind") == "source_route" for h in hits)
    assert "held_thing" not in {h.get("id") for h in hits}
