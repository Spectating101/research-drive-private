#!/usr/bin/env python3
"""Discover exists to find what the desk does NOT hold.

DISCOVER_ADAPTIVE_FREEZE_2026-07-28 is explicit: "Library evidence is compact chrome, not
a permanent result section" and "external offerings remain the centre priority". Held rows
are reassurance that something close is already on the shelf — they must never be returned
as though they were the offering, and the response must say which it is.

Route discovery is the half that answers the actual question, so it also indexes the
access-scope record: reachable_products, coverage notes and fetch modes. Those are recorded
facts, not invented entitlements — a source with no patent record still misses.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.research_data_mcp.semantic_index import SemanticCatalogIndex


class _Engine:
    @staticmethod
    def list_datasets() -> list[dict]:
        return [{"dataset_id": "held", "name": "Held", "description": "on disk"}]


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
                "id": "public_macro",
                "label": "Public macro baselines (Ken French etc.)",
                "provider": "Public academic mirrors",
                "capabilities": [],
                "access_mode": "materialized_instant",
                # from databank_access_scope.json
                "coverage_notes": ["Factor returns not single-name prices"],
                "fetch_modes": ["ken_french_zip", "queue_download"],
            },
            {
                "id": "lseg_desktop_rescue",
                "label": "LSEG Eikon desktop rescue",
                "provider": "LSEG Refinitiv",
                "capabilities": ["risk_overlay"],
                "access_mode": "materialized_instant",
                "reachable_products": ["US vol / skew / put-call / short-interest daily history"],
            },
        ]


def _index() -> SemanticCatalogIndex:
    index = SemanticCatalogIndex(Path("."))
    index.build(_Gateway())
    return index


def test_reachable_products_are_indexed() -> None:
    doc = next(d for d in _index()._docs if d["id"] == "lseg_desktop_rescue")
    text = doc["text"].lower()
    for word in ("skew", "short-interest", "put-call"):
        assert word in text, f"{word!r} missing; the access-scope record was not indexed"


def test_coverage_notes_and_fetch_modes_are_indexed() -> None:
    doc = next(d for d in _index()._docs if d["id"] == "public_macro")
    text = doc["text"].lower()
    assert "factor returns" in text
    assert "ken french" in text


def test_a_source_with_no_record_of_a_capability_still_misses() -> None:
    """Indexing recorded facts must not become inventing entitlements."""
    text = " ".join(d["text"].lower() for d in _index()._docs if d["kind"] == "source_route")
    assert "patent" not in text


# ---------- Discover must declare held rows as evidence, not offering ----------

def test_discover_declares_held_rows_as_library_evidence() -> None:
    from scripts.research_data_mcp.gateway import ResearchDataGateway

    class _Gw(ResearchDataGateway):
        def __init__(self) -> None:
            self.repo_root = "."

        def semantic_discover(self, query: str, *, limit: int = 12) -> dict[str, Any]:
            return {"rows": [{"dataset_id": "held", "title": "Held", "semantic_score": 0.5}]}

        def list_datasets(self, **kw: Any) -> dict[str, Any]:
            return {"datasets": [{"dataset_id": "held", "name": "Held", "description": "d",
                                  "local_path": ""}]}

    gw = _Gw()
    rows, _status = gw._semantic_candidates_with_status("q", limit=5, exclude=set())
    assert rows, "held evidence should still be gathered"
    # Every held row must be labelled so no surface can paint it as an external offering.
    assert all(r.get("result_role") == "library_evidence" for r in rows), rows[0]
    assert all(r.get("is_offering") is False for r in rows)
