#!/usr/bin/env python3
"""Discover must offer held datasets a keyword query cannot reach.

Benchmarked on the real registry: keyword retrieval never finds 38-41% of datasets at
any depth, because min_relevance_threshold rises with each query word while dataset
metadata carries no research vocabulary. Semantic reaches 100% recall@10, and there is
no case of semantic missing what keyword found.
"""

from __future__ import annotations

from typing import Any

from scripts.research_data_mcp.gateway import ResearchDataGateway


class _Gateway(ResearchDataGateway):
    """Only the two retrieval paths and the registry lookup are exercised."""

    def __init__(self, semantic_rows: list[dict], registry: list[dict]) -> None:  # noqa: D107
        self._semantic_rows = semantic_rows
        self._registry = registry
        self.repo_root = "."

    def semantic_discover(self, query: str, *, limit: int = 12) -> dict[str, Any]:
        return {"rows": self._semantic_rows[:limit]}

    def list_datasets(self, **kwargs: Any) -> dict[str, Any]:
        return {"datasets": self._registry}


def _row(dataset_id: str, score: float) -> dict:
    return {"dataset_id": dataset_id, "title": dataset_id, "semantic_score": score}


def _registry_row(dataset_id: str) -> dict:
    return {"dataset_id": dataset_id, "name": dataset_id, "description": "d", "local_path": ""}


def test_semantic_hits_become_candidates_with_procurement_fields() -> None:
    gw = _Gateway([_row("twse_market", 0.51)], [_registry_row("twse_market")])
    out = gw._semantic_candidates("taiwan returns", limit=5, exclude=set())
    assert [c["dataset_id"] for c in out] == ["twse_market"]
    candidate = out[0]
    assert candidate["match_type"] == "semantic"
    assert candidate["score"] == 0.51
    # The UI renders these; a semantic row missing them would render as a blank tile.
    for field in ("procureability_label", "collect_via", "local_ready", "title", "badges"):
        assert field in candidate, f"semantic candidate lacks {field}, which the row projection reads"


def test_a_dataset_keyword_already_found_is_not_duplicated() -> None:
    gw = _Gateway([_row("twse_market", 0.51)], [_registry_row("twse_market")])
    out = gw._semantic_candidates("taiwan", limit=5, exclude={"twse_market"})
    assert out == []


def test_a_semantic_hit_absent_from_the_registry_is_dropped() -> None:
    gw = _Gateway([_row("ghost", 0.9)], [_registry_row("real")])
    assert gw._semantic_candidates("x", limit=5, exclude=set()) == []


def test_a_failing_semantic_index_never_breaks_discover() -> None:
    class _Broken(_Gateway):
        def semantic_discover(self, query: str, *, limit: int = 12) -> dict[str, Any]:
            raise RuntimeError("index unavailable")

    gw = _Broken([], [_registry_row("real")])
    assert gw._semantic_candidates("x", limit=5, exclude=set()) == []
