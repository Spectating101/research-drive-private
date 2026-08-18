#!/usr/bin/env python3
"""A count that disagrees with the payload is worse than no count.

Semantic route supplements were appended to results without updating total, so the
response could carry rows and report total: 0. Anything reading total to decide whether
to escalate to procurement would draw the wrong conclusion, and telemetry would record a
miss on a successful answer. Caught in review.
"""

from __future__ import annotations

from typing import Any

from scripts.research_data_mcp.gateway import ResearchDataGateway


class _Gw(ResearchDataGateway):
    """Underlying lexical search finds nothing; semantic finds two routes."""

    def __init__(self) -> None:
        self.repo_root = "."

    def semantic_source_routes(self, query: str, *, limit: int = 8) -> list[dict[str, Any]]:
        return [
            {"source_id": "capital_iq_compustat", "label": "Compustat", "kind": "source"},
            {"source_id": "wrds_crsp_compustat", "label": "WRDS", "kind": "source"},
        ]


def _patched_search(monkeypatch, base: dict[str, Any]) -> dict[str, Any]:
    import scripts.research_data_mcp.discover_source_search as dss

    monkeypatch.setattr(dss, "search_discover_sources", lambda *a, **k: dict(base))
    return _Gw().discover_source_search("company fundamentals", limit=5)


def test_total_counts_the_semantic_supplements(monkeypatch) -> None:
    out = _patched_search(monkeypatch, {"results": [], "total": 0, "index_miss": True})
    assert len(out["results"]) == 2
    assert out["total"] == 2, f"reported total {out['total']} against {len(out['results'])} rows"


def test_total_stays_consistent_when_lexical_already_found_rows(monkeypatch) -> None:
    base = {"results": [{"source_id": "sec_edgar", "kind": "source"}], "total": 1, "index_miss": False}
    out = _patched_search(monkeypatch, base)
    assert out["total"] == len(out["results"]) == 3


def test_no_supplements_leaves_the_total_untouched(monkeypatch) -> None:
    class _Empty(_Gw):
        def semantic_source_routes(self, query: str, *, limit: int = 8):
            return []

    import scripts.research_data_mcp.discover_source_search as dss

    monkeypatch.setattr(dss, "search_discover_sources",
                        lambda *a, **k: {"results": [{"source_id": "x"}], "total": 1})
    out = _Empty().discover_source_search("q", limit=5)
    assert out["total"] == 1
